from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .base import Meter, ProviderSnapshot

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
DASHBOARD_URL = "https://claude.ai/settings/usage"
OAUTH_BETA = "oauth-2025-04-20"
CREDENTIALS_FILE = Path.home() / ".claude" / ".credentials.json"

# Window key → label. Claude Code calls five_hour the "session limit"; the mockup
# calls it the 5-hour limit, so we keep the mockup's wording.
WINDOWS: list[tuple[str, str]] = [
    ("five_hour", "5-hour limit"),
    ("seven_day", "Weekly"),
    ("seven_day_opus", "Opus weekly"),
    ("seven_day_sonnet", "Sonnet weekly"),
]


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class ClaudeAuthError(RuntimeError):
    """Raised when the local Claude Code login is missing or stale."""


class ClaudeProvider:
    """Claude subscription limits, read through the Claude Code OAuth login.

    The token is read but never written. Claude Code owns the refresh cycle;
    rotating the refresh token here could sign the user out of the CLI, so an
    expired token surfaces as auth_needed instead.
    """

    id = "claude"
    display_name = "Claude Code"

    def _read_oauth(self) -> dict[str, Any]:
        path = Path(os.environ.get("CLAUDE_CREDENTIALS_FILE", CREDENTIALS_FILE))
        if not path.exists():
            raise ClaudeAuthError("Sign in to Claude Code")
        try:
            creds = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise ClaudeAuthError(f"Could not read Claude login: {exc}") from exc
        oauth = creds.get("claudeAiOauth") or {}
        if not oauth.get("accessToken"):
            raise ClaudeAuthError("Sign in to Claude Code")
        return oauth

    def available(self) -> bool:
        try:
            self._read_oauth()
        except ClaudeAuthError:
            return False
        return True

    def fetch(self) -> ProviderSnapshot:
        try:
            oauth = self._read_oauth()
        except ClaudeAuthError as exc:
            return self._auth_snapshot(str(exc))

        expires_at = oauth.get("expiresAt")
        if isinstance(expires_at, (int, float)) and expires_at / 1000 <= time.time():
            return self._auth_snapshot("Claude login expired — run claude")

        try:
            usage = self._get_usage(oauth["accessToken"])
        except PermissionError as exc:
            return self._auth_snapshot(str(exc))

        metrics: list[Meter] = []
        for key, label in WINDOWS:
            window = usage.get(key)
            if not isinstance(window, dict):
                continue
            utilization = window.get("utilization")
            if utilization is None:
                continue
            metrics.append(
                Meter(key, label, float(utilization), resets_at=_parse_iso(window.get("resets_at")))
            )

        if not metrics:
            return ProviderSnapshot.error_snapshot(
                provider_id=self.id,
                display_name=self.display_name,
                icon="claude",
                message="No limit windows reported",
                dashboard_url=DASHBOARD_URL,
            )

        plan = oauth.get("subscriptionType")
        return ProviderSnapshot(
            provider_id=self.id,
            display_name=self.display_name,
            icon="claude",
            plan=str(plan).title() if plan else None,
            metrics=metrics,
            primary_key=metrics[0].key,
            dashboard_url=DASHBOARD_URL,
            status="ok",
            error=None,
            fetched_at=datetime.now(timezone.utc),
        )

    def _auth_snapshot(self, message: str) -> ProviderSnapshot:
        return ProviderSnapshot.error_snapshot(
            provider_id=self.id,
            display_name=self.display_name,
            icon="claude",
            message=message,
            auth_needed=True,
            dashboard_url=DASHBOARD_URL,
        )

    def _get_usage(self, access_token: str) -> dict[str, Any]:
        request = urllib.request.Request(
            USAGE_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "anthropic-beta": OAUTH_BETA,
                "User-Agent": "cursor-spend-monitor",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            if exc.code in {401, 403}:
                raise PermissionError("Claude login rejected — run claude to refresh") from exc
            detail = exc.read().decode("utf-8", errors="replace")[:200]
            raise RuntimeError(f"HTTP {exc.code} from Claude usage: {detail}") from exc

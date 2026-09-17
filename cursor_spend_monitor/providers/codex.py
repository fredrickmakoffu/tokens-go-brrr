from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..instances import ProcessSpec
from .base import Meter, ProviderSnapshot

USAGE_URL = "https://chatgpt.com/backend-api/codex/usage"
DASHBOARD_URL = "https://chatgpt.com/codex"
CREDENTIALS_FILE = Path.home() / ".codex" / "auth.json"

# plan_type values the ChatGPT usage endpoint reports, → menu-label wording.
PLAN_NAMES = {
    "free": "Free",
    "chatgptplus": "ChatGPT Plus",
    "chatgptpro": "ChatGPT Pro",
    "chatgptteam": "Team",
    "chatgptbusiness": "Business",
    "chatgptenterprise": "Enterprise",
}

# limit_window_seconds → meter label. The ChatGPT response names no window, only
# the seconds, so the label is derived from the duration like the daemon's other
# providers do ("5-hour limit", "Monthly limit", ...).
WINDOW_LABELS = {
    18000: "5-hour limit",
    86400: "Daily",
    604800: "Weekly",
    2592000: "Monthly limit",
}


def _window_label(seconds: Any) -> str:
    if isinstance(seconds, (int, float)) and not isinstance(seconds, bool):
        if seconds in WINDOW_LABELS:
            return WINDOW_LABELS[seconds]
        if seconds > 0:
            days = seconds // 86400
            if days > 0 and days * 86400 == seconds:
                return f"{days} day window"
    return "Rolling limit"


def _parse_epoch(value: Any) -> datetime | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    try:
        return datetime.fromtimestamp(value, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _jwt_exp(token: str) -> int | None:
    """Exact JWT expiry (seconds) without verifying the signature.

    Same trick the Cursor auth path uses: the access token is only read, never
    written, so the CLI owns the refresh cycle and a stale token surfaces as
    auth_needed instead of us risking signing the user out by rotating it.
    """
    if not token:
        return None
    try:
        payload = token.split(".")[1]
        pad = "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload + pad))
    except (IndexError, ValueError, json.JSONDecodeError):
        return None
    exp = data.get("exp")
    if not isinstance(exp, (int, float)):
        return None
    try:
        return int(exp)
    except (TypeError, ValueError, OverflowError):
        return None


def _is_bot_challenge(code: int, body: str) -> bool:
    """True when a 403 carries chatgpt.com's HTML anti-bot challenge.

    chatgpt.com's edge intermittently answers non-browser clients with an HTML
    block page. That is a transient bot block, not a login problem; a JSON
    rejection is a real auth failure.
    """
    return code == 403 and "<html" in body[:512].lower()


class CodexAuthError(RuntimeError):
    """Raised when the local Codex login is missing or unusable."""


class CodexProvider:
    """ChatGPT Codex plan limits, read through the Codex CLI's own login.

    The token is read but never written. Codex owns the refresh cycle and this
    daemon must not race it on auth.json, so an expired token surfaces as
    auth_needed instead (same policy as ClaudeProvider).
    """

    id = "codex"
    display_name = "Codex"
    # pi-lens-ignore: python-mutable-class-attr
    process_specs = [
        ProcessSpec(
            names=frozenset({"codex", "codex.exe"}),
            label="session",
        ),
    ]

    def _read_auth(self) -> dict[str, Any]:
        path = Path(os.environ.get("CODEX_CREDENTIALS_FILE", CREDENTIALS_FILE))
        if not path.exists():
            raise CodexAuthError("Sign in to Codex")
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise CodexAuthError(f"Could not read Codex login: {exc}") from exc
        # Only the ChatGPT OAuth login can hit the usage endpoint. An API key
        # (auth_mode != chatgpt) bills usage differently and has no window here.
        if data.get("auth_mode") != "chatgpt":
            raise CodexAuthError("Codex must be signed in to a ChatGPT account")
        tokens = data.get("tokens") or {}
        if not tokens.get("access_token"):
            raise CodexAuthError("Sign in to Codex")
        return data

    def available(self) -> bool:
        try:
            self._read_auth()
        except CodexAuthError:
            return False
        return True

    def fetch(self) -> ProviderSnapshot:
        try:
            auth = self._read_auth()
        except CodexAuthError as exc:
            return self._auth_snapshot(str(exc))

        token = auth["tokens"]["access_token"]
        expires_at = _jwt_exp(token)
        if expires_at is not None and expires_at <= time.time():
            return self._auth_snapshot("Codex login expired — run codex")

        try:
            usage = self._get_usage(token)
        except PermissionError as exc:
            return self._auth_snapshot(str(exc))

        rate = usage.get("rate_limit") or {}
        allowed = rate.get("allowed")
        if allowed is not None and not allowed:
            return ProviderSnapshot.error_snapshot(
                provider_id=self.id,
                display_name=self.display_name,
                icon="codex",
                message="Codex is blocked on this plan",
                dashboard_url=DASHBOARD_URL,
            )

        metrics: list[Meter] = []
        for key, window in (
            ("monthly", rate.get("primary_window")),
            ("window", rate.get("secondary_window")),
        ):
            if not isinstance(window, dict):
                continue
            pct = window.get("used_percent")
            if pct is None:
                continue
            try:
                pct_float = float(pct)
            except (TypeError, ValueError):
                continue
            metrics.append(
                Meter(
                    key,
                    _window_label(window.get("limit_window_seconds")),
                    pct_float,
                    resets_at=_parse_epoch(window.get("reset_at")),
                )
            )

        if not metrics:
            return ProviderSnapshot.error_snapshot(
                provider_id=self.id,
                display_name=self.display_name,
                icon="codex",
                message="No limit window reported",
                dashboard_url=DASHBOARD_URL,
            )

        plan_type = str(usage.get("plan_type") or "")
        return ProviderSnapshot(
            provider_id=self.id,
            display_name=self.display_name,
            icon="codex",
            plan=PLAN_NAMES.get(plan_type.lower(), plan_type.title() or None),
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
            icon="codex",
            message=message,
            auth_needed=True,
            dashboard_url=DASHBOARD_URL,
        )

    def _get_usage(self, access_token: str) -> dict[str, Any]:
        if urllib.parse.urlsplit(USAGE_URL).scheme != "https":
            raise RuntimeError(f"Unsupported usage URL scheme: {USAGE_URL}")
        request = urllib.request.Request(
            USAGE_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "User-Agent": "cursor-spend-monitor",
            },
        )
        try:
            # pi-lens-ignore: S310
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            if exc.code in {401, 403}:
                # chatgpt.com's edge intermittently answers non-browser clients
                # with an HTML anti-bot challenge (403). That is a transient
                # block, not a login problem — surface it as retryable, and only
                # report a login failure for a real JSON rejection.
                try:
                    body = exc.read().decode("utf-8", errors="replace")
                except (AttributeError, OSError, ValueError):
                    body = ""
                if _is_bot_challenge(exc.code, body):
                    raise RuntimeError(
                        "chatgpt.com blocked the request — retrying later"
                    ) from exc
                raise PermissionError("Codex login rejected — run codex") from exc
            detail = exc.read().decode("utf-8", errors="replace")[:200]
            raise RuntimeError(f"HTTP {exc.code} from Codex usage: {detail}") from exc

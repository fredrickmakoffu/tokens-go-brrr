from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..instances import ProcessSpec
from .base import Meter, ProviderSnapshot

USAGE_URL = "https://opencode.ai/zen/go/v1/usage"
DASHBOARD_URL = "https://opencode.ai/console"
AUTH_KEY = "opencode-go"

# Window key → label, in the order they are shown. The API names the short
# window "rolling" without stating its length, so the label does not claim one.
WINDOWS: list[tuple[str, str]] = [
    ("rolling", "Rolling limit"),
    ("weekly", "Weekly"),
    ("monthly", "Monthly"),
]


def _auth_path() -> Path:
    data_home = os.environ.get("XDG_DATA_HOME")
    base = Path(data_home) if data_home else Path.home() / ".local" / "share"
    return base / "opencode" / "auth.json"


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class OpenCodeAuthError(RuntimeError):
    """Raised when no OpenCode Go API key can be found."""


class OpenCodeProvider:
    """OpenCode Go subscription limits.

    The CLI itself only learns about limits reactively, from the error body of a
    refused request. The console's usage endpoint reports them up front, so that
    is what this polls.
    """

    id = "opencode"
    display_name = "OpenCode"
    process_specs = [
        ProcessSpec(names=frozenset({"opencode"}), label="session"),
    ]

    def _read_key(self) -> str:
        env_key = os.environ.get("OPENCODE_API_KEY", "").strip()
        if env_key:
            return env_key
        path = _auth_path()
        if not path.exists():
            raise OpenCodeAuthError("Sign in to OpenCode")
        try:
            auth = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise OpenCodeAuthError(f"Could not read OpenCode login: {exc}") from exc
        key = (auth.get(AUTH_KEY) or {}).get("key")
        if not key:
            raise OpenCodeAuthError("No OpenCode Go subscription found")
        return str(key)

    def available(self) -> bool:
        try:
            self._read_key()
        except OpenCodeAuthError:
            return False
        return True

    def fetch(self) -> ProviderSnapshot:
        try:
            key = self._read_key()
        except OpenCodeAuthError as exc:
            return self._auth_snapshot(str(exc))

        try:
            payload = self._get_usage(key)
        except PermissionError as exc:
            return self._auth_snapshot(str(exc))

        usage = payload.get("usage")
        if not isinstance(usage, dict):
            return ProviderSnapshot.error_snapshot(
                provider_id=self.id,
                display_name=self.display_name,
                icon="opencode",
                message="No usage reported",
                dashboard_url=DASHBOARD_URL,
            )

        metrics: list[Meter] = []
        for key_name, label in WINDOWS:
            window = usage.get(key_name)
            if not isinstance(window, dict):
                continue
            percent = window.get("percent")
            if percent is None:
                continue
            metrics.append(
                Meter(key_name, label, float(percent), resets_at=_parse_iso(window.get("resetsAt")))
            )

        if not metrics:
            return ProviderSnapshot.error_snapshot(
                provider_id=self.id,
                display_name=self.display_name,
                icon="opencode",
                message="No limit windows reported",
                dashboard_url=DASHBOARD_URL,
            )

        return ProviderSnapshot(
            provider_id=self.id,
            display_name=self.display_name,
            icon="opencode",
            plan="Go",
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
            icon="opencode",
            message=message,
            auth_needed=True,
            dashboard_url=DASHBOARD_URL,
        )

    def _get_usage(self, api_key: str) -> dict[str, Any]:
        request = urllib.request.Request(
            USAGE_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "cursor-spend-monitor",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            if exc.code in {401, 403}:
                raise PermissionError("OpenCode key rejected — sign in again") from exc
            detail = exc.read().decode("utf-8", errors="replace")[:200]
            raise RuntimeError(f"HTTP {exc.code} from OpenCode usage: {detail}") from exc

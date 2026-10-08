from __future__ import annotations

import http.client
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..instances import ProcessSpec
from .base import Meter, ProviderSnapshot

# A host and a path rather than a URL: the fetch below uses `HTTPSConnection`,
# where https is a property of the code and there is no scheme to get wrong.
USAGE_HOST = "opencode.ai"
USAGE_PATH = "/zen/go/v1/usage"


def _as_float(value: Any) -> float | None:
    """The number the API sent, or None.

    A `Meter` is a claim about how much of a limit is used, so a reading that
    will not parse drops the window instead of becoming a zero we invented.
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
DASHBOARD_URL = "https://opencode.ai/console"
AUTH_KEY = "opencode-go"

# Window key → label, in the order they are shown. The API names the short
# window "rolling" without stating its length, so the label does not claim one.
WINDOWS: list[tuple[str, str, str]] = [
    ("rolling", "Rolling limit", "rolling"),
    ("weekly", "Weekly", "weekly"),
    ("monthly", "Monthly", "monthly"),
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
    process_specs = (ProcessSpec(names=frozenset({"opencode"}), label="session"),)

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
        for key_name, label, kind in WINDOWS:
            window = usage.get(key_name)
            if not isinstance(window, dict):
                continue
            percent = _as_float(window.get("percent"))
            if percent is None:
                continue
            metrics.append(
                Meter(
                    key_name, label, percent,
                    resets_at=_parse_iso(window.get("resetsAt")), kind=kind,
                )
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
        """Read the usage endpoint, mapping its failures onto ours."""
        # `HTTPSConnection` rather than `urlopen`: TLS is a property of the code,
        # with no URL to open and no scheme to get wrong. `api.py` does the same,
        # for the same reason. Constructed outside the `try` so the `finally`
        # always has one to close -- it does not connect here, so it cannot fail.
        connection = http.client.HTTPSConnection(USAGE_HOST, timeout=30)
        try:
            connection.request(
                "GET",
                USAGE_PATH,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "cursor-spend-monitor",
                },
            )
            response = connection.getresponse()
            status = int(response.status)
            detail = response.read().decode("utf-8", errors="replace")
        except OSError as exc:
            raise RuntimeError(f"OpenCode usage unreachable: {exc}") from exc
        finally:
            connection.close()

        if status in {401, 403}:
            raise PermissionError("OpenCode key rejected — sign in again")
        if status >= 400:
            raise RuntimeError(f"HTTP {status} from OpenCode usage: {detail[:200]}")
        try:
            return json.loads(detail)
        except ValueError as exc:
            raise RuntimeError("OpenCode usage returned invalid JSON") from exc

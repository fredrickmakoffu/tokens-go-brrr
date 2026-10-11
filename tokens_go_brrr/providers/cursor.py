from __future__ import annotations

from datetime import UTC, datetime

from ..instances import ProcessSpec
from ..local_auth import read_local_auth
from .base import Meter, ProviderSnapshot
from .cursor_api import CursorUsageClient

DASHBOARD_URL = "https://cursor.com/dashboard/spending"


class CursorProvider:
    id = "cursor"
    display_name = "Cursor"
    process_specs = (
        # The terminal agent: launched through a shell wrapper, so argv[0] is the
        # node entry point and the distinguishing part is the install path.
        # worker-server is an internal helper; --print is non-interactive (Task /
        # headless) and is not a terminal session the user is working in.
        ProcessSpec(
            names=frozenset({"agent", "cursor-agent", "node"}),
            require_args=("cursor-agent",),
            exclude_args=("worker-server", "--print"),
            label="agent",
        ),
        # The desktop app. Electron spawns a helper process per window and per
        # service, all carrying --type=, so only the main process is a session.
        ProcessSpec(
            names=frozenset({"cursor"}),
            exclude_args=("--type=",),
            label="editor",
        ),
    )

    def __init__(self) -> None:
        self._client = CursorUsageClient()

    def available(self) -> bool:
        return read_local_auth() is not None

    def fetch(self) -> ProviderSnapshot:
        if not self.available():
            return ProviderSnapshot.error_snapshot(
                provider_id=self.id,
                display_name=self.display_name,
                icon="cursor",
                message="Sign in to Cursor desktop",
                auth_needed=True,
                dashboard_url=DASHBOARD_URL,
            )

        usage = self._client.fetch()
        plan = usage.membership_type.title() if usage.membership_type else None
        resets = usage.billing_cycle_end
        metrics: list[Meter] = []
        # Drop windows the dashboard did not report — do not invent 0%.
        if usage.auto_percent is not None:
            metrics.append(
                Meter(
                    "monthly",
                    "Monthly limit",
                    usage.auto_percent,
                    resets_at=resets,
                    kind="monthly",
                )
            )
        if usage.api_percent is not None:
            metrics.append(
                Meter(
                    "other",
                    "Other models",
                    usage.api_percent,
                    resets_at=resets,
                    kind="other",
                )
            )
        if not metrics:
            return ProviderSnapshot.error_snapshot(
                provider_id=self.id,
                display_name=self.display_name,
                icon="cursor",
                message="No usage reported",
                dashboard_url=DASHBOARD_URL,
            )
        return ProviderSnapshot(
            provider_id=self.id,
            display_name=self.display_name,
            icon="cursor",
            plan=plan,
            metrics=metrics,
            primary_key=metrics[0].key,
            dashboard_url=DASHBOARD_URL,
            status="ok",
            error=None,
            fetched_at=datetime.now(UTC),
        )

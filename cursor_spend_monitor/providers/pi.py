from __future__ import annotations

from datetime import datetime, timezone

from ..instances import ProcessSpec
from . import pi_backend
from .base import ProviderSnapshot

DASHBOARD_URL = "https://pi.dev"


class PiProvider:
    """Pi, a harness with no subscription of its own.

    Every other provider here owns the account it reports on. Pi does not: it
    spends against whichever LLM account the session selected, which today is
    OpenCode Go, Codex, xAI or a custom endpoint such as Cline. So this provider
    ships no meters. It reports which account its live sessions are on, and the daemon
    borrows that account's meters when one of our own providers already polls it
    (see `daemon._apply_borrowing`).

    When the account is one we cannot meter — xAI publishes no usage endpoint,
    and Cline reports a credit balance rather than a window — the row still
    appears with its sessions and names the account, because a session you are
    running is worth showing whether or not its limit is knowable.
    """

    id = "pi"
    display_name = "Pi"
    process_specs = (
        ProcessSpec(
            names=frozenset({"pi"}),
            label="session",
            resolve_backend=pi_backend.BackendResolver(),
        ),
    )

    def available(self) -> bool:
        return pi_backend.installed()

    def fetch(self) -> ProviderSnapshot:
        if not pi_backend.installed():
            return ProviderSnapshot.error_snapshot(
                provider_id=self.id,
                display_name=self.display_name,
                icon="pi",
                message="Pi is not installed",
                dashboard_url=DASHBOARD_URL,
            )

        # There is nothing to poll. The snapshot is a shell that the daemon fills
        # from the live sessions' backend and from that backend's own provider.
        return ProviderSnapshot(
            provider_id=self.id,
            display_name=self.display_name,
            icon="pi",
            plan=None,
            metrics=[],
            primary_key="",
            dashboard_url=DASHBOARD_URL,
            status="ok",
            error=None,
            fetched_at=datetime.now(timezone.utc),
        )

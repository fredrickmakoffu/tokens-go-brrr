"""Copy meters from a subscribed provider onto a harness row (e.g. Pi)."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from .providers import pi_backend
from .providers.base import ProviderSnapshot


def apply_borrowing(
    snapshots: list[ProviderSnapshot],
    *,
    is_harness: Callable[[str], bool],
    primary_overrides: Mapping[str, str],
) -> None:
    """Give a harness the meters of the account its sessions are spending on.

    Mutates ``snapshots`` in place. See ``UsageDaemon._apply_borrowing`` history
    for the three panel outcomes (borrowed / unmeterable / idle).
    """
    by_id = {snap.provider_id: snap for snap in snapshots}
    for snap in snapshots:
        if not is_harness(snap.provider_id):
            continue

        backends = [i.backend for i in snap.instances.all if i.backend is not None]
        backend = pi_backend.dominant(backends)
        snap.backend = backend
        snap.borrowed_from = None
        snap.metrics = []
        snap.primary_key = ""
        snap.plan = backend.model if backend else None

        if backend is None:
            snap.status = "ok"
            snap.error = None
            continue

        source = by_id.get(backend.provider_id) if backend.metered else None
        if source is None or source.status != "ok":
            snap.status = "ok"
            snap.error = (
                f"{backend.name} reports no limits"
                if not backend.metered
                else f"Sign in to {backend.name} to show limits"
            )
            continue

        snap.metrics = list(source.metrics)
        snap.primary_key = source.primary_key
        snap.borrowed_from = source.provider_id
        snap.status = "ok"
        snap.error = None
        override = primary_overrides.get(snap.provider_id)
        if override and override in {m.key for m in snap.metrics}:
            snap.primary_key = override

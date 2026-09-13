from __future__ import annotations

from .base import Meter, Provider, ProviderSnapshot
from .cursor import CursorProvider

PROVIDERS: dict[str, type] = {
    "cursor": CursorProvider,
}


def build_providers(enabled: list[str] | None = None) -> list[Provider]:
    ids = enabled or ["cursor"]
    out: list[Provider] = []
    for provider_id in ids:
        cls = PROVIDERS.get(provider_id)
        if cls is None:
            continue
        out.append(cls())
    return out


__all__ = [
    "Meter",
    "Provider",
    "ProviderSnapshot",
    "CursorProvider",
    "PROVIDERS",
    "build_providers",
]

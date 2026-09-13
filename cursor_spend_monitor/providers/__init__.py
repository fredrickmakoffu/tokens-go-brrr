from __future__ import annotations

from .base import Meter, Provider, ProviderSnapshot
from .claude import ClaudeProvider
from .cursor import CursorProvider

DEFAULT_PROVIDERS = ["cursor", "claude"]

PROVIDERS: dict[str, type] = {
    "cursor": CursorProvider,
    "claude": ClaudeProvider,
}


def build_providers(enabled: list[str] | None = None) -> list[Provider]:
    ids = enabled or DEFAULT_PROVIDERS
    out: list[Provider] = []
    for provider_id in ids:
        cls = PROVIDERS.get(provider_id)
        if cls is None:
            continue
        out.append(cls())
    return out


__all__ = [
    "Meter",
    "ClaudeProvider",
    "DEFAULT_PROVIDERS",
    "Provider",
    "ProviderSnapshot",
    "CursorProvider",
    "PROVIDERS",
    "build_providers",
]

from __future__ import annotations

from .base import Meter, Provider, ProviderSnapshot
from .claude import ClaudeProvider
from .codex import CodexProvider
from .cursor import CursorProvider
from .opencode import OpenCodeProvider
from .pi import PiProvider

DEFAULT_PROVIDERS = ["cursor", "claude", "opencode", "pi", "codex"]

PROVIDERS: dict[str, type] = {
    "cursor": CursorProvider,
    "claude": ClaudeProvider,
    "codex": CodexProvider,
    "opencode": OpenCodeProvider,
    "pi": PiProvider,
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
    "CodexProvider",
    "OpenCodeProvider",
    "PiProvider",
    "DEFAULT_PROVIDERS",
    "Provider",
    "ProviderSnapshot",
    "CursorProvider",
    "PROVIDERS",
    "build_providers",
]

"""Compose a notification with a language model, when that is worth doing.

The templates are the product; this is the upgrade. Every trigger already
produces a correct sentence with no model in the loop, so this module is allowed
to fail — a refused request, a missing credential, a provider with too little
capacity — and the caller simply keeps the template. That is why nothing here
raises into the daemon.

Three jobs:

* **Choose the writer.** The provider with the most *short-window* headroom
  (rolling, then weekly) writes the message. Using the provider that is itself
  nearly spent to warn about a nearly-spent provider is the failure this avoids.
  Monthly-only providers are a tiebreak at best, and the provider that triggered
  the message is excluded outright.
* **Ask for the wording — and for which AI it is about.** The reply carries a
  `FEATURED:` line naming a provider from the ranked list we send. Without it the
  panel would badge whichever provider the ledger ranked first while the prose
  talked about someone else.
* **Read credentials without ever writing them.** Claude's token and OpenCode's
  key are opened read-only. Rotating a refresh token here is the bug class that
  signs the user out of their own CLI, and it is not worth the convenience.

Only the numbers travel. No transcript text, no prompt history, no file
contents — a ledger digest or a meter reading, and nothing else.
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import llm_log
from .coerce import as_float as _as_float
from .coerce import as_int as _as_int
from .http_json import HttpJsonError, request_json
from .notify_engine import SOURCE_LLM, Message, provider_label

# Endpoints, one per generator we can actually authenticate to. Hosts are
# separate from paths so a connection is https by construction rather than a URL
# that has to be validated.
ENDPOINTS: dict[str, tuple[str, str]] = {
    "claude": ("api.anthropic.com", "/v1/messages"),
    "opencode": ("opencode.ai", "/zen/v1/chat/completions"),
}

# The cheap end of each provider, overridable with `llm_generator_model`. These
# are a cost decision, not a value judgement about the user's usage, so they are
# the one thing here that is a constant. A wrong id is not fatal: the provider
# answers with an error and the caller keeps the template.
DEFAULT_MODELS: dict[str, str] = {
    "claude": "claude-haiku-4-5",
    "opencode": "deepseek-v4-flash",
}

GENERATOR_POOL = tuple(ENDPOINTS)

ANTHROPIC_VERSION = "2023-06-01"
OAUTH_BETA = "oauth-2025-04-20"

# A short window with less room than this is not a candidate writer.
MIN_SHORT_HEADROOM_FLOOR = 15

SHARE_LIMIT = 200


class LlmError(RuntimeError):
    """The generator could not be reached, or refused. Never fatal."""


class LlmRateLimited(LlmError):
    """The generator said 429. The caller falls back rather than retrying hard."""


@dataclass(frozen=True)
class Generator:
    """A provider that can write the message, and why it was chosen."""

    provider_id: str
    name: str
    model: str
    short_headroom: int
    monthly_headroom: int | None
    reason: str


# -- choosing the writer -----------------------------------------------------


def _short_headroom(snapshot: Any) -> int | None:
    """The tightest rolling/weekly window, as percent remaining.

    The tightest one decides: a provider with 80% left on its weekly and 5% on
    its rolling window cannot write anything.
    """
    values = [
        max(0.0, 100.0 - _as_float(meter.percent))
        for meter in snapshot.metrics
        if meter.kind in ("rolling", "weekly")
    ]
    return _as_int(min(values)) if values else None


def _monthly_headroom(snapshot: Any) -> int | None:
    values = [
        max(0.0, 100.0 - _as_float(meter.percent))
        for meter in snapshot.metrics
        if meter.kind == "monthly"
    ]
    return _as_int(min(values)) if values else None


def candidates(
    snapshots: list[Any], *, trigger: str = "", model_for: Any = None
) -> list[Generator]:
    """Every provider that could write, best capacity first.

    Ranked by short-window headroom, then by how many windows are healthy, then
    by monthly headroom. A provider with only a monthly meter still appears, at
    the bottom: it is a usable writer of last resort, never a preferred one.
    """
    found: list[Generator] = []
    for snapshot in snapshots:
        provider_id = getattr(snapshot, "provider_id", "")
        if provider_id not in GENERATOR_POOL or provider_id == trigger:
            continue
        if getattr(snapshot, "status", "") != "ok":
            continue
        if getattr(snapshot, "borrowed_from", None) is not None:
            continue
        if not getattr(snapshot, "metrics", None):
            continue
        short = _short_headroom(snapshot)
        monthly = _monthly_headroom(snapshot)
        if short is None and monthly is None:
            continue
        found.append(
            Generator(
                provider_id=provider_id,
                name=str(getattr(snapshot, "display_name", provider_id)),
                model="",
                short_headroom=short if short is not None else 0,
                monthly_headroom=monthly,
                reason=(
                    f"{short}% left in the tightest window"
                    if short is not None
                    else f"monthly only, {monthly}% left"
                ),
            )
        )

    # Sorted here rather than by the caller so the ordering rule lives in one
    # place and can be argued with in a test.
    found.sort(
        key=lambda g: (
            g.short_headroom,
            _healthy_windows(snapshots, g.provider_id),
            g.monthly_headroom or 0,
        ),
        reverse=True,
    )
    if model_for is not None:
        found = [
            Generator(
                provider_id=g.provider_id,
                name=g.name,
                model=model_for(g.provider_id),
                short_headroom=g.short_headroom,
                monthly_headroom=g.monthly_headroom,
                reason=g.reason,
            )
            for g in found
        ]
    return found


def _healthy_windows(snapshots: list[Any], provider_id: str) -> int:
    for snapshot in snapshots:
        if getattr(snapshot, "provider_id", "") != provider_id:
            continue
        return sum(
            1
            for meter in snapshot.metrics
            if meter.kind in ("rolling", "weekly") and (100.0 - _as_float(meter.percent)) >= 50
        )
    return 0


def choose(
    snapshots: list[Any],
    *,
    trigger: str = "",
    floor: int = MIN_SHORT_HEADROOM_FLOOR,
    model: str = "",
    provider: str = "",
) -> Generator | None:
    """The provider that should write, or None when none should.

    `floor` is the point below which writing costs more than it is worth: the
    message is usually about capacity, and spending capacity to warn about
    missing capacity is the joke this avoids. A floor of zero still requires
    *some* room, because a spent provider cannot write anything.
    """
    effective_floor = max(1, floor)
    for candidate in candidates(snapshots, trigger=trigger):
        if candidate.short_headroom < effective_floor:
            continue
        if provider and candidate.provider_id != provider:
            continue
        chosen_model = model or DEFAULT_MODELS.get(candidate.provider_id, "")
        if not chosen_model:
            continue
        return Generator(
            provider_id=candidate.provider_id,
            name=candidate.name,
            model=chosen_model,
            short_headroom=candidate.short_headroom,
            monthly_headroom=candidate.monthly_headroom,
            reason=candidate.reason,
        )
    return None


# -- the prompt --------------------------------------------------------------

PROMPT_RULES = """\
You write one short notification for a developer about their own AI coding usage.
The notification is shown in a desktop panel.

Rules:
- At most 3 sentences. No preamble, no markdown, no headings.
- Use only the figures in FACTS. Never invent, round up, or estimate a number.
- Speak about the developer's own work in the second person. Be specific and
  plain; this comes from their own tool, not from a report.
- If KIND is actionable, end with one concrete thing to do.

Then, on their own lines at the very end:
SHARE: one line of at most 200 characters suitable for posting publicly, or
       omit this line entirely if nothing here is worth sharing.
FEATURED: exactly one provider id, copied from the ids in RANKED.\
"""


def build_prompt(message: Message, facts: dict[str, Any]) -> str:
    """The whole instruction, numbers only, plus what to send back."""
    ranked = [
        {
            "id": row.get("provider"),
            "tokens": row.get("tokens"),
            "sessions": row.get("sessions"),
            "cost_usd": row.get("cost_usd"),
        }
        for row in (facts.get("ranked") or [])
        if row.get("provider")
    ]
    return "\n\n".join(
        [
            PROMPT_RULES,
            f"KIND: {message.kind}",
            f"FACTS:\n{json.dumps(facts, indent=2, default=str)}",
            "RANKED (choose FEATURED from these ids):\n"
            + (json.dumps(ranked, indent=2, default=str) if ranked else "[]"),
            f"DRAFT to rewrite, keeping its numbers:\n{message.body}",
        ]
    )


def parse_reply(text: str) -> tuple[str, str, str]:
    """Split a reply into (body, share, featured provider id).

    Anything after the first `SHARE:` or `FEATURED:` line is not part of the
    message, so a model that adds a trailing note cannot leak it into the panel.
    """
    body_lines: list[str] = []
    share = ""
    featured = ""
    seen_marker = False
    for line in str(text or "").splitlines():
        stripped = line.strip()
        upper = stripped.upper()
        if upper.startswith("SHARE:"):
            seen_marker = True
            piece = stripped.split(":", 1)[1].strip()
            if piece:
                share = piece
                if not share.upper().startswith("SHARE:"):
                    share = f"SHARE: {share}"
                share = share[:SHARE_LIMIT]
            continue
        if upper.startswith("FEATURED:"):
            seen_marker = True
            featured = stripped.split(":", 1)[1].strip().lower()
            continue
        if seen_marker:
            # Whatever follows the markers is the model talking to us, not to
            # the developer. It never reaches the panel.
            continue
        body_lines.append(line)
    return "\n".join(body_lines).strip(), share, featured


def known_provider_ids(facts: dict[str, Any]) -> set[str]:
    """The ids the model was allowed to pick from."""
    return {str(row.get("provider")) for row in (facts.get("ranked") or []) if row.get("provider")}


# -- talking to a provider ---------------------------------------------------


def _post_json(
    host: str,
    path: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    *,
    timeout: int,
) -> dict[str, Any]:
    """POST over a connection that is TLS by construction."""
    try:
        return request_json(
            "POST",
            host,
            path,
            body=payload,
            headers=headers,
            timeout=timeout,
        )
    except OSError as exc:
        raise LlmError(f"{host} unreachable: {exc}") from exc
    except HttpJsonError as exc:
        if exc.status == 429:
            raise LlmRateLimited(f"{host} rate limited") from exc
        raise LlmError(f"HTTP {exc.status} from {host}: {exc.body[:200]}") from exc
    except RuntimeError as exc:
        raise LlmError(str(exc)) from exc


def _claude_token() -> str:
    """Claude Code's OAuth token, read and never written."""
    path = Path(
        os.environ.get("CLAUDE_CREDENTIALS_FILE", Path.home() / ".claude" / ".credentials.json")
    )
    try:
        creds = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise LlmError(f"no usable Claude login: {exc}") from exc
    token = (creds.get("claudeAiOauth") or {}).get("accessToken")
    if not token:
        raise LlmError("no usable Claude login")
    return str(token)


def _opencode_key() -> str:
    """OpenCode's Zen key, read and never written."""
    data_home = os.environ.get("XDG_DATA_HOME")
    base = Path(data_home) if data_home else Path.home() / ".local" / "share"
    path = base / "opencode" / "auth.json"
    try:
        auth = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise LlmError(f"no usable OpenCode login: {exc}") from exc
    key = (auth.get("opencode-go") or {}).get("key")
    if not key:
        raise LlmError("no usable OpenCode login")
    return str(key)


def _text_of_anthropic(payload: dict[str, Any]) -> str:
    blocks = payload.get("content")
    if not isinstance(blocks, list):
        return ""
    return "".join(
        str(block.get("text", ""))
        for block in blocks
        if isinstance(block, dict) and block.get("type") == "text"
    )


def _text_of_openai(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0] if isinstance(choices[0], dict) else {}
    message = first.get("message")
    if not isinstance(message, dict):
        return ""
    return str(message.get("content") or "")


def _usage_of(payload: dict[str, Any], provider_id: str) -> dict[str, int]:
    """Token counts from a provider's usage block, or an empty dict."""
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return {}
    if provider_id == "claude":
        tin, tout = usage.get("input_tokens"), usage.get("output_tokens")
    else:
        tin, tout = usage.get("prompt_tokens"), usage.get("completion_tokens")
    found: dict[str, int] = {}
    if tin is not None:
        found["tokens_in"] = _as_int(tin)
    if tout is not None:
        found["tokens_out"] = _as_int(tout)
    return found


def _complete(
    generator: Generator, prompt: str, *, max_tokens: int, timeout: int
) -> tuple[str, dict[str, int]]:
    """One request, returning the reply text and the provider's token counts."""
    endpoint = ENDPOINTS.get(generator.provider_id)
    if endpoint is None:
        raise LlmError(f"{generator.provider_id} is not a generator")
    host, path = endpoint
    payload = {
        "model": generator.model,
        "max_tokens": max(16, _as_int(max_tokens)),
        "temperature": 0.4,
        "messages": [{"role": "user", "content": prompt}],
    }

    if generator.provider_id == "claude":
        response = _post_json(
            host,
            path,
            payload,
            {
                "authorization": f"Bearer {_claude_token()}",
                "anthropic-version": ANTHROPIC_VERSION,
                "anthropic-beta": OAUTH_BETA,
            },
            timeout=timeout,
        )
        return _text_of_anthropic(response), _usage_of(response, "claude")

    response = _post_json(
        host,
        path,
        payload,
        {"authorization": f"Bearer {_opencode_key()}"},
        timeout=timeout,
    )
    return _text_of_openai(response), _usage_of(response, generator.provider_id)


def _outcome_of(exc: LlmError) -> str:
    if isinstance(exc, LlmRateLimited):
        return llm_log.RATE_LIMITED
    return llm_log.TIMEOUT if "timed out" in str(exc) else llm_log.ERROR


def generate(
    generator: Generator,
    prompt: str,
    *,
    max_tokens: int = 200,
    timeout: int = 30,
    recorder: Callable[[dict[str, Any]], None] | None = None,
    context: dict[str, Any] | None = None,
) -> str:
    """Ask the chosen provider for the wording. Raises `LlmError` on refusal.

    `recorder`, when given, is handed one entry per call -- successful or not --
    for the LLM log. It is best-effort: a recorder that raises must not turn a
    good reply into a failure, so its errors stop here. `context` is merged in
    (why the call ran, which message it was for).
    """
    started = time.monotonic()

    def record(outcome: str, **extra: Any) -> None:
        if recorder is None:
            return
        try:
            recorder(
                {
                    **(context or {}),
                    "provider": generator.provider_id,
                    "model": generator.model,
                    "outcome": outcome,
                    "latency_ms": int((time.monotonic() - started) * 1000),
                    "prompt": prompt,
                    **extra,
                }
            )
        except Exception as exc:  # noqa: BLE001 -- see the docstring
            print(f"LLM log recorder failed: {exc}", file=sys.stderr, flush=True)

    try:
        text, usage = _complete(generator, prompt, max_tokens=max_tokens, timeout=timeout)
    except LlmError as exc:
        record(_outcome_of(exc), error=f"{type(exc).__name__}: {exc}")
        raise
    record(llm_log.OK, reply=text, **usage)
    return text


def rewrite(
    message: Message,
    *,
    generator: Generator,
    facts: dict[str, Any],
    max_tokens: int = 200,
    timeout: int = 30,
    recorder: Callable[[dict[str, Any]], None] | None = None,
    context: dict[str, Any] | None = None,
) -> Message | None:
    """The message in the model's words, or None to keep the template.

    `featured` is only accepted when the model names a provider it was actually
    offered. Anything else falls back to whatever the template derived, because
    a badge pointing at the wrong AI is worse than no rewrite at all.
    """
    try:
        reply = generate(
            generator,
            build_prompt(message, facts),
            max_tokens=max_tokens,
            timeout=timeout,
            recorder=recorder,
            context={
                "message_kind": message.kind,
                "message_key": message.key,
                **(context or {}),
            },
        )
    except LlmError:
        return None

    body, share, featured = parse_reply(reply)
    if not body:
        return None

    allowed = known_provider_ids(facts)
    provider = featured if featured in allowed else message.provider
    meta = dict(message.meta)
    meta["composed_by"] = generator.provider_id
    # The wording is the model's now; the figures were still the ledger's.
    meta["source"] = SOURCE_LLM
    if provider:
        meta["providerName"] = provider_label(provider)
    return Message(
        kind=message.kind,
        key=message.key,
        body=body,
        share=share or message.share,
        provider=provider or message.provider,
        meta=meta,
    )


__all__ = [
    "ANTHROPIC_VERSION",
    "DEFAULT_MODELS",
    "ENDPOINTS",
    "GENERATOR_POOL",
    "Generator",
    "LlmError",
    "LlmRateLimited",
    "OAUTH_BETA",
    "SHARE_LIMIT",
    "build_prompt",
    "candidates",
    "choose",
    "generate",
    "known_provider_ids",
    "parse_reply",
    "rewrite",
]

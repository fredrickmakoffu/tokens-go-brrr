"""Turn the ledger into messages a person would actually want to read.

Package layout (seams for further extraction):

* ``shared`` — Message, constants, coercion helpers
* ``digest`` — scheduled digests and fun/share lines
* ``insights`` — cold-note insight candidates
* ``live_notes`` — cold / warm note builders
* ``events`` — meter event messages
* ``billboard`` — landing-page selection
* ``core`` — full implementation (imported by facades)
"""

from __future__ import annotations

from .core import *  # noqa: F403
from .core import (  # noqa: F401 — explicit for type checkers / star-import clarity
    ACTIONABLE,
    COLD,
    DEFAULT_COOLDOWN_SECONDS,
    FUN,
    HOT,
    INFORMATIVE,
    PRIORITY,
    SHAREABLE,
    SOURCE_LLM,
    SOURCE_TEMPLATE,
    WARM,
    Message,
    billboard_payload,
    choose_billboard,
    cold_note,
    daily_digest,
    due,
    event_messages,
    expires_at_for,
    featured_provider,
    fingerprint_of,
    fun_fact,
    has_pending_insight,
    keep,
    monthly_digest,
    next_insight,
    provenance,
    provider_label,
    scheduled_messages,
    share_line,
    tier_for,
    warm_note,
    weekly_digest,
)

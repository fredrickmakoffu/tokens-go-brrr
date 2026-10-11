"""A sliding-window cap on model calls made because the panel was opened.

Scheduled digests are bounded by the clock; a call made on open is bounded only
by how often the person looks, so it needs its own ceiling. The design's default
is a few an hour and a couple of dozen a day: enough that a working day gets
fresh wording, few enough that the panel can never become a meaningful drain on
the quota it exists to protect.

Held in memory. A restart forgives the count, which is acceptable: it can raise
the day's total by one window's worth, once, and keeping a durable counter would
mean a second store to keep in step with the LLM log, which can be switched off.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable

HOUR = 3600
DAY = 24 * HOUR

OVER_HOUR = "over_hour_cap"
OVER_DAY = "over_day_cap"


class CallBudget:
    """At most `per_hour` calls in any hour and `per_day` in any day."""

    def __init__(
        self,
        per_hour: int,
        per_day: int,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.per_hour = max(0, int(per_hour))
        self.per_day = max(0, int(per_day))
        self._clock = clock
        self._stamps: deque[float] = deque()
        self._lock = threading.Lock()

    def _trim(self, now: float) -> None:
        while self._stamps and now - self._stamps[0] >= DAY:
            self._stamps.popleft()

    def refusal(self) -> str | None:
        """Why a call may not be made now, or None when it may."""
        now = self._clock()
        with self._lock:
            self._trim(now)
            if len(self._stamps) >= self.per_day:
                return OVER_DAY
            in_hour = sum(1 for stamp in self._stamps if now - stamp < HOUR)
            if in_hour >= self.per_hour:
                return OVER_HOUR
        return None

    def spend(self) -> None:
        """Count a call. Failed calls count too: they used the same request."""
        now = self._clock()
        with self._lock:
            self._trim(now)
            self._stamps.append(now)


__all__ = ["CallBudget", "OVER_DAY", "OVER_HOUR"]

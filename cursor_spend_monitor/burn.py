"""Turn a series of samples into "how long until this meter is spent".

A percentage answers where you are. What decides whether to start a two-hour
agent run is where you will be, and at what time the window stops you.

The fit is deliberately conservative. It would be easy to always produce a
number, and a confident wrong estimate here is worse than none: someone reads
"4h left", starts the run, and is cut off in twenty minutes. Every guard below
exists to return None instead of guessing.
"""

from __future__ import annotations

# Two points always fit a line perfectly, which says nothing about a trend.
MIN_SAMPLES = 3

# A window whose samples span less than this has not been watched long enough
# for the slope to mean anything, however many samples landed in it.
MIN_SPAN_SECONDS = 300

# Usage is bursty — idle stretches then a flurry — so the fit is never going to
# be tight. This rejects the series that are pure noise, not the merely rough.
MIN_R_SQUARED = 0.5


def eta_seconds(
    samples: list[tuple[float, float]], *, target: float = 100.0
) -> float | None:
    """Seconds until the meter reaches `target`, or None if it cannot be said.

    None means "not enough to go on": too few samples, too short a span, usage
    that is flat or falling, or a spread the line does not explain.
    """
    if len(samples) < MIN_SAMPLES:
        return None

    times = [t for t, _ in samples]
    percents = [p for _, p in samples]
    span = times[-1] - times[0]
    if span < MIN_SPAN_SECONDS:
        return None

    slope, intercept = _least_squares(times, percents)
    if slope is None or slope <= 0:
        # Flat or falling: nothing is being spent, so nothing runs out.
        return None

    if _r_squared(times, percents, slope, intercept) < MIN_R_SQUARED:
        return None

    remaining = target - percents[-1]
    if remaining <= 0:
        return 0.0
    return remaining / slope


def eta_label(seconds: float | None) -> str:
    """Short human form for a status line: 45m, 3h 10m, 2 days."""
    if seconds is None:
        return ""
    secs = int(seconds)
    if secs <= 60:
        return "<1m"
    minutes = secs // 60
    if minutes < 60:
        return f"{minutes}m"
    hours, mins = divmod(minutes, 60)
    if hours >= 48:
        return f"{hours // 24} days"
    if mins:
        return f"{hours}h {mins}m"
    return f"{hours}h"


def _least_squares(xs: list[float], ys: list[float]) -> tuple[float | None, float]:
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    variance = sum((x - mean_x) ** 2 for x in xs)
    if variance == 0:
        return None, mean_y
    covariance = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    slope = covariance / variance
    return slope, mean_y - slope * mean_x


def _r_squared(
    xs: list[float], ys: list[float], slope: float, intercept: float
) -> float:
    mean_y = sum(ys) / len(ys)
    ss_tot = sum((y - mean_y) ** 2 for y in ys)
    if ss_tot == 0:
        return 0.0
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
    return 1 - ss_res / ss_tot

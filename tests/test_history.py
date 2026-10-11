"""Tests for the sample store and the burn-rate fit built on it."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from tokens_go_brrr import burn, history
from tokens_go_brrr.providers.base import Meter, ProviderSnapshot

NOW = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)
RESET = NOW + timedelta(hours=3)


def snapshot(
    provider_id: str = "claude",
    *,
    percent: float = 40.0,
    status: str = "ok",
    borrowed: str | None = None,
    resets_at: datetime | None = RESET,
) -> ProviderSnapshot:
    return ProviderSnapshot(
        provider_id=provider_id,
        display_name=provider_id.title(),
        icon=provider_id,
        plan=None,
        metrics=[
            Meter("five_hour", "5-hour limit", percent, resets_at=resets_at),
            Meter("seven_day", "Weekly", 10.0, resets_at=resets_at),
        ],
        primary_key="five_hour",
        status=status,
        borrowed_from=borrowed,
    )


class SampleStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.con = history.connect(Path(self._dir.name) / "history.db")
        self.addCleanup(self.con.close)

    def rows(self) -> list[tuple]:
        return self.con.execute(
            "SELECT provider, metric, percent FROM samples ORDER BY provider, metric"
        ).fetchall()

    def test_one_row_per_meter(self):
        self.assertEqual(history.record(self.con, [snapshot()], at=NOW), 2)
        self.assertEqual(len(self.rows()), 2)

    def test_a_provider_that_is_not_ok_is_not_recorded(self):
        history.record(self.con, [snapshot(status="auth_needed")], at=NOW)
        self.assertEqual(self.rows(), [])

    def test_a_borrowed_row_is_not_recorded_twice(self):
        # Pi's meters are OpenCode's; storing both would double-weight every
        # sample of that one subscription in any later fit.
        snaps = [snapshot("opencode"), snapshot("pi", borrowed="opencode")]
        history.record(self.con, snaps, at=NOW)
        self.assertEqual({r[0] for r in self.rows()}, {"opencode"})

    def test_placeholder_meters_are_skipped(self):
        snap = snapshot()
        snap.metrics = [Meter("—", "—", 0.0)]
        history.record(self.con, [snap], at=NOW)
        self.assertEqual(self.rows(), [])

    def add(self, percent: float, minutes: int, resets_at: datetime | None = RESET) -> None:
        history.record(
            self.con,
            [snapshot(percent=percent, resets_at=resets_at)],
            at=NOW + timedelta(minutes=minutes),
        )

    def samples(self) -> list[float]:
        return [p for _, p in history.window_samples(self.con, "claude", "five_hour")]

    def test_samples_come_back_oldest_first(self):
        for offset, pct in enumerate([10.0, 20.0, 30.0]):
            self.add(pct, offset * 5)
        self.assertEqual(self.samples(), [10.0, 20.0, 30.0])

    def test_a_rollover_cuts_the_series(self):
        # The meter only climbs within a window, so a lower reading after a
        # higher one is the window having reset in between.
        for pct, minutes in [(70.0, 0), (85.0, 5), (5.0, 10), (12.0, 15)]:
            self.add(pct, minutes)
        self.assertEqual(self.samples(), [5.0, 12.0])

    def test_a_jittering_reset_time_is_still_one_window(self):
        # Claude reports the same reset with microsecond jitter. Keying on it
        # turned a continuous series into a pile of one-sample groups.
        for offset, pct in enumerate([10.0, 20.0, 30.0]):
            jittered = RESET + timedelta(microseconds=offset * 271_828)
            self.add(pct, offset * 5, resets_at=jittered)
        self.assertEqual(self.samples(), [10.0, 20.0, 30.0])

    def test_a_rolling_window_is_still_one_window(self):
        # OpenCode's rolling reset slides forward on every poll by design.
        for offset, pct in enumerate([10.0, 20.0, 30.0]):
            sliding = RESET + timedelta(minutes=offset * 5)
            self.add(pct, offset * 5, resets_at=sliding)
        self.assertEqual(self.samples(), [10.0, 20.0, 30.0])

    def test_a_long_gap_cuts_the_series(self):
        # The daemon was off, or the machine slept; the line across that says
        # nothing about the rate.
        self.add(10.0, 0)
        self.add(20.0, 5)
        self.add(30.0, 5 + 120)
        self.assertEqual(self.samples(), [30.0])

    def test_small_noise_does_not_look_like_a_rollover(self):
        for pct, minutes in [(30.0, 0), (29.8, 5), (31.0, 10)]:
            self.add(pct, minutes)
        self.assertEqual(len(self.samples()), 3)

    def test_prune_drops_only_what_is_past_retention(self):
        history.record(self.con, [snapshot()], at=datetime.now(timezone.utc))
        old = datetime.now(timezone.utc) - timedelta(days=120)
        history.record(self.con, [snapshot()], at=old)
        self.assertEqual(history.prune(self.con, keep_days=90), 2)
        self.assertEqual(len(self.rows()), 2)

    def test_prune_is_a_no_op_when_retention_is_off(self):
        history.record(self.con, [snapshot()], at=NOW)
        self.assertEqual(history.prune(self.con, keep_days=0), 0)


class RecorderTest(unittest.TestCase):
    """Storage trouble disables history; it never stops the daemon."""

    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.path = Path(self._dir.name) / "history.db"

    def test_records_through_the_wrapper(self):
        recorder = history.Recorder(self.path)
        self.addCleanup(recorder.close)
        self.assertEqual(recorder.record([snapshot()], at=NOW), 2)
        self.assertTrue(recorder.active)

    def test_an_unopenable_database_disables_recording_quietly(self):
        with (
            mock.patch.object(history, "connect", side_effect=sqlite3.Error("locked")),
            mock.patch("sys.stderr"),
        ):
            recorder = history.Recorder(self.path)
        self.assertFalse(recorder.active)
        self.assertEqual(recorder.record([snapshot()], at=NOW), 0)
        self.assertEqual(recorder.window_samples("claude", "five_hour"), [])

    def test_a_write_failure_disables_rather_than_raises(self):
        recorder = history.Recorder(self.path)
        self.addCleanup(recorder.close)
        with (
            mock.patch.object(history, "record", side_effect=sqlite3.Error("disk full")),
            mock.patch("sys.stderr"),
        ):
            self.assertEqual(recorder.record([snapshot()], at=NOW), 0)
        self.assertFalse(recorder.active)


def series(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """(minutes, percent) → (unix seconds, percent)."""
    base = NOW.timestamp()
    return [(base + minutes * 60, pct) for minutes, pct in points]


class BurnRateTest(unittest.TestCase):
    """The fit returns None rather than guess; a wrong ETA is worse than none."""

    def test_a_steady_climb_projects_the_remaining_percent(self):
        # 10% per 10 minutes, now at 40 → 60 left → 60 minutes.
        samples = series([(0, 10), (10, 20), (20, 30), (30, 40)])
        self.assertAlmostEqual(burn.eta_seconds(samples), 3600, delta=1)

    def test_too_few_samples_says_nothing(self):
        self.assertIsNone(burn.eta_seconds(series([(0, 10), (30, 40)])))

    def test_too_short_a_span_says_nothing(self):
        # Three samples a minute apart is a burst, not a trend.
        self.assertIsNone(burn.eta_seconds(series([(0, 10), (1, 20), (2, 30)])))

    def test_flat_usage_never_runs_out(self):
        self.assertIsNone(burn.eta_seconds(series([(0, 40), (10, 40), (20, 40), (30, 40)])))

    def test_a_falling_meter_never_runs_out(self):
        self.assertIsNone(burn.eta_seconds(series([(0, 40), (10, 30), (20, 20), (30, 10)])))

    def test_noise_the_line_does_not_explain_is_rejected(self):
        samples = series([(0, 10), (10, 80), (20, 15), (30, 70), (40, 20)])
        self.assertIsNone(burn.eta_seconds(samples))

    def test_a_meter_already_at_the_limit_is_spent_now(self):
        samples = series([(0, 70), (10, 80), (20, 90), (30, 100)])
        self.assertEqual(burn.eta_seconds(samples), 0.0)

    def test_labels_read_as_durations(self):
        self.assertEqual(burn.eta_label(None), "")
        self.assertEqual(burn.eta_label(30), "<1m")
        self.assertEqual(burn.eta_label(45 * 60), "45m")
        self.assertEqual(burn.eta_label(3 * 3600 + 10 * 60), "3h 10m")
        self.assertEqual(burn.eta_label(5 * 3600), "5h")
        self.assertEqual(burn.eta_label(3 * 86400), "3 days")


class DaemonForecastTest(unittest.TestCase):
    """The daemon attaches ETAs, and withholds ones the window makes moot."""

    def _daemon(self, samples, *, now=NOW):
        from tokens_go_brrr.daemon import UsageDaemon

        stub = mock.Mock()
        stub.history.window_samples.return_value = samples
        with mock.patch("tokens_go_brrr.daemon.datetime") as clock:
            clock.now.return_value = now
            meter = Meter("five_hour", "5-hour limit", 40.0, resets_at=RESET)
            return UsageDaemon._forecast(stub, "claude", meter)

    def test_an_eta_inside_the_window_is_reported(self):
        # 60 minutes to exhaustion, 3 hours until reset.
        eta = self._daemon(series([(0, 10), (10, 20), (20, 30), (30, 40)]))
        self.assertAlmostEqual(eta, 3600, delta=1)

    def test_an_eta_beyond_the_reset_is_withheld(self):
        # 1% per 10 minutes from 40 → 10 hours, but the window rolls over in 3.
        # "in 10h" under a 3h window warns about something that cannot happen.
        samples = series([(0, 37), (10, 38), (20, 39), (30, 40)])
        self.assertIsNone(self._daemon(samples))

    def test_a_meter_with_no_reset_still_gets_an_eta(self):
        from tokens_go_brrr.daemon import UsageDaemon

        stub = mock.Mock()
        stub.history.window_samples.return_value = series(
            [(0, 10), (10, 20), (20, 30), (30, 40)]
        )
        meter = Meter("rolling", "Rolling limit", 40.0, resets_at=None)
        self.assertAlmostEqual(UsageDaemon._forecast(stub, "opencode", meter), 3600, delta=1)


if __name__ == "__main__":
    unittest.main()

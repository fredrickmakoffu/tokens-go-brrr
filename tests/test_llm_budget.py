"""Tests for the cap on model calls made because the panel was opened."""

from __future__ import annotations

import unittest

from cursor_spend_monitor.llm_budget import DAY, HOUR, OVER_DAY, OVER_HOUR, CallBudget


class Clock:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now


class BudgetTest(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = Clock()

    def budget(self, per_hour=4, per_day=24) -> CallBudget:
        return CallBudget(per_hour, per_day, clock=self.clock)

    def test_a_fresh_budget_allows_a_call(self):
        self.assertIsNone(self.budget().refusal())

    def test_the_hourly_cap_refuses_the_next_call(self):
        budget = self.budget(per_hour=2)
        budget.spend()
        budget.spend()
        self.assertEqual(budget.refusal(), OVER_HOUR)

    def test_the_hour_slides_rather_than_resetting_on_the_clock(self):
        budget = self.budget(per_hour=1)
        budget.spend()
        self.clock.now += HOUR - 1
        self.assertEqual(budget.refusal(), OVER_HOUR)
        self.clock.now += 1
        self.assertIsNone(budget.refusal())

    def test_the_daily_cap_outlasts_the_hourly_one(self):
        budget = self.budget(per_hour=10, per_day=3)
        for _ in range(3):
            budget.spend()
            self.clock.now += 2 * HOUR  # each call is out of the hourly window
        self.assertEqual(budget.refusal(), OVER_DAY)
        self.clock.now += DAY
        self.assertIsNone(budget.refusal())

    def test_the_daily_cap_is_reported_before_the_hourly_one(self):
        budget = self.budget(per_hour=1, per_day=1)
        budget.spend()
        self.assertEqual(budget.refusal(), OVER_DAY)

    def test_zero_means_never(self):
        self.assertEqual(self.budget(per_hour=0).refusal(), OVER_HOUR)
        self.assertEqual(self.budget(per_day=0).refusal(), OVER_DAY)

    def test_a_refusal_does_not_spend(self):
        budget = self.budget(per_hour=1)
        budget.spend()
        for _ in range(5):
            self.assertEqual(budget.refusal(), OVER_HOUR)
        self.clock.now += HOUR
        self.assertIsNone(budget.refusal())

    def test_negative_limits_are_treated_as_zero(self):
        self.assertEqual(self.budget(per_hour=-3).per_hour, 0)


if __name__ == "__main__":
    unittest.main()

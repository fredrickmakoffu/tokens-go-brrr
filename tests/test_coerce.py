"""Unit tests for tokens_go_brrr.coerce."""

from __future__ import annotations

import base64
import json
import unittest
from datetime import UTC, datetime

from tokens_go_brrr.coerce import (
    as_float,
    as_float_or_none,
    as_int,
    as_int_or_none,
    jwt_exp,
    parse_iso,
    parse_ms_or_iso,
)


class AsIntTests(unittest.TestCase):
    def test_parses(self) -> None:
        self.assertEqual(as_int("42"), 42)
        self.assertEqual(as_int(3.9), 3)

    def test_default_on_junk(self) -> None:
        self.assertEqual(as_int(None), 0)
        self.assertEqual(as_int("nope", 7), 7)
        self.assertEqual(as_int(float("inf"), -1), -1)

    def test_or_none(self) -> None:
        self.assertIsNone(as_int_or_none(None))
        self.assertIsNone(as_int_or_none(""))
        self.assertIsNone(as_int_or_none("x"))
        self.assertEqual(as_int_or_none("9"), 9)


class AsFloatTests(unittest.TestCase):
    def test_parses_including_zero(self) -> None:
        self.assertEqual(as_float_or_none(0), 0.0)
        self.assertEqual(as_float_or_none("0"), 0.0)
        self.assertEqual(as_float_or_none(12.5), 12.5)

    def test_none_for_unknown_not_zero(self) -> None:
        """Meter policy: unparsable must not become a healthy 0%."""
        self.assertIsNone(as_float_or_none(None))
        self.assertIsNone(as_float_or_none(""))
        self.assertIsNone(as_float_or_none("n/a"))

    def test_default_variant(self) -> None:
        self.assertEqual(as_float(None, 1.5), 1.5)
        self.assertEqual(as_float("bad"), 0.0)


class ParseIsoTests(unittest.TestCase):
    def test_z_suffix(self) -> None:
        stamp = parse_iso("2024-01-02T03:04:05Z")
        assert stamp is not None
        self.assertEqual(stamp.tzinfo, UTC)
        self.assertEqual(stamp.hour, 3)

    def test_naive_gets_utc(self) -> None:
        stamp = parse_iso("2024-01-02T03:04:05")
        assert stamp is not None
        self.assertEqual(stamp.tzinfo, UTC)

    def test_junk(self) -> None:
        self.assertIsNone(parse_iso(None))
        self.assertIsNone(parse_iso(""))
        self.assertIsNone(parse_iso("not-a-date"))


class ParseMsOrIsoTests(unittest.TestCase):
    def test_ms_int_and_digit_string(self) -> None:
        ms = 1_700_000_000_000
        expected = datetime.fromtimestamp(ms / 1000, tz=UTC)
        self.assertEqual(parse_ms_or_iso(ms), expected)
        self.assertEqual(parse_ms_or_iso(str(ms)), expected)

    def test_iso(self) -> None:
        stamp = parse_ms_or_iso("2024-06-01T12:00:00Z")
        assert stamp is not None
        self.assertEqual(stamp.month, 6)


class JwtExpTests(unittest.TestCase):
    def test_reads_exp(self) -> None:
        payload = (
            base64.urlsafe_b64encode(json.dumps({"exp": 1_700_000_000}).encode())
            .decode()
            .rstrip("=")
        )
        token = f"x.{payload}.y"
        self.assertEqual(jwt_exp(token), 1_700_000_000)

    def test_bad_token(self) -> None:
        self.assertIsNone(jwt_exp(""))
        self.assertIsNone(jwt_exp("not-a-jwt"))
        self.assertIsNone(jwt_exp("a.b.c"))


if __name__ == "__main__":
    unittest.main()

"""Tests for the Codex provider: token handling, usage parsing, auth failures."""

from __future__ import annotations

import base64
import email.message
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from tokens_go_brrr.providers import codex
from tokens_go_brrr.providers.codex import CodexProvider


def _jwt(exp: int) -> str:
    """A JWT whose payload carries exp; the signature is never checked."""
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').rstrip(b"=").decode()
    payload = (
        base64.urlsafe_b64encode(json.dumps({"sub": "user", "exp": exp}).encode())
        .rstrip(b"=")
        .decode()
    )
    return f"{header}.{payload}.sig"


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode()

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def usage_payload(**overrides) -> dict:
    payload = {
        "user_id": "u1",
        "account_id": "a1",
        "email": "u@example.com",
        "plan_type": "chatgptplus",
        "rate_limit": {
            "allowed": True,
            "limit_reached": False,
            "primary_window": {
                "used_percent": 42,
                "limit_window_seconds": 2592000,
                "reset_after_seconds": 2592000,
                "reset_at": 1792226711,
            },
            "secondary_window": {
                "used_percent": 12,
                "limit_window_seconds": 18000,
                "reset_after_seconds": 18000,
                "reset_at": 1792226711,
            },
        },
        "credits": {"has_credits": False, "balance": None},
    }
    payload.update(overrides)
    return payload


class ProviderTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        creds = Path(self._tmp.name) / "auth.json"
        self._patch_creds = mock.patch.object(codex, "CREDENTIALS_FILE", creds)
        self._patch_creds.start()
        self._write_auth(auth_mode="chatgpt", token=_jwt(9_999_999_999))
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(self._patch_creds.stop)

    def _write_auth(self, *, auth_mode: str, token: str) -> None:
        codex.CREDENTIALS_FILE.parent.mkdir(parents=True, exist_ok=True)
        codex.CREDENTIALS_FILE.write_text(
            json.dumps(
                {
                    "auth_mode": auth_mode,
                    "tokens": {
                        "access_token": token,
                        "refresh_token": "r",
                        "account_id": "a1",
                    },
                }
            )
        )

    def _stub_usage(self, payload: dict):
        patcher = mock.patch.object(
            codex.urllib.request, "urlopen", return_value=FakeResponse(payload)
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        return patcher

    # --- auth gate ---------------------------------------------------------

    def test_missing_login_is_auth_needed(self) -> None:
        codex.CREDENTIALS_FILE.unlink()
        snapshot = CodexProvider().fetch()
        self.assertEqual(snapshot.status, "auth_needed")
        self.assertEqual(snapshot.error, "Sign in to Codex")

    def test_non_chatgpt_auth_mode_is_auth_needed(self) -> None:
        self._write_auth(auth_mode="api_key", token="api-key-dummy")
        snapshot = CodexProvider().fetch()
        self.assertEqual(snapshot.status, "auth_needed")
        assert snapshot.error is not None
        self.assertIn("ChatGPT account", snapshot.error)

    def test_expired_token_surfaces_auth_needed_without_a_call(self) -> None:
        self._write_auth(auth_mode="chatgpt", token=_jwt(1_000))
        with mock.patch.object(codex.urllib.request, "urlopen") as urlopen:
            snapshot = CodexProvider().fetch()
        urlopen.assert_not_called()
        self.assertEqual(snapshot.status, "auth_needed")
        assert snapshot.error is not None
        self.assertIn("expired", snapshot.error)

    def test_corrupt_login_file_is_auth_needed(self) -> None:
        codex.CREDENTIALS_FILE.write_text("not json")
        snapshot = CodexProvider().fetch()
        self.assertEqual(snapshot.status, "auth_needed")

    # --- usage parsing -----------------------------------------------------

    def test_parses_windows_into_meters(self) -> None:
        self._stub_usage(usage_payload())
        snapshot = CodexProvider().fetch()
        self.assertEqual(snapshot.status, "ok")
        self.assertEqual(snapshot.plan, "ChatGPT Plus")
        self.assertEqual([m.key for m in snapshot.metrics], ["monthly", "window"])
        self.assertEqual(
            [m.label for m in snapshot.metrics], ["Monthly limit", "5-hour limit"]
        )
        self.assertEqual([m.percent for m in snapshot.metrics], [42.0, 12.0])
        self.assertEqual(snapshot.primary_key, "monthly")
        self.assertEqual(snapshot.primary.percent, 42.0)
        resets = snapshot.primary.resets_at
        self.assertIsNotNone(resets)
        self.assertEqual(resets, datetime.fromtimestamp(1792226711, tz=timezone.utc))

    def test_secondary_window_absent_still_yields_primary(self) -> None:
        payload = usage_payload()
        payload["rate_limit"]["secondary_window"] = None
        self._stub_usage(payload)
        snapshot = CodexProvider().fetch()
        self.assertEqual([m.key for m in snapshot.metrics], ["monthly"])

    def test_no_windows_is_an_error_not_a_crash(self) -> None:
        payload = usage_payload()
        payload["rate_limit"]["primary_window"] = None
        payload["rate_limit"]["secondary_window"] = None
        self._stub_usage(payload)
        snapshot = CodexProvider().fetch()
        self.assertEqual(snapshot.status, "error")
        self.assertEqual(snapshot.error, "No limit window reported")

    def test_blocked_plan_reports_why(self) -> None:
        payload = usage_payload()
        payload["rate_limit"]["allowed"] = False
        self._stub_usage(payload)
        snapshot = CodexProvider().fetch()
        self.assertEqual(snapshot.status, "error")
        assert snapshot.error is not None
        self.assertIn("blocked", snapshot.error)

    def test_http_401_is_auth_needed(self) -> None:
        import urllib.error

        patcher = mock.patch.object(
            codex.urllib.request,
            "urlopen",
            side_effect=urllib.error.HTTPError(
                "url", 401, "Unauthorized", email.message.Message(), None
            ),
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        snapshot = CodexProvider().fetch()
        self.assertEqual(snapshot.status, "auth_needed")
        assert snapshot.error is not None
        self.assertIn("rejected", snapshot.error)

    def test_http_403_html_challenge_is_retryable_not_a_login_failure(self) -> None:
        import io
        import urllib.error

        patcher = mock.patch.object(
            codex.urllib.request,
            "urlopen",
            side_effect=urllib.error.HTTPError(
                "url",
                403,
                "Forbidden",
                email.message.Message(),
                io.BytesIO(b"<html><body>challenge</body></html>"),
            ),
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        with self.assertRaises(RuntimeError) as ctx:
            CodexProvider().fetch()
        self.assertIn("blocked", str(ctx.exception))

    def test_http_403_json_rejection_is_auth_needed(self) -> None:
        import io
        import urllib.error

        patcher = mock.patch.object(
            codex.urllib.request,
            "urlopen",
            side_effect=urllib.error.HTTPError(
                "url",
                403,
                "Forbidden",
                email.message.Message(),
                io.BytesIO(b'{"error": "nope"}'),
            ),
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        snapshot = CodexProvider().fetch()
        self.assertEqual(snapshot.status, "auth_needed")
        assert snapshot.error is not None
        self.assertIn("rejected", snapshot.error)

    def test_free_plan_type_is_labeled(self) -> None:
        payload = usage_payload(plan_type="free")
        self._stub_usage(payload)
        snapshot = CodexProvider().fetch()
        self.assertEqual(snapshot.plan, "Free")

    def test_unknown_plan_type_falls_back_to_title_case(self) -> None:
        payload = usage_payload(plan_type="grok_ultra")
        self._stub_usage(payload)
        snapshot = CodexProvider().fetch()
        self.assertEqual(snapshot.plan, "Grok_Ultra")


class WindowKindPayloadTest(ProviderTest):
    """The kind survives the trip to the panel, which is what groups providers."""

    def test_the_kind_reaches_the_panel_payload(self):
        self._stub_usage(usage_payload())
        snapshot = CodexProvider().fetch()
        kinds = {m["key"]: m["kind"] for m in snapshot.to_panel_dict()["metrics"]}
        # monthly window -> monthly, the 5-hour secondary -> rolling
        self.assertEqual(kinds, {"monthly": "monthly", "window": "rolling"})


class WindowLabelTest(unittest.TestCase):
    def test_known_windows(self) -> None:
        self.assertEqual(codex._window_label(18000), "5-hour limit")
        self.assertEqual(codex._window_label(86400), "Daily")
        self.assertEqual(codex._window_label(604800), "Weekly")
        self.assertEqual(codex._window_label(2592000), "Monthly limit")

    def test_unknown_durations(self) -> None:
        self.assertEqual(codex._window_label(1209600), "14 day window")
        self.assertEqual(codex._window_label(0), "Rolling limit")
        self.assertEqual(codex._window_label(None), "Rolling limit")


if __name__ == "__main__":
    unittest.main()


class WindowKindTest(unittest.TestCase):
    """Codex names both meters generically, so the duration decides the kind.

    Its keys are "monthly" and "window" whatever the windows actually are, so
    limit_window_seconds is the only trustworthy signal — and the one the panel's
    shared window picker groups providers by.
    """

    def test_five_hour_window_is_rolling(self):
        self.assertEqual(codex._window_kind(18000), "rolling")

    def test_a_day_is_still_the_short_window(self):
        self.assertEqual(codex._window_kind(86400), "rolling")

    def test_seven_days_is_weekly(self):
        self.assertEqual(codex._window_kind(604800), "weekly")

    def test_a_week_rounded_oddly_is_still_weekly(self):
        # Providers do not agree on what a week is; someone choosing between
        # windows does not care about the rounding.
        self.assertEqual(codex._window_kind(648000), "weekly")

    def test_a_month_is_monthly(self):
        self.assertEqual(codex._window_kind(2592000), "monthly")

    def test_a_missing_or_absurd_duration_is_not_a_window(self):
        for value in (None, "soon", 0, -1, True):
            self.assertEqual(codex._window_kind(value), "other")


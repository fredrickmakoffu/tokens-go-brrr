"""Tests for the LLM layer: who writes, what is asked, and what comes back.

Nothing here touches a network. The transport is stubbed, which is also what
makes the important assertions possible: that only numbers are sent, that a
credential file is never written to, and that every failure mode returns the
template rather than raising into the daemon.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import cursor_spend_monitor.llm_composer as llm
from cursor_spend_monitor.notify_engine import ACTIONABLE, INFORMATIVE, Message
from cursor_spend_monitor.providers.base import Meter, ProviderSnapshot


def snap(
    provider_id: str,
    name: str,
    meters: list[Meter],
    *,
    status: str = "ok",
    borrowed: str | None = None,
) -> ProviderSnapshot:
    return ProviderSnapshot(
        provider_id=provider_id,
        display_name=name,
        icon=provider_id,
        plan=None,
        metrics=meters,
        primary_key=meters[0].key if meters else "",
        status=status,
        borrowed_from=borrowed,
    )


def meter(key: str, percent: float, kind: str) -> Meter:
    return Meter(key, key, percent, kind=kind)


CLAUDE_TIGHT = snap(
    "claude",
    "Claude Code",
    [meter("five_hour", 92, "rolling"), meter("seven_day", 40, "weekly")],
)
CLAUDE_ROOMY = snap(
    "claude",
    "Claude Code",
    [meter("five_hour", 10, "rolling"), meter("seven_day", 20, "weekly")],
)
OPENCODE_ROOMY = snap(
    "opencode",
    "OpenCode",
    [meter("rolling", 5, "rolling"), meter("weekly", 8, "weekly")],
)
CURSOR = snap("cursor", "Cursor", [meter("monthly", 30, "monthly")])

FACTS = {
    "ranked": [
        {"provider": "opencode", "tokens": 1400000, "sessions": 27, "cost_usd": 4.1},
        {"provider": "claude", "tokens": 340000, "sessions": 11, "cost_usd": 20.0},
    ]
}


class RoutingTest(unittest.TestCase):
    def test_the_writer_is_whichever_has_the_most_short_window_room(self):
        chosen = llm.choose([CLAUDE_TIGHT, OPENCODE_ROOMY])
        assert chosen is not None
        self.assertEqual(chosen.provider_id, "opencode")
        self.assertEqual(chosen.short_headroom, 92)

    def test_a_provider_outside_the_pool_is_never_the_writer(self):
        # Cursor has no inference API we can call, whatever room its meter shows.
        chosen = llm.choose([CURSOR, OPENCODE_ROOMY])
        assert chosen is not None
        self.assertEqual(chosen.provider_id, "opencode")
        self.assertEqual([g.provider_id for g in llm.candidates([CURSOR])], [])

    def test_the_provider_that_triggered_the_message_is_excluded(self):
        # Warning about a spent provider by spending that same provider is the
        # joke this rule exists to prevent.
        self.assertIsNone(llm.choose([CLAUDE_ROOMY], trigger="claude"))
        chosen = llm.choose([CLAUDE_ROOMY, OPENCODE_ROOMY], trigger="opencode")
        assert chosen is not None
        self.assertEqual(chosen.provider_id, "claude")

    def test_a_provider_below_the_floor_does_not_write(self):
        tight = snap("opencode", "OpenCode", [meter("rolling", 95, "rolling")])
        self.assertIsNone(llm.choose([tight], floor=15))
        chosen = llm.choose([tight], floor=3)
        assert chosen is not None
        self.assertEqual(chosen.provider_id, "opencode")

    def test_a_borrowed_row_is_not_a_writer(self):
        borrowed = snap(
            "opencode", "OpenCode", [meter("rolling", 5, "rolling")], borrowed="claude"
        )
        self.assertIsNone(llm.choose([borrowed]))

    def test_a_broken_provider_is_not_a_writer(self):
        broken = snap(
            "opencode", "OpenCode", [meter("rolling", 5, "rolling")], status="error"
        )
        self.assertIsNone(llm.choose([broken]))

    def test_monthly_only_ranks_below_a_short_window(self):
        monthly_claude = snap("claude", "Claude Code", [meter("monthly", 1, "monthly")])
        ranked = [
            g.provider_id for g in llm.candidates([monthly_claude, OPENCODE_ROOMY])
        ]
        self.assertEqual(ranked, ["opencode", "claude"])

    def test_the_default_model_comes_from_the_provider(self):
        chosen = llm.choose([OPENCODE_ROOMY])
        assert chosen is not None
        self.assertEqual(chosen.model, llm.DEFAULT_MODELS["opencode"])

    def test_a_configured_model_wins_and_can_pin_the_provider(self):
        chosen = llm.choose(
            [CLAUDE_ROOMY, OPENCODE_ROOMY], provider="claude", model="claude-haiku-4-5"
        )
        assert chosen is not None
        self.assertEqual(chosen.provider_id, "claude")
        self.assertEqual(chosen.model, "claude-haiku-4-5")

    def test_a_spent_provider_never_writes_even_with_no_floor(self):
        dead = snap("opencode", "OpenCode", [meter("rolling", 100, "rolling")])
        self.assertIsNone(llm.choose([dead], floor=0))


class PromptTest(unittest.TestCase):
    def message(self) -> Message:
        return Message(kind=INFORMATIVE, key="weekly:1", body="Last week: 38 sessions.")

    def test_the_prompt_carries_the_numbers_and_the_ranked_ids(self):
        prompt = llm.build_prompt(self.message(), FACTS)
        self.assertIn("1400000", prompt)
        self.assertIn("opencode", prompt)
        self.assertIn("claude", prompt)

    def test_the_prompt_asks_for_the_featured_provider(self):
        # Without this the badge and the prose can disagree.
        prompt = llm.build_prompt(self.message(), FACTS)
        self.assertIn("FEATURED:", prompt)
        self.assertIn("SHARE:", prompt)

    def test_the_prompt_forbids_inventing_numbers(self):
        self.assertIn("Never invent", llm.build_prompt(self.message(), FACTS))

    def test_a_prompt_with_no_ranked_facts_is_still_valid(self):
        prompt = llm.build_prompt(self.message(), {})
        self.assertIn("FEATURED:", prompt)


class ParseReplyTest(unittest.TestCase):
    def test_a_full_reply_splits_into_its_parts(self):
        body, share, featured = llm.parse_reply(
            "You shipped 38 sessions last week.\n"
            "SHARE: 38 sessions, 1.9M tokens.\n"
            "FEATURED: opencode"
        )
        self.assertEqual(body, "You shipped 38 sessions last week.")
        self.assertEqual(share, "SHARE: 38 sessions, 1.9M tokens.")
        self.assertEqual(featured, "opencode")

    def test_a_trailing_note_after_the_markers_is_not_part_of_the_message(self):
        body, _, _ = llm.parse_reply("Body text.\nFEATURED: claude\nHope that helps!")
        self.assertEqual(body, "Body text.")

    def test_a_share_line_is_normalised_and_clamped(self):
        _, share, _ = llm.parse_reply(f"Body.\nSHARE: {'x' * 400}")
        self.assertTrue(share.startswith("SHARE: "))
        self.assertEqual(len(share), llm.SHARE_LIMIT)

    def test_a_reply_without_markers_is_all_body(self):
        body, share, featured = llm.parse_reply("Just a sentence.")
        self.assertEqual(body, "Just a sentence.")
        self.assertEqual(share, "")
        self.assertEqual(featured, "")

    def test_the_featured_id_is_lowercased(self):
        _, _, featured = llm.parse_reply("Body.\nFEATURED: OpenCode")
        self.assertEqual(featured, "opencode")


class GenerateTest(unittest.TestCase):
    def generator(self, provider: str = "opencode") -> llm.Generator:
        return llm.Generator(
            provider_id=provider,
            name=provider.title(),
            model="a-cheap-model",
            short_headroom=50,
            monthly_headroom=None,
            reason="test",
        )

    def test_an_openai_shaped_reply_is_read(self):
        response = {"choices": [{"message": {"content": "Hello there."}}]}
        with (
            mock.patch.object(llm, "_opencode_key", return_value="key"),
            mock.patch.object(llm, "_post_json", return_value=response) as post,
        ):
            text = llm.generate(self.generator(), "prompt")
        self.assertEqual(text, "Hello there.")
        host, path = llm.ENDPOINTS["opencode"]
        self.assertEqual(post.call_args[0][0], host)
        self.assertEqual(post.call_args[0][1], path)
        self.assertIn("Bearer key", post.call_args[0][3]["authorization"])

    def test_an_anthropic_shaped_reply_is_read(self):
        response = {"content": [{"type": "text", "text": "Hello there."}]}
        with (
            mock.patch.object(llm, "_claude_token", return_value="tok"),
            mock.patch.object(llm, "_post_json", return_value=response) as post,
        ):
            text = llm.generate(self.generator("claude"), "prompt")
        self.assertEqual(text, "Hello there.")
        headers = post.call_args[0][3]
        self.assertIn("Bearer tok", headers["authorization"])
        self.assertEqual(headers["anthropic-version"], llm.ANTHROPIC_VERSION)
        self.assertEqual(headers["anthropic-beta"], llm.OAUTH_BETA)

    def test_only_one_message_is_sent_and_it_is_the_prompt(self):
        response = {"choices": [{"message": {"content": "x"}}]}
        with (
            mock.patch.object(llm, "_opencode_key", return_value="k"),
            mock.patch.object(llm, "_post_json", return_value=response) as post,
        ):
            llm.generate(self.generator(), "the whole instruction")
        payload = post.call_args[0][2]
        self.assertEqual(
            payload["messages"], [{"role": "user", "content": "the whole instruction"}]
        )
        self.assertEqual(payload["model"], "a-cheap-model")

    def test_a_provider_outside_the_pool_cannot_generate(self):
        with self.assertRaises(llm.LlmError):
            llm.generate(self.generator("cursor"), "prompt")

    def test_a_missing_credential_is_an_error_not_a_crash(self):
        with (
            mock.patch.object(llm, "_opencode_key", side_effect=llm.LlmError("none")),
            self.assertRaises(llm.LlmError),
        ):
            llm.generate(self.generator(), "prompt")


class TransportTest(unittest.TestCase):
    """The HTTP layer, exercised through a fake connection."""

    class Response:
        def __init__(self, status: int, body: str) -> None:
            self.status = status
            self._body = body.encode()

        def read(self) -> bytes:
            return self._body

    class Connection:
        def __init__(self, status: int, body: str) -> None:
            self._response = TransportTest.Response(status, body)
            self.requests: list[tuple] = []
            self.closed = False

        def request(self, method, path, body=None, headers=None) -> None:
            self.requests.append((method, path, body, headers))

        def getresponse(self):
            return self._response

        def close(self) -> None:
            self.closed = True

    def post(self, status: int, body: str):
        connection = self.Connection(status, body)
        with mock.patch.object(
            llm.http.client, "HTTPSConnection", return_value=connection
        ):
            result = llm._post_json(
                "example.test",
                "/v1/x",
                {"a": 1},
                {"authorization": "Bearer t"},
                timeout=5,
            )
        return result, connection

    def test_a_successful_reply_is_decoded(self):
        result, connection = self.post(200, json.dumps({"ok": True}))
        self.assertEqual(result, {"ok": True})
        self.assertTrue(connection.closed)

    def test_the_connection_is_tls_by_construction(self):
        # No URL and no scheme, so there is nothing to validate and nothing to
        # get wrong.
        _, connection = self.post(200, "{}")
        method, path, body, headers = connection.requests[0]
        self.assertEqual(method, "POST")
        self.assertEqual(path, "/v1/x")
        self.assertEqual(json.loads(body), {"a": 1})
        self.assertEqual(headers["content-type"], "application/json")

    def test_a_rate_limit_is_its_own_error(self):
        with self.assertRaises(llm.LlmRateLimited):
            self.post(429, "{}")

    def test_a_server_error_is_reported_without_its_body_leaking_far(self):
        with self.assertRaises(llm.LlmError) as caught:
            self.post(500, "x" * 1000)
        self.assertLess(len(str(caught.exception)), 300)

    def test_invalid_json_is_an_error(self):
        with self.assertRaises(llm.LlmError):
            self.post(200, "not json")

    def test_an_unreachable_host_is_an_error(self):
        with (
            mock.patch.object(
                llm.http.client, "HTTPSConnection", side_effect=OSError("no route")
            ),
            self.assertRaises(llm.LlmError),
        ):
            llm._post_json("example.test", "/x", {}, {}, timeout=5)


class RewriteTest(unittest.TestCase):
    def message(self) -> Message:
        return Message(
            kind=ACTIONABLE,
            key="meter:claude:five_hour:92",
            body="Claude Code 5-hour limit is at 92%. OpenCode has room.",
            provider="opencode",
            meta={"role": "suggested", "providerName": "Opencode", "percent": 92},
        )

    def generator(self) -> llm.Generator:
        return llm.Generator(
            provider_id="claude",
            name="Claude Code",
            model="a-cheap-model",
            short_headroom=60,
            monthly_headroom=None,
            reason="test",
        )

    def rewrite(self, reply: str, facts: dict | None = None) -> Message | None:
        with mock.patch.object(llm, "generate", return_value=reply):
            return llm.rewrite(
                self.message(), generator=self.generator(), facts=facts or FACTS
            )

    def test_the_model_wording_replaces_the_template(self):
        rewritten = self.rewrite(
            "Claude is nearly spent. Move to OpenCode.\nFEATURED: opencode"
        )
        assert rewritten is not None
        self.assertEqual(rewritten.body, "Claude is nearly spent. Move to OpenCode.")
        self.assertEqual(rewritten.kind, ACTIONABLE)
        self.assertEqual(rewritten.key, "meter:claude:five_hour:92")

    def test_the_model_chooses_which_ai_is_featured(self):
        rewritten = self.rewrite("Body.\nFEATURED: claude")
        assert rewritten is not None
        self.assertEqual(rewritten.provider, "claude")
        self.assertEqual(rewritten.meta["providerName"], "Claude Code")

    def test_a_featured_id_it_was_not_offered_is_ignored(self):
        # A badge pointing at an AI the message is not about is worse than the
        # template's own choice.
        rewritten = self.rewrite("Body.\nFEATURED: gpt-9")
        assert rewritten is not None
        self.assertEqual(rewritten.provider, "opencode")

    def test_a_share_line_is_carried_through(self):
        rewritten = self.rewrite("Body.\nSHARE: 1.9M tokens.\nFEATURED: opencode")
        assert rewritten is not None
        self.assertEqual(rewritten.share, "SHARE: 1.9M tokens.")

    def test_a_reworded_message_is_marked_as_the_models(self):
        rewritten = self.rewrite("Body.\nFEATURED: opencode")
        assert rewritten is not None
        self.assertEqual(rewritten.meta["source"], "llm")

    def test_a_reworded_warm_note_is_shown_as_written_not_re_rendered(self):
        from cursor_spend_monitor import notify_engine as ne

        warm = Message(
            kind=INFORMATIVE,
            key="warm:abc",
            body="Last 2h: 3 sessions.",
            meta={"tier": "warm", "asOf": 1, "tpl": {"id": "warm", "p": {"hours": 2}}},
        )
        with mock.patch.object(llm, "generate", return_value="Model words."):
            rewritten = llm.rewrite(warm, generator=self.generator(), facts=FACTS)
        assert rewritten is not None
        payload = ne.billboard_payload(
            {
                "id": 1, "kind": rewritten.kind, "created_at": 1,
                "body": rewritten.body, "meta": __import__("json").dumps(rewritten.meta),
            }
        )
        self.assertIsNone(payload["template"])
        self.assertEqual(payload["source"], "llm")
        self.assertEqual(payload["tier"], "warm")

    def test_an_empty_reply_keeps_the_template(self):
        self.assertIsNone(self.rewrite("   "))

    def test_a_refusal_keeps_the_template(self):
        with mock.patch.object(llm, "generate", side_effect=llm.LlmRateLimited("429")):
            self.assertIsNone(
                llm.rewrite(self.message(), generator=self.generator(), facts=FACTS)
            )

    def test_the_template_s_share_survives_a_reply_without_one(self):
        original = Message(
            kind="shareable", key="share:1", body="body", share="SHARE: kept"
        )
        with mock.patch.object(
            llm, "generate", return_value="New body.\nFEATURED: opencode"
        ):
            rewritten = llm.rewrite(original, generator=self.generator(), facts=FACTS)
        assert rewritten is not None
        self.assertEqual(rewritten.share, "SHARE: kept")

    def test_which_provider_wrote_it_is_recorded(self):
        rewritten = self.rewrite("Body.\nFEATURED: opencode")
        assert rewritten is not None
        self.assertEqual(rewritten.meta["composed_by"], "claude")


class CredentialTest(unittest.TestCase):
    """Credentials are read and never written."""

    def test_a_credential_file_is_untouched_by_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            # The data home is redirected, so the opencode path resolves inside
            # the temporary directory.
            path = Path(tmp) / "opencode" / "auth.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"opencode-go": {"key": "secret"}}))
            before = (path.read_bytes(), path.stat().st_mtime_ns)

            response = {"choices": [{"message": {"content": "hi"}}]}
            with (
                mock.patch.dict("os.environ", {"XDG_DATA_HOME": tmp}),
                mock.patch.object(llm, "_post_json", return_value=response),
            ):
                key = llm._opencode_key()
                self.assertEqual(key, "secret")

            self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), before)

    def test_a_missing_credential_file_raises_rather_than_creating_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            with (
                mock.patch.dict("os.environ", {"XDG_DATA_HOME": tmp}),
                self.assertRaises(llm.LlmError),
            ):
                llm._opencode_key()
            self.assertEqual(list(Path(tmp).iterdir()), [])


class DaemonComposeTest(unittest.TestCase):
    """The daemon's wiring: templates, unless a model can improve on them."""

    def setUp(self) -> None:
        import tempfile as _tempfile

        from cursor_spend_monitor import ledger as _ledger

        self._dir = _tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.con = _ledger.connect(Path(self._dir.name) / "usage.db")
        self.addCleanup(self.con.close)
        self.ledger = _ledger

    def daemon(self, **values):
        import types as _types

        from cursor_spend_monitor.config import MonitorConfig
        from cursor_spend_monitor.daemon import UsageDaemon

        stub = mock.Mock()
        stub.config = MonitorConfig(**values)
        stub.snapshots = []
        stub._llm_backoff = {}
        stub._facts_for = _types.MethodType(UsageDaemon._facts_for, stub)
        stub._log_skipped = _types.MethodType(UsageDaemon._log_skipped, stub)
        stub._record_llm = _types.MethodType(UsageDaemon._record_llm, stub)
        return stub

    def message(self) -> Message:
        return Message(kind=INFORMATIVE, key="weekly:1", body="template body")

    def compose(self, stub):
        from cursor_spend_monitor.daemon import UsageDaemon

        return UsageDaemon._compose(stub, self.con, [self.message()])

    def test_the_model_is_not_consulted_while_the_feature_is_off(self):
        stub = self.daemon(llm_notifications=False)
        with mock.patch.object(llm, "choose") as choose:
            result = self.compose(stub)
        choose.assert_not_called()
        self.assertEqual(result[0].body, "template body")

    def test_no_generator_with_room_keeps_the_template(self):
        stub = self.daemon(llm_notifications=True)
        with mock.patch.object(llm, "choose", return_value=None) as choose:
            result = self.compose(stub)
        choose.assert_called_once()
        self.assertEqual(result[0].body, "template body")

    def test_a_written_message_replaces_the_template(self):
        stub = self.daemon(llm_notifications=True)
        written = Message(kind=INFORMATIVE, key="weekly:1", body="model body")
        with (
            mock.patch.object(llm, "choose", return_value=self.generator()),
            mock.patch.object(llm, "rewrite", return_value=written),
        ):
            result = self.compose(stub)
        self.assertEqual(result[0].body, "model body")

    def test_a_failed_rewrite_keeps_the_template(self):
        stub = self.daemon(llm_notifications=True)
        with (
            mock.patch.object(llm, "choose", return_value=self.generator()),
            mock.patch.object(llm, "rewrite", return_value=None),
        ):
            result = self.compose(stub)
        self.assertEqual(result[0].body, "template body")

    def test_a_skipped_rewrite_is_logged_with_its_origin(self):
        stub = self.daemon(llm_notifications=True)
        from cursor_spend_monitor.daemon import UsageDaemon

        with mock.patch.object(llm, "choose", return_value=None):
            UsageDaemon._compose(
                stub, self.con, [self.message()], origin="scheduled:weekly"
            )
        (entry,) = [c.args[0] for c in stub.llm_log.record.call_args_list]
        self.assertEqual(entry["outcome"], "skipped")
        self.assertEqual(entry["reason"], "no_generator")
        self.assertEqual(entry["trigger"], "scheduled:weekly")
        self.assertEqual(entry["message_key"], "weekly:1")

    def test_a_rewrite_is_given_the_log_and_its_origin(self):
        stub = self.daemon(llm_notifications=True)
        from cursor_spend_monitor.daemon import UsageDaemon

        with (
            mock.patch.object(llm, "choose", return_value=self.generator()),
            mock.patch.object(llm, "rewrite", return_value=None) as rewrite,
        ):
            UsageDaemon._compose(
                stub, self.con, [self.message()], origin="event:meter"
            )
        self.assertIs(rewrite.call_args.kwargs["recorder"], stub._record_llm)
        self.assertEqual(rewrite.call_args.kwargs["context"], {"trigger": "event:meter"})

    def test_nothing_is_logged_while_the_feature_is_off(self):
        stub = self.daemon(llm_notifications=False)
        self.compose(stub)
        stub.llm_log.record.assert_not_called()

    def test_the_floor_and_the_pins_come_from_the_config(self):
        stub = self.daemon(
            llm_notifications=True,
            llm_min_headroom=42,
            llm_generator_provider="opencode",
            llm_generator_model="a-cheap-model",
        )
        with mock.patch.object(llm, "choose", return_value=None) as choose:
            self.compose(stub)
        kwargs = choose.call_args.kwargs
        self.assertEqual(kwargs["floor"], 42)
        self.assertEqual(kwargs["provider"], "opencode")
        self.assertEqual(kwargs["model"], "a-cheap-model")

    def generator(self) -> llm.Generator:
        return llm.Generator(
            provider_id="claude",
            name="Claude Code",
            model="a-cheap-model",
            short_headroom=60,
            monthly_headroom=None,
            reason="test",
        )


if __name__ == "__main__":
    unittest.main()

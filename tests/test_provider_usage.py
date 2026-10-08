"""The two usage fetches: what a reply becomes, and what a failure becomes.

Both reach their endpoint over `http.client.HTTPSConnection`, so the socket is
mocked rather than a URL opener. That keeps these honest about what changed when
they stopped using `urlopen`: the status-to-exception mapping, and the JSON
decoding around it. The tokens here are throwaway strings -- nothing in this file
touches a credential.

Both providers are driven through the same tests, because the contract is the
same: read one JSON endpoint, map its failures onto ours, never invent a number.
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass
from typing import Any
from unittest import mock

from cursor_spend_monitor.providers import claude, opencode


@dataclass(frozen=True)
class Target:
    """One provider's usage call, and the endpoint it must reach."""

    name: str
    fetch: Any
    token: str
    host: str
    path: str


def targets() -> list[Target]:
    return [
        Target(
            "claude",
            claude.ClaudeProvider()._get_usage,
            "token",
            claude.USAGE_HOST,
            claude.USAGE_PATH,
        ),
        Target(
            "opencode",
            opencode.OpenCodeProvider()._get_usage,
            "key",
            opencode.USAGE_HOST,
            opencode.USAGE_PATH,
        ),
    ]


def reply(status: int, body: str = "{}") -> mock.Mock:
    """A stand-in for what `getresponse()` hands back."""
    response = mock.Mock()
    response.status = status
    response.read.return_value = body.encode()
    return response


class UsageFetchTest(unittest.TestCase):
    """One endpoint, one socket, one set of failure mappings."""

    def setUp(self) -> None:
        self.answer = reply(200)
        self.unreachable: OSError | None = None
        self.sockets: list[mock.Mock] = []
        patcher = mock.patch("http.client.HTTPSConnection", side_effect=self._connect)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _connect(self, host: str, timeout: int | None = None) -> mock.Mock:
        """A fresh socket per call, so call counts stay honest per provider."""
        socket = mock.Mock()
        socket.host = host
        socket.getresponse.return_value = self.answer
        if self.unreachable is not None:
            socket.getresponse.side_effect = self.unreachable
        self.sockets.append(socket)
        return socket

    def test_it_goes_straight_to_the_https_host(self):
        # No URL to open and no scheme to validate, which is why the audit rule
        # that flagged `urlopen` here cannot apply: https is in the code.
        for target in targets():
            with self.subTest(provider=target.name):
                target.fetch(target.token)
                socket = self.sockets[-1]
                self.assertEqual(socket.host, target.host)
                self.assertEqual(
                    socket.request.call_args[0][:2], ("GET", target.path)
                )

    def test_a_reply_is_decoded(self):
        self.answer = reply(200, '{"weekly": {"percent": 12}}')
        for target in targets():
            with self.subTest(provider=target.name):
                self.assertEqual(target.fetch(target.token)["weekly"]["percent"], 12)

    def test_a_rejected_key_is_a_permission_error(self):
        self.answer = reply(401)
        for target in targets():
            with self.subTest(provider=target.name):
                with self.assertRaises(PermissionError):
                    target.fetch(target.token)
                self.sockets[-1].close.assert_called_once()

    def test_another_status_names_itself(self):
        self.answer = reply(500, "boom")
        for target in targets():
            with self.subTest(provider=target.name):
                with self.assertRaises(RuntimeError) as caught:
                    target.fetch(target.token)
                self.assertIn("500", str(caught.exception))
                self.assertIn("boom", str(caught.exception))

    def test_invalid_json_is_reported_rather_than_raised_raw(self):
        self.answer = reply(200, "not json")
        for target in targets():
            with self.subTest(provider=target.name):
                with self.assertRaises(RuntimeError) as caught:
                    target.fetch(target.token)
                self.assertIn("invalid JSON", str(caught.exception))

    def test_an_unreachable_host_is_reported_and_the_socket_closed(self):
        # The read fails, which is how an unreachable host actually shows up:
        # constructing `HTTPSConnection` does not connect.
        self.unreachable = OSError("no route to host")
        for target in targets():
            with self.subTest(provider=target.name):
                with self.assertRaises(RuntimeError) as caught:
                    target.fetch(target.token)
                self.assertIn("no route to host", str(caught.exception))
                self.sockets[-1].close.assert_called_once()


class MeterReadingTest(unittest.TestCase):
    def test_a_reading_that_will_not_parse_is_dropped(self):
        # A meter states how much of a limit is used. Defaulting an unreadable
        # one to zero would be inventing a number, so the window goes instead.
        self.assertEqual(claude._as_float("42.5"), 42.5)
        self.assertIsNone(claude._as_float("not a number"))
        self.assertIsNone(claude._as_float(None))
        self.assertEqual(opencode._as_float(7), 7.0)
        self.assertIsNone(opencode._as_float({"percent": 1}))


if __name__ == "__main__":
    unittest.main()

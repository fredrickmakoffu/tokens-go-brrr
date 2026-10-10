from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from gi.repository import Gio, GLib  # type: ignore  # gi has no stubs

BUS_NAME = "io.github.fredrickmakoffu.AIUsage"
OBJECT_PATH = "/io/github/fredrickmakoffu/AIUsage"
INTERFACE = BUS_NAME


def _as_int(value: Any) -> int:
    """A value off the bus as an int; a malformed one is not worth raising for."""
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return 0


INTERFACE_XML = """
<node>
  <interface name="io.github.fredrickmakoffu.AIUsage">
    <property name="Version" type="s" access="read"/>
    <method name="GetState"><arg type="s" direction="out" name="json"/></method>
    <method name="Refresh"/>
    <method name="SetPrimary">
      <arg type="s" direction="in" name="provider"/>
      <arg type="s" direction="in" name="metric"/>
    </method>
    <method name="Acknowledge">
      <arg type="u" direction="in" name="id"/>
    </method>
    <method name="LlmLog">
      <arg type="s" direction="in" name="day"/>
      <arg type="s" direction="out" name="json"/>
    </method>
    <method name="ClearLlmLog"/>
    <method name="Quit"/>
    <signal name="StateChanged"><arg type="s" name="json"/></signal>
  </interface>
</node>
"""


class UsageService:
    """Session-bus service the GNOME Shell extension talks to."""

    def __init__(
        self,
        *,
        version: str,
        get_state: Callable[[], dict[str, Any]],
        on_refresh: Callable[..., Any],
        on_set_primary: Callable[[str, str], None],
        on_acknowledge: Callable[[int], None],
        on_quit: Callable[..., Any],
        on_name_lost: Callable[[], None],
        on_llm_log: Callable[[str], dict[str, Any]] | None = None,
        on_llm_log_clear: Callable[[], None] | None = None,
    ) -> None:
        self._version = version
        self._get_state = get_state
        self._on_refresh = on_refresh
        self._on_set_primary = on_set_primary
        self._on_acknowledge = on_acknowledge
        self._on_quit = on_quit
        self._on_llm_log = on_llm_log
        self._on_llm_log_clear = on_llm_log_clear
        self._on_name_lost = on_name_lost
        self._connection: Gio.DBusConnection | None = None
        self._registration = 0
        self._iface = Gio.DBusNodeInfo.new_for_xml(INTERFACE_XML).interfaces[0]
        self._own_id = Gio.bus_own_name(
            Gio.BusType.SESSION,
            BUS_NAME,
            Gio.BusNameOwnerFlags.NONE,
            self._bus_acquired,
            None,
            self._name_lost,
        )

    def _bus_acquired(self, connection: Gio.DBusConnection, _name: str) -> None:
        self._connection = connection
        self._registration = connection.register_object(
            OBJECT_PATH, self._iface, self._method_call, self._get_property, None
        )

    def _name_lost(self, _connection, _name: str) -> None:
        self._on_name_lost()

    def _method_call(
        self, _conn, _sender, _path, _iface, method, params, invocation
    ) -> None:
        if method == "GetState":
            payload = json.dumps(self._get_state())
            invocation.return_value(GLib.Variant("(s)", (payload,)))
        elif method == "Refresh":
            invocation.return_value(None)
            GLib.idle_add(self._on_refresh)
        elif method == "SetPrimary":
            provider, metric = params.unpack()
            self._on_set_primary(str(provider), str(metric))
            invocation.return_value(None)
        elif method == "Acknowledge":
            # The panel has shown this message; the daemon records that so it
            # is never offered again, across logins and extension reloads.
            (message_id,) = params.unpack()
            invocation.return_value(None)
            self._on_acknowledge(_as_int(message_id))
        elif method == "LlmLog":
            # Read-only: the extension never opens the log files itself.
            (day,) = params.unpack()
            payload = self._on_llm_log(str(day)) if self._on_llm_log else {}
            invocation.return_value(GLib.Variant("(s)", (json.dumps(payload),)))
        elif method == "ClearLlmLog":
            if self._on_llm_log_clear:
                self._on_llm_log_clear()
            invocation.return_value(None)
        elif method == "Quit":
            invocation.return_value(None)
            GLib.idle_add(self._on_quit)
        else:
            invocation.return_error_literal(
                Gio.dbus_error_quark(),
                Gio.DBusError.UNKNOWN_METHOD,
                f"Unknown {method}",
            )

    def _get_property(self, _conn, _sender, _path, _iface, prop):
        if prop == "Version":
            return GLib.Variant("s", self._version)
        return None

    def emit_state(self, state: dict[str, Any]) -> None:
        if self._connection is None:
            return
        self._connection.emit_signal(
            None,
            OBJECT_PATH,
            INTERFACE,
            "StateChanged",
            GLib.Variant("(s)", (json.dumps(state),)),
        )

    def close(self) -> None:
        if self._connection and self._registration:
            self._connection.unregister_object(self._registration)
            self._registration = 0
        if self._own_id:
            Gio.bus_unown_name(self._own_id)
            self._own_id = 0

"""HTTPS JSON helpers shared by providers, Cursor auth, and the LLM composer.

Uses ``http.client.HTTPSConnection`` so TLS is a property of the code — no
scheme string to get wrong. Certificate and hostname verification stay on
(Python ≥ 3.4.3 default; this package requires 3.11).
"""

from __future__ import annotations

import http.client
import json
from typing import Any
from urllib.parse import urlsplit

from . import __version__

USER_AGENT = f"tokens-go-brrr/{__version__}"


class HttpJsonError(Exception):
    """Non-success HTTP status with a decoded body snippet available."""

    def __init__(self, status: int, body: str, *, host: str, path: str) -> None:
        self.status = status
        self.body = body
        self.host = host
        self.path = path
        super().__init__(f"HTTP {status} from {host}{path}")


def request_json(
    method: str,
    host: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | bytes | None = None,
    timeout: float = 30,
) -> dict[str, Any]:
    """POST/GET JSON over HTTPS. Returns a decoded object.

    Raises:
        OSError: connection failure (callers usually wrap as RuntimeError).
        HttpJsonError: HTTP status ≥ 400.
        RuntimeError: response is not a JSON object.
    """
    hdrs = {"User-Agent": USER_AGENT, "Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)

    payload: bytes | None
    if body is None:
        payload = None
    elif isinstance(body, (bytes, bytearray)):
        payload = bytes(body)
    else:
        payload = json.dumps(body).encode()

    connection = http.client.HTTPSConnection(host, timeout=timeout)
    try:
        connection.request(method, path, body=payload, headers=hdrs)
        response = connection.getresponse()
        status = int(response.status)
        detail = response.read().decode("utf-8", errors="replace")
    finally:
        connection.close()

    if status >= 400:
        raise HttpJsonError(status, detail, host=host, path=path)
    try:
        parsed = json.loads(detail) if detail else {}
    except ValueError as exc:
        raise RuntimeError(f"invalid JSON from {host}{path}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError(f"{host}{path} returned {type(parsed).__name__}, not an object")
    return parsed


def request_json_url(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | bytes | None = None,
    timeout: float = 30,
) -> dict[str, Any]:
    """Same as ``request_json`` but takes an https URL."""
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        raise RuntimeError(f"Unsupported URL scheme: {url}")
    path = parts.path or "/"
    if parts.query:
        path = f"{path}?{parts.query}"
    return request_json(
        method,
        parts.hostname,
        path,
        headers=headers,
        body=body,
        timeout=timeout,
    )

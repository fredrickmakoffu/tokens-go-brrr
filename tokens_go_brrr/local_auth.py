from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

from .coerce import jwt_exp
from .http_json import USER_AGENT, HttpJsonError, request_json_url

STATE_DB = Path.home() / ".config" / "Cursor" / "User" / "globalStorage" / "state.vscdb"
# pi-lens-ignore: python-hardcoded-secrets  # public api2.cursor.sh endpoint
OAUTH_TOKEN_URL = (
    "https://api2.cursor.sh/oauth/token"  # nosemgrep: public endpoint, name contains TOKEN
)
# Public Cursor desktop OAuth client id (used by the IDE / community tools)
# pi-lens-ignore: python-hardcoded-secrets  # public OAuth client id, not a credential
OAUTH_CLIENT_ID = "KbZUR41cY7W6zRSdpSUJ7I7mLYBKOCmB"  # gitleaks:allow public OAuth client id


@dataclass
class LocalCursorAuth:
    access_token: str
    # field(default_factory=str) keeps the same "" defaults without string-literal
    # defaults, which the python-hardcoded-secrets pattern flags on the NAME
    # (refresh_token matches its token/secret regex) rather than the value.
    refresh_token: str = field(default_factory=str)
    email: str = field(default_factory=str)
    membership_type: str = field(default_factory=str)


def state_db_path() -> Path:
    return STATE_DB


def read_local_auth() -> LocalCursorAuth | None:
    db = STATE_DB
    if not db.exists():
        return None
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error:
        return None
    try:
        cur = con.cursor()

        def get(key: str) -> str:
            row = cur.execute("SELECT value FROM ItemTable WHERE key = ?", (key,)).fetchone()
            return str(row[0]) if row and row[0] is not None else ""

        access = get("cursorAuth/accessToken")
        if not access:
            return None
        return LocalCursorAuth(
            access_token=access,
            refresh_token=get("cursorAuth/refreshToken"),
            email=get("cursorAuth/cachedEmail"),
            membership_type=get("cursorAuth/stripeMembershipType"),
        )
    finally:
        con.close()


def token_expired(token: str, *, skew_seconds: int = 120) -> bool:
    exp = jwt_exp(token)
    if exp is None:
        return False
    return time.time() >= (exp - skew_seconds)


def refresh_access_token(refresh_token: str) -> tuple[str, str]:
    """Return (access_token, refresh_token) from Cursor oauth refresh."""
    try:
        data = request_json_url(
            "POST",
            OAUTH_TOKEN_URL,
            body={
                "grant_type": "refresh_token",
                "client_id": OAUTH_CLIENT_ID,
                "refresh_token": refresh_token,
            },
            headers={"User-Agent": USER_AGENT},
        )
    except OSError as exc:
        raise RuntimeError(f"Cursor OAuth refresh unreachable: {exc}") from exc
    except HttpJsonError as exc:
        raise RuntimeError(f"Token refresh failed: HTTP {exc.status}: {exc.body[:200]}") from exc
    except RuntimeError as exc:
        raise RuntimeError("Cursor OAuth refresh returned invalid JSON") from exc
    access = data.get("access_token") or data.get("accessToken")
    refresh = data.get("refresh_token") or data.get("refreshToken") or refresh_token
    if not access:
        raise RuntimeError(f"Token refresh failed: {data}")
    return str(access), str(refresh)


def write_tokens(access_token: str, refresh_token: str) -> None:
    """Best-effort persist refreshed tokens back into Cursor's state DB."""
    if not STATE_DB.exists():
        return
    try:
        con = sqlite3.connect(str(STATE_DB), timeout=5)
        cur = con.cursor()
        cur.execute(
            "INSERT INTO ItemTable(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            ("cursorAuth/accessToken", access_token),
        )
        if refresh_token:
            cur.execute(
                "INSERT INTO ItemTable(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                ("cursorAuth/refreshToken", refresh_token),
            )
        con.commit()
        con.close()
    except sqlite3.Error:
        # Don't break monitoring if Cursor has the DB locked
        return


def resolve_access_token() -> LocalCursorAuth:
    auth = read_local_auth()
    if not auth:
        raise PermissionError(
            "No Cursor IDE login found. Open Cursor and sign in, then retry.\n"
            f"Expected DB: {STATE_DB}"
        )

    if not token_expired(auth.access_token):
        return auth

    if not auth.refresh_token:
        raise PermissionError(
            "Cursor access token expired and no refresh token is available. "
            "Open Cursor and sign in again."
        )

    access, refresh = refresh_access_token(auth.refresh_token)
    write_tokens(access, refresh)
    auth.access_token = access
    auth.refresh_token = refresh
    return auth

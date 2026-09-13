from __future__ import annotations

import json
import sqlite3
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

STATE_DB = Path.home() / ".config" / "Cursor" / "User" / "globalStorage" / "state.vscdb"
OAUTH_TOKEN_URL = "https://api2.cursor.sh/oauth/token"
# Public Cursor desktop OAuth client id (used by the IDE / community tools)
OAUTH_CLIENT_ID = "KbZUR41cY7W6zRSdpSUJ7I7mLYBKOCmB"


@dataclass
class LocalCursorAuth:
    access_token: str
    refresh_token: str = ""
    email: str = ""
    membership_type: str = ""


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


def _jwt_exp(token: str) -> int | None:
    try:
        import base64

        payload = token.split(".")[1]
        pad = "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload + pad))
        exp = data.get("exp")
        return int(exp) if exp is not None else None
    except Exception:
        return None


def token_expired(token: str, *, skew_seconds: int = 120) -> bool:
    exp = _jwt_exp(token)
    if exp is None:
        return False
    return time.time() >= (exp - skew_seconds)


def refresh_access_token(refresh_token: str) -> tuple[str, str]:
    """Return (access_token, refresh_token) from Cursor oauth refresh."""
    body = json.dumps(
        {
            "grant_type": "refresh_token",
            "client_id": OAUTH_CLIENT_ID,
            "refresh_token": refresh_token,
        }
    ).encode()
    req = urllib.request.Request(
        OAUTH_TOKEN_URL,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "cursor-spend-monitor/0.1"},
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        data = json.loads(response.read().decode())
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
        pass


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

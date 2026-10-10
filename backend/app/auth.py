"""Staff authentication: per-user accounts, scrypt password hashes, HttpOnly session cookies."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from typing import Any

from fastapi import Depends, HTTPException, Request, Response

from . import db
from .config import settings

COOKIE = "cb_session"
_SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1, "dklen": 32}
_failures: dict[str, deque[float]] = defaultdict(deque)
MAX_FAILURES, WINDOW_S = 5, 600


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return f"scrypt${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_hex, dk_hex = stored.split("$")
    except ValueError:
        return False
    dk = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), **_SCRYPT)
    return hmac.compare_digest(dk.hex(), dk_hex)


def create_user(username: str, display_name: str, password: str, role: str = "staff") -> int:
    if role not in ("staff", "mp", "admin"):
        raise ValueError("role must be staff, mp or admin")
    if len(password) < 10:
        raise ValueError("password must be at least 10 characters")
    with db.get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO users (username, display_name, role, password_hash, created_at) VALUES (?,?,?,?,?)",
            (username, display_name, role, hash_password(password), db.now_iso()))
        return cur.lastrowid


def _throttled(key: str) -> bool:
    q = _failures[key]
    now = time.monotonic()
    while q and now - q[0] > WINDOW_S:
        q.popleft()
    return len(q) >= MAX_FAILURES


def login(username: str, password: str, response: Response, client_ip: str) -> dict[str, Any]:
    key = f"{username.lower()}|{client_ip}"
    if _throttled(key):
        raise HTTPException(429, "Too many attempts. Try again in a few minutes.")
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ? AND active = 1", (username,)).fetchone()
    if not row or not verify_password(password, row["password_hash"]):
        _failures[key].append(time.monotonic())
        raise HTTPException(401, "Incorrect username or password")
    _failures.pop(key, None)
    token = secrets.token_urlsafe(32)
    with db.get_conn() as conn:
        conn.execute("INSERT INTO sessions (token_hash, user_id, created_at, expires_at) VALUES (?,?,?,?)",
                     (_hash(token), row["id"], db.now_iso(), db.expiry(settings.session_hours)))
    response.set_cookie(COOKIE, token, max_age=settings.session_hours * 3600, httponly=True,
                        secure=settings.cookie_secure, samesite="strict", path="/")
    return _public(row)


def logout(request: Request, response: Response) -> None:
    token = request.cookies.get(COOKIE)
    if token:
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_hash(token),))
    response.delete_cookie(COOKIE, path="/")


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _public(row: Any) -> dict[str, Any]:
    return {"id": row["id"], "username": row["username"], "display_name": row["display_name"],
            "role": row["role"]}


def current_user(request: Request) -> dict[str, Any]:
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401, "Sign in required")
    with db.get_conn() as conn:
        row = conn.execute(
            """SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id
               WHERE s.token_hash = ? AND s.expires_at > ? AND u.active = 1""",
            (_hash(token), db.now_iso())).fetchone()
    if not row:
        raise HTTPException(401, "Session expired - sign in again")
    return _public(row)


def require_admin(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    if user["role"] != "admin":
        raise HTTPException(403, "Only administrators can change the library")
    return user

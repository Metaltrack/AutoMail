"""Users, roles, login sessions and API keys.

Passwords are hashed with PBKDF2 (standard library). Session tokens and API
keys are random strings; only their SHA-256 hash is stored, so a leaked
database does not leak working credentials.
"""
import hashlib
import hmac
import os
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Optional

from fastapi import Header, HTTPException

import db
from logger import logger, log_level

log = logger()
SESSION_DAYS = 7
PBKDF2_ROUNDS = 200_000


@dataclass
class Principal:
    """Whoever is making the request: a logged-in user or an API key."""
    user_id: Optional[int]
    username: str
    role: str                  # admin | sender | app
    api_key_id: Optional[int] = None

    @property
    def is_admin(self):
        return self.role == "admin"


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PBKDF2_ROUNDS).hex()
    return f"pbkdf2${PBKDF2_ROUNDS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, rounds, salt, digest = stored.split("$")
    except ValueError:
        return False
    test = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(rounds)).hex()
    return hmac.compare_digest(test, digest)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def admin_email() -> str:
    return os.getenv("ADMIN_EMAIL", "").strip().lower()


def ensure_admin():
    """Makes sure somebody can become admin.

    With ADMIN_EMAIL set, nothing is created: whoever signs up with that address
    and verifies it (proving they own the mailbox) becomes admin, so no password
    is stored anywhere. Without it, the first account is created from
    ADMIN_PASSWORD, or with a random password printed in the log.
    """
    if admin_email():
        log.log(log_level.INFO, "auth.py", f"Admin is whoever signs up and verifies {admin_email()}.")
        return
    with db.tx() as conn:
        if conn.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            return
        username = os.getenv("ADMIN_USERNAME", "admin")
        password = os.getenv("ADMIN_PASSWORD") or secrets.token_urlsafe(9)
        conn.execute(
            "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, 'admin', ?)",
            (username, hash_password(password), db.now()),
        )
    if os.getenv("ADMIN_PASSWORD"):
        log.log(log_level.WARNING, "auth.py", f"Created admin account '{username}' (password from ADMIN_PASSWORD).")
    else:
        log.log(log_level.WARNING, "auth.py",
                f"Created admin account '{username}' with password: {password}  <- write this down")


# ---------- login throttling (5 failed tries per username per 5 minutes) ----------
_failed = {}
_failed_lock = threading.Lock()


def _too_many_attempts(username: str) -> bool:
    cutoff = time.time() - 300
    with _failed_lock:
        tries = [t for t in _failed.get(username.lower(), []) if t > cutoff]
        _failed[username.lower()] = tries
        return len(tries) >= 5


def _note_failure(username: str):
    with _failed_lock:
        _failed.setdefault(username.lower(), []).append(time.time())


def login(username: str, password: str) -> dict:
    """`username` may also be the account's email address."""
    if _too_many_attempts(username):
        raise HTTPException(429, "Too many failed attempts. Wait 5 minutes and try again.")
    with db.tx() as conn:
        user = conn.execute("SELECT * FROM users WHERE username = ? OR email = ?", (username, username)).fetchone()
        if not user or not verify_password(password, user["password_hash"]):
            _note_failure(username)
            raise HTTPException(401, "Wrong username or password.")
        if not user["email_verified"]:
            raise HTTPException(403, "Please verify your email first. Open the link we sent you.")
        token = secrets.token_urlsafe(32)
        conn.execute("DELETE FROM sessions WHERE expires_at < ?", (db.now(),))
        conn.execute(
            "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
            (sha(token), user["id"], db.now() + SESSION_DAYS * 86400),
        )
    return {"token": token, "user": {"id": user["id"], "username": user["username"], "role": user["role"]}}


def logout(token: str):
    with db.tx() as conn:
        conn.execute("DELETE FROM sessions WHERE token_hash = ?", (sha(token),))


# ---------- sign-up, email verification, password reset ----------

VERIFY_HOURS = 24
RESET_HOURS = 1
_hits = {}
_hits_lock = threading.Lock()


def rate_limit(bucket: str, key: str, limit: int, window_seconds: int):
    """Allows `limit` calls per `key` per window; raises 429 after that."""
    now = time.time()
    k = (bucket, key.lower())
    with _hits_lock:
        if len(_hits) > 5000:  # forget stale keys so the dict can't grow forever
            for old in [x for x, ts in _hits.items() if not ts or ts[-1] < now - 3600]:
                del _hits[old]
        recent = [t for t in _hits.get(k, []) if t > now - window_seconds]
        if len(recent) >= limit:
            raise HTTPException(429, "Too many requests. Please wait a bit and try again.")
        recent.append(now)
        _hits[k] = recent


def _new_token(conn, user_id: int, purpose: str, hours: int) -> str:
    conn.execute("DELETE FROM email_tokens WHERE user_id = ? AND purpose = ?", (user_id, purpose))
    token = secrets.token_urlsafe(32)
    conn.execute("INSERT INTO email_tokens (token_hash, user_id, purpose, expires_at) VALUES (?, ?, ?, ?)",
                 (sha(token), user_id, purpose, db.now() + hours * 3600))
    return token


def _use_token(conn, token: str, purpose: str):
    """Single use: the row is deleted as it is read, so two clicks can't both win."""
    row = conn.execute("DELETE FROM email_tokens WHERE token_hash = ? AND purpose = ? AND expires_at > ?"
                       " RETURNING user_id", (sha(token), purpose, db.now())).fetchone()
    return row["user_id"] if row else None


def signup(username: str, email: str, password: str) -> str:
    """Creates an unverified 'sender' account and returns the verification token."""
    with db.tx() as conn:
        # An account nobody verified holds nothing: it must not block the real owner
        # of that email address or username, and old ones are cleaned up.
        conn.execute("DELETE FROM users WHERE email_verified = 0 AND (created_at < ? OR email = ? OR username = ?)",
                     (db.now() - 2 * 86400, email, username))
        if conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
            raise HTTPException(409, f"The username '{username}' is taken.")
        if conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            raise HTTPException(409, "An account with this email already exists. Try signing in or resetting the password.")
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, role, created_at, email, email_verified)"
            " VALUES (?, ?, 'sender', ?, ?, 0)", (username, hash_password(password), db.now(), email))
        return _new_token(conn, cur.lastrowid, "verify", VERIFY_HOURS)


def verify_email(token: str) -> str:
    with db.tx() as conn:
        user_id = _use_token(conn, token, "verify")
        if not user_id:
            raise HTTPException(400, "This link has expired or was already used. Sign in to get a new one.")
        user = conn.execute("SELECT username, email FROM users WHERE id = ?", (user_id,)).fetchone()
        role = "admin" if admin_email() and user["email"].lower() == admin_email() else None
        conn.execute("UPDATE users SET email_verified = 1, role = COALESCE(?, role) WHERE id = ?", (role, user_id))
        return user["username"]


def resend_verification(identifier: str):
    """Returns (email, token) for an unverified account, else None."""
    with db.tx() as conn:
        user = conn.execute("SELECT id, email FROM users WHERE (email = ? OR username = ?) AND email_verified = 0"
                            " AND email IS NOT NULL", (identifier, identifier)).fetchone()
        if not user:
            return None
        return user["email"], _new_token(conn, user["id"], "verify", VERIFY_HOURS)


def start_reset(email: str):
    """Returns (username, token) for a verified account with this email, else None."""
    with db.tx() as conn:
        user = conn.execute("SELECT id, username FROM users WHERE email = ? AND email_verified = 1", (email,)).fetchone()
        if not user:
            return None
        return user["username"], _new_token(conn, user["id"], "reset", RESET_HOURS)


def reset_password(token: str, password: str):
    with db.tx() as conn:
        user_id = _use_token(conn, token, "reset")
        if not user_id:
            raise HTTPException(400, "This reset link has expired or was already used. Request a new one.")
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(password), user_id))
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))     # sign out everywhere
        conn.execute("DELETE FROM email_tokens WHERE user_id = ?", (user_id,))


def create_api_key(name: str, created_by: int) -> dict:
    key = "am_" + secrets.token_urlsafe(24)
    with db.tx() as conn:
        cur = conn.execute(
            "INSERT INTO api_keys (name, key_hash, prefix, created_by, created_at) VALUES (?, ?, ?, ?, ?)",
            (name, sha(key), key[:8], created_by, db.now()),
        )
    return {"id": cur.lastrowid, "name": name, "key": key, "prefix": key[:8]}


def _from_token(token: str) -> Optional[Principal]:
    with db.tx() as conn:
        row = conn.execute(
            "SELECT u.id, u.username, u.role FROM sessions s JOIN users u ON u.id = s.user_id "
            "WHERE s.token_hash = ? AND s.expires_at > ?", (sha(token), db.now())).fetchone()
    return Principal(row["id"], row["username"], row["role"]) if row else None


def _from_api_key(key: str) -> Optional[Principal]:
    with db.tx() as conn:
        row = conn.execute(
            "SELECT id, name FROM api_keys WHERE key_hash = ? AND revoked = 0", (sha(key),)).fetchone()
        if not row:
            return None
        conn.execute("UPDATE api_keys SET last_used_at = ? WHERE id = ?", (db.now(), row["id"]))
    return Principal(None, f"app:{row['name']}", "app", api_key_id=row["id"])


def _bearer(authorization: Optional[str]) -> Optional[str]:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def current_user(authorization: Optional[str] = Header(default=None)) -> Principal:
    """Logged-in people only (the web UI)."""
    token = _bearer(authorization)
    principal = _from_token(token) if token else None
    if not principal:
        raise HTTPException(401, "Please log in.")
    return principal


def current_admin(authorization: Optional[str] = Header(default=None)) -> Principal:
    principal = current_user(authorization)
    if not principal.is_admin:
        raise HTTPException(403, "Only admins can do this.")
    return principal


def user_or_app(authorization: Optional[str] = Header(default=None),
                x_api_key: Optional[str] = Header(default=None)) -> Principal:
    """Logged-in people, or other programs using an API key."""
    token = _bearer(authorization)
    if token:
        principal = _from_token(token)
        if principal:
            return principal
    if x_api_key:
        principal = _from_api_key(x_api_key)
        if principal:
            return principal
    raise HTTPException(401, "Log in, or send a valid X-API-Key header.")

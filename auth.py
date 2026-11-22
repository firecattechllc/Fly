"""Local-only password login and in-memory browser sessions for FLY.

Do not expose the development HTTP server to the internet. This module
does not provide multi-user access, TLS termination, or SSO.
"""
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from http.cookies import SimpleCookie
from pathlib import Path

AUTH_PATH = Path(os.environ.get("FLY_AUTH_PATH", Path(__file__).parent / "data" / "owner-auth.json"))
COOKIE = "fly_session"
TTL_SECONDS = 8 * 60 * 60
LOCK = threading.RLock()
SESSIONS = {}
FAILED = {}
WORK_FACTOR = 310000


def is_configured():
    return AUTH_PATH.is_file()


def _hash_password(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, WORK_FACTOR)


def create_owner(password):
    if not isinstance(password, str) or not 14 <= len(password) <= 128:
        raise ValueError("Use an owner password of 14 to 128 characters")
    if password.isspace() or password.strip() != password:
        raise ValueError("Do not use leading or trailing whitespace")
    salt = secrets.token_bytes(32)
    record = {"algorithm": "pbkdf2-sha256", "iterations": WORK_FACTOR,
              "salt": salt.hex(), "digest": _hash_password(password, salt).hex()}
    AUTH_PATH.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with LOCK:
        try:
            fd = os.open(str(AUTH_PATH), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise ValueError("Owner setup has already been completed") from None
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as out:
                json.dump(record, out)
                out.flush()
                os.fsync(out.fileno())
        except Exception:
            AUTH_PATH.unlink(missing_ok=True)
            raise
    return make_session()


def verify_password(password):
    if not isinstance(password, str) or len(password) > 128 or not is_configured():
        return False
    try:
        with AUTH_PATH.open("r", encoding="utf-8") as f:
            record = json.load(f)
        if record.get("algorithm") != "pbkdf2-sha256" or record.get("iterations") != WORK_FACTOR:
            return False
        expected = bytes.fromhex(record["digest"])
        actual = _hash_password(password, bytes.fromhex(record["salt"]))
        return hmac.compare_digest(actual, expected)
    except (OSError, ValueError, KeyError, TypeError):
        return False


def make_session():
    sid = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    with LOCK:
        now = time.time()
        for key, value in list(SESSIONS.items()):
            if value["expiry"] <= now:
                SESSIONS.pop(key, None)
        SESSIONS[sid] = {"csrf": csrf, "expiry": now + TTL_SECONDS}
    return sid


def session_for(headers):
    cookie = SimpleCookie()
    try:
        cookie.load(headers.get("Cookie", ""))
        morsel = cookie.get(COOKIE)
        sid = morsel.value if morsel else ""
    except Exception:
        return None
    with LOCK:
        found = SESSIONS.get(sid)
        if not found:
            return None
        if found["expiry"] <= time.time():
            SESSIONS.pop(sid, None)
            return None
        return dict(found)


def end_session(headers):
    cookie = SimpleCookie()
    try:
        cookie.load(headers.get("Cookie", ""))
        morsel = cookie.get(COOKIE)
        if morsel:
            with LOCK:
                SESSIONS.pop(morsel.value, None)
    except Exception:
        pass


def allowed_login(ip):
    now = time.monotonic()
    with LOCK:
        attempts = [x for x in FAILED.get(ip, []) if now - x < 900]
        FAILED[ip] = attempts
        return len(attempts) < 5


def record_failed_login(ip):
    with LOCK:
        FAILED.setdefault(ip, []).append(time.monotonic())


def reset_failed_login(ip):
    with LOCK:
        FAILED.pop(ip, None)


def cookie_header(sid):
    return "{}={}; HttpOnly; SameSite=Strict; Path=/; Max-Age={}".format(COOKIE, sid, TTL_SECONDS)


def expire_cookie_header():
    return "{}=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0".format(COOKIE)

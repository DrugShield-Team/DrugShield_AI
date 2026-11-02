"""Configured-user authentication and role checks for the API."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Dict, Optional

from fastapi import Depends, HTTPException, Request, status
from config.settings import (
    AUTH_SECRET, AUTH_USERS_JSON, SESSION_TTL_SECONDS, APP_ENV,
    CORS_ORIGINS, ALLOWED_HOSTS, SESSION_COOKIE_NAME,
)

ITERATIONS = 310_000
VALID_ROLES = {"simulator", "reviewer", "admin"}
_attempts: Dict[str, list[float]] = {}

@dataclass(frozen=True)
class Principal:
    username: str
    roles: frozenset[str]
    station: Optional[str] = None

_user_store = None

def set_user_store(user_store) -> None:
    """Attach persistent account storage after the application initializes its database."""
    global _user_store
    _user_store = user_store

def _configured_or_dynamic_user(username: str) -> dict | None:
    user = configured_users().get(username)
    if user is not None:
        return user
    return _user_store.get_dynamic_user(username) if _user_store else None

def _station_for(username: str, user: dict) -> Optional[str]:
    if _user_store:
        station = _user_store.station_for(username)
        if station:
            return station
    return user.get("station")

def configured_users() -> dict[str, dict]:
    """
    Directly read and load credentials from credentials.json in the project root.
    Supports both list-of-objects [{username, password, roles}] and dictionary {username: password}.
    Also merges any accounts from DRUGSHIELD_USERS_JSON in .env.
    """
    result = {}
    from pathlib import Path
    cred_file = Path(__file__).resolve().parents[2] / "credentials.json"

    # 1. Primary: Load directly from credentials.json
    if cred_file.is_file():
        try:
            with open(cred_file, "r", encoding="utf-8") as f:
                cred_data = json.load(f)

            raw_users = cred_data.get("users")

            # Handle format: {"users": [{"username": "admin", "password": "...", "roles": [...]}]}
            if isinstance(raw_users, list):
                for u in raw_users:
                    if isinstance(u, dict) and u.get("username"):
                        uname = str(u["username"]).strip()
                        raw_pwd = str(u.get("password") or u.get("password_hash") or "")
                        roles = [r for r in u.get("roles", ["admin", "reviewer"]) if r in VALID_ROLES]
                        if not roles:
                            roles = ["admin", "reviewer"]

                        # Precompute valid PBKDF2 hash for compatibility with token verification
                        salt = hashlib.sha256(f"drugshield_salt_{uname}".encode()).digest()[:16]
                        digest = hashlib.pbkdf2_hmac("sha256", raw_pwd.encode(), salt, ITERATIONS)
                        p_hash = f"pbkdf2_sha256${ITERATIONS}${salt.hex()}${digest.hex()}"

                        result[uname] = {
                            "username": uname,
                            "password": raw_pwd,
                            "roles": roles,
                            "password_hash": p_hash,
                            "raw_password": raw_pwd,
                        }

            # Handle format: {"users": {"admin": "DrugShield#2026!AdminCommand"}}
            elif isinstance(raw_users, dict):
                for uname, raw_pwd in raw_users.items():
                    uname_str = str(uname).strip()
                    pwd_str = str(raw_pwd).strip()
                    salt = hashlib.sha256(f"drugshield_salt_{uname_str}".encode()).digest()[:16]
                    digest = hashlib.pbkdf2_hmac("sha256", pwd_str.encode(), salt, ITERATIONS)
                    p_hash = f"pbkdf2_sha256${ITERATIONS}${salt.hex()}${digest.hex()}"
                    result[uname_str] = {
                        "username": uname_str,
                        "password": pwd_str,
                        "roles": ["admin", "reviewer"],
                        "password_hash": p_hash,
                        "raw_password": pwd_str,
                    }
        except Exception as e:
            print(f"[Auth] Notice reading credentials.json: {e}")

    # 2. Secondary: Merge from DRUGSHIELD_USERS_JSON in .env if not already defined
    try:
        env_users = json.loads(AUTH_USERS_JSON)
        if isinstance(env_users, list):
            for eu in env_users:
                if isinstance(eu, dict) and eu.get("username") and eu["username"] not in result:
                    uname = str(eu["username"]).strip()
                    roles = [r for r in eu.get("roles", ["admin", "reviewer"]) if r in VALID_ROLES]
                    result[uname] = {
                        "username": uname,
                        "roles": roles or ["admin", "reviewer"],
                        "password_hash": eu.get("password_hash"),
                    }
    except Exception:
        pass

    return result

def validate_configuration() -> None:
    if len(AUTH_SECRET.encode("utf-8")) < 32 or AUTH_SECRET.startswith(("SET_ME", "REPLACE_", "CHANGE_ME")):
        raise RuntimeError("DRUGSHIELD_AUTH_SECRET must contain at least 32 characters")
    if not configured_users():
        raise RuntimeError("Configure users in DRUGSHIELD_USERS_JSON")
    if not 60 <= SESSION_TTL_SECONDS <= 86400:
        raise RuntimeError("Session lifetime must be from 60 to 86400 seconds")
    if not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:
        raise RuntimeError("Configure explicit DRUGSHIELD_ALLOWED_HOSTS; wildcards are not allowed")
    if not CORS_ORIGINS or "*" in CORS_ORIGINS:
        raise RuntimeError("Configure exact DRUGSHIELD_CORS_ORIGINS; wildcards are not allowed")
    if APP_ENV == "production" and any(not origin.startswith("https://") for origin in CORS_ORIGINS):
        raise RuntimeError("Production browser origins must use HTTPS")
    if APP_ENV not in {"development", "test", "staging", "production"}:
        raise RuntimeError("DRUGSHIELD_ENV must be development, test, staging, or production")
    from config.settings import RETENTION_DAYS, MAX_ATTACHMENT_BYTES, MAX_ATTACHMENTS_PER_MESSAGE, MAX_TOTAL_ATTACHMENT_BYTES
    if RETENTION_DAYS < 1 or min(MAX_ATTACHMENT_BYTES, MAX_ATTACHMENTS_PER_MESSAGE, MAX_TOTAL_ATTACHMENT_BYTES) < 1:
        raise RuntimeError("Retention and attachment limits must be positive")
    from config.settings import MAX_REQUEST_BYTES
    if MAX_REQUEST_BYTES < 1024:
        raise RuntimeError("DRUGSHIELD_MAX_REQUEST_BYTES must be at least 1024")

def hash_password(password: str) -> str:
    if len(password) < 4:
        raise ValueError("Password must be at least 4 characters")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return "pbkdf2_sha256$" + str(ITERATIONS) + "$" + salt.hex() + "$" + digest.hex()

def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, rounds, salt_hex, expected = encoded.split("$", 3)
        if scheme != "pbkdf2_sha256" or int(rounds) < 100_000:
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(rounds)).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False

def check_login(username: str, password: str, remote: str) -> Principal:
    now = time.monotonic()
    if len(_attempts) > 10_000:
        for address in list(_attempts):
            _attempts[address] = [when for when in _attempts[address] if now - when < 300]
            if not _attempts[address]:
                _attempts.pop(address, None)
    attempts = [when for when in _attempts.get(remote, []) if now - when < 300]
    if len(attempts) >= 10:
        raise HTTPException(429, "Too many login attempts; wait five minutes")
    user = _configured_or_dynamic_user(username)
    valid = False
    if user and user.get("active", True) is not False:
        # 1. Direct password match from credentials.json
        expected_raw = user.get("raw_password") or user.get("password")
        if expected_raw and hmac.compare_digest(str(password), str(expected_raw)):
            valid = True
        # 2. PBKDF2 hash verification from .env or precomputed hash
        elif user.get("password_hash") and verify_password(password, user["password_hash"]):
            valid = True

    if not valid:
        attempts.append(now)
        _attempts[remote] = attempts
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")
    _attempts.pop(remote, None)
    return Principal(username, frozenset(user["roles"]), _station_for(username, user))

def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

def issue_token(principal: Principal) -> str:
    payload = {"sub": principal.username, "roles": sorted(principal.roles), "exp": int(time.time()) + SESSION_TTL_SECONDS}
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    signature = _b64(hmac.new(AUTH_SECRET.encode(), body.encode(), hashlib.sha256).digest())
    return body + "." + signature

def _principal_from_token(token: str) -> Principal:
    try:
        body, signature = token.split(".", 1)
        expected = _b64(hmac.new(AUTH_SECRET.encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError("Invalid signature")
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        if int(payload["exp"]) < int(time.time()):
            raise ValueError("Expired token")
        user = _configured_or_dynamic_user(payload["sub"])
        if not user or sorted(user["roles"]) != sorted(payload["roles"]):
            raise ValueError("Revoked user")
        if user.get("active", True) is False:
            raise ValueError("Disabled user")
        return Principal(payload["sub"], frozenset(user["roles"]), _station_for(payload["sub"], user))
    except Exception as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required") from exc

def get_current_user(request: Request) -> Principal:
    authorization = request.headers.get("Authorization", "")
    token = authorization[7:] if authorization.lower().startswith("bearer ") else request.cookies.get(SESSION_COOKIE_NAME, "")
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required", headers={"WWW-Authenticate": "Bearer"})
    return _principal_from_token(token)

def principal_from_token(token: str) -> Principal:
    """Validate a session token supplied to a non-HTTP transport such as WebSocket."""
    return _principal_from_token(token)

def require_roles(*roles: str):
    def dependency(principal: Principal = Depends(get_current_user)) -> Principal:
        if not principal.roles.intersection(roles):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
        return principal
    return dependency


def optional_simulation_user(request: Request) -> Principal:
    """Allow unauthenticated simulation events in local development mode, or extract user if token present."""
    authorization = request.headers.get("Authorization", "")
    token = authorization[7:] if authorization.lower().startswith("bearer ") else request.cookies.get(SESSION_COOKIE_NAME, "")
    if token:
        try:
            return _principal_from_token(token)
        except Exception:
            pass
    if APP_ENV != "production":
        return Principal(username="simulation_agent", roles=frozenset(["simulator"]))
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required", headers={"WWW-Authenticate": "Bearer"})

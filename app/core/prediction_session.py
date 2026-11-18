"""Server-side operator session for browser-triggered model predictions.

The server-to-server PREDICTION_API_TOKEN must never be returned to, or used
by, a browser.  The browser holds only a short-lived HttpOnly session cookie.
"""

import base64
import hashlib
import hmac
import os
import re
import secrets
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

from fastapi import HTTPException, Request, Response

COOKIE_NAME = "__Host-cnc_prediction_session"
SESSION_AGE_SECONDS = 900
MIN_PBKDF2_ITERATIONS = 300_000


@dataclass(frozen=True)
class OperatorConfig:
    username: str
    password_hash: str
    signing_key: bytes
    origin: str
    host: str


def _enabled() -> None:
    if os.getenv("PREDICTION_API_ENABLED", "0") != "1":
        raise HTTPException(503, "Prediction API is disabled")


def _config() -> OperatorConfig:
    _enabled()
    username = os.getenv("PREDICTION_OPERATOR_USERNAME", "")
    password_hash = os.getenv("PREDICTION_OPERATOR_PASSWORD_HASH", "")
    signing_key = os.getenv("PREDICTION_SESSION_SECRET", "").encode("utf-8")
    origin = os.getenv("PREDICTION_BROWSER_ORIGIN", "")
    parsed = urlsplit(origin)
    if (
        not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", username)
        or len(signing_key) < 32
        or parsed.scheme != "https"
        or not parsed.netloc
        or parsed.path not in ("", "/")
        or parsed.query or parsed.fragment
        or origin != f"https://{parsed.netloc}"
    ):
        raise HTTPException(503, "Prediction browser authentication is not configured")
    _parse_password_hash(password_hash)  # Validate configuration before accepting sessions.
    return OperatorConfig(username, password_hash, signing_key, origin, parsed.netloc)


def _parse_password_hash(value: str) -> tuple[int, bytes, bytes]:
    try:
        algorithm, iterations_str, salt_hex, digest_hex = value.split("$")
        iterations = int(iterations_str)
        salt, digest = bytes.fromhex(salt_hex), bytes.fromhex(digest_hex)
        if (
            algorithm != "pbkdf2_sha256"
            or not MIN_PBKDF2_ITERATIONS <= iterations <= 2_000_000
            or len(salt) < 16 or len(digest) != 32
        ):
            raise ValueError("Invalid password hash parameters")
        return iterations, salt, digest
    except (ValueError, TypeError) as exc:
        raise HTTPException(503, "Prediction password hash is not configured") from exc


def _check_origin(request: Request, config: OperatorConfig) -> None:
    """Require an explicitly permitted HTTPS browser origin (CSRF protection)."""
    if (
        request.headers.get("origin") != config.origin
        or request.headers.get("host") != config.host
    ):
        raise HTTPException(403, "Prediction origin is not allowed")


def _check_password(config: OperatorConfig, username: str, password: str) -> None:
    iterations, salt, expected = _parse_password_hash(config.password_hash)
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    if not (secrets.compare_digest(username, config.username) and secrets.compare_digest(candidate, expected)):
        raise HTTPException(401, "Invalid operator credentials")


def _sign_cookie(config: OperatorConfig) -> str:
    expires = int(time.time()) + SESSION_AGE_SECONDS
    message = f"v1|{config.username}|{expires}|{secrets.token_hex(16)}".encode("utf-8")
    encoded = base64.urlsafe_b64encode(message).rstrip(b"=").decode("ascii")
    signature = hmac.new(config.signing_key, encoded.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def _verify_cookie(config: OperatorConfig, cookie: str | None) -> bool:
    if not cookie or len(cookie) > 512:
        return False
    try:
        encoded, signature = cookie.split(".")
        if len(signature) != 64:
            return False
        expected = hmac.new(config.signing_key, encoded.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            return False
        raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode("utf-8")
        version, username, expires_str, nonce = raw.split("|")
        expires = int(expires_str)
        return (
            version == "v1"
            and username == config.username
            and len(nonce) == 32
            and int(time.time()) < expires <= int(time.time()) + SESSION_AGE_SECONDS
        )
    except (UnicodeError, ValueError, TypeError):
        return False


def login_operator(request: Request, response: Response, *, username: str, password: str) -> dict:
    config = _config()
    _check_origin(request, config)
    _check_password(config, username, password)
    response.set_cookie(
        COOKIE_NAME, _sign_cookie(config),
        max_age=SESSION_AGE_SECONDS, path="/", httponly=True, secure=True, samesite="strict",
    )
    response.headers["Cache-Control"] = "no-store"
    return {"authenticated": True, "expires_in_seconds": SESSION_AGE_SECONDS}


def operator_session_exists(request: Request) -> bool:
    config = _config()
    return _verify_cookie(config, request.cookies.get(COOKIE_NAME))


def require_operator_session(request: Request) -> None:
    _enabled()
    cookie = request.cookies.get(COOKIE_NAME)
    # Preserve the existing 401 behaviour for unauthenticated callers even
    # when the optional browser-login feature has not been configured.
    if not cookie:
        raise HTTPException(401, "Operator login required")
    config = _config()
    _check_origin(request, config)
    if not _verify_cookie(config, cookie):
        raise HTTPException(401, "Operator login required")


def logout_operator(request: Request, response: Response) -> dict:
    config = _config()
    _check_origin(request, config)
    response.delete_cookie(COOKIE_NAME, path="/", secure=True, httponly=True, samesite="strict")
    response.headers["Cache-Control"] = "no-store"
    return {"authenticated": False}

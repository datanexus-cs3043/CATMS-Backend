import logging
import time
import hmac
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

import jwt
from argon2 import PasswordHasher, Type
from argon2.exceptions import VerifyMismatchError, InvalidHashError
import bcrypt

from app.core.config import settings

logger = logging.getLogger("medsync.auth.security")

# Initialize Argon2id password hasher (RFC 9106 recommended parameters)
ph = PasswordHasher(
    time_cost=3,
    memory_cost=65536,  # 64 MB
    parallelism=4,
    hash_len=32,
    salt_len=16,
    type=Type.ID
)


# ==========================================
# 1. Password Hashing & Verification
# ==========================================

def get_password_hash(password: str) -> str:
    """Hashes a plain-text password using Argon2id."""
    return ph.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verifies a plain-text password against a stored hash.
    Supports Argon2id and standard bcrypt hashes.
    """
    if not hashed_password or not plain_password:
        return False

    # Check for Argon2 hash format
    if hashed_password.startswith("$argon2"):
        try:
            return ph.verify(hashed_password, plain_password)
        except (VerifyMismatchError, InvalidHashError):
            return False
        except Exception:
            return False

    # Check for Bcrypt hash format
    if hashed_password.startswith("$2a$") or hashed_password.startswith("$2b$") or hashed_password.startswith("$2y$"):
        try:
            return bcrypt.checkpw(
                plain_password.encode("utf-8"),
                hashed_password.encode("utf-8")
            )
        except Exception:
            return False

    # Plain-text check strictly restricted to development/testing environments
    if settings.ENVIRONMENT.lower() in ("development", "dev", "test", "local"):
        if hmac.compare_digest(plain_password, hashed_password):
            logger.warning(
                "Authentication succeeded using plain-text password fallback in development mode. "
                "Please migrate stored passwords to Argon2id hashes."
            )
            return True

    return False


# ==========================================
# 2. JWT Creation & Verification
# ==========================================

def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Generates a signed JWT containing safe claims.
    Do NOT pass passwords, hashes, or sensitive health data here.
    """
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    })

    encoded_jwt = jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt


def decode_access_token(token: str) -> Dict[str, Any]:
    """
    Decodes and verifies a JWT token.
    Raises jwt.PyJWTError (e.g. ExpiredSignatureError, InvalidTokenError) on failure.
    """
    return jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM]
    )


# ==========================================
# 3. CSRF Token Generation & Verification
# ==========================================

def generate_csrf_token(user_identifier: str = "guest") -> str:
    """
    Generates a signed, time-limited CSRF token.
    Format: payload.signature where payload is hex(timestamp:user_identifier:random_salt)
    """
    timestamp = str(int(time.time()))
    salt = secrets.token_hex(8)
    raw_payload = f"{user_identifier}:{timestamp}:{salt}"
    payload_hex = raw_payload.encode("utf-8").hex()

    signature = hmac.new(
        settings.CSRF_SECRET_KEY.encode("utf-8"),
        payload_hex.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    return f"{payload_hex}.{signature}"


def verify_csrf_token(csrf_token: str, max_age_seconds: int = 7200) -> bool:
    """
    Verifies the HMAC signature and timestamp validity of a CSRF token.
    """
    if not csrf_token or "." not in csrf_token:
        return False

    try:
        payload_hex, signature = csrf_token.split(".", 1)
        expected_signature = hmac.new(
            settings.CSRF_SECRET_KEY.encode("utf-8"),
            payload_hex.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(signature, expected_signature):
            return False

        raw_payload = bytes.fromhex(payload_hex).decode("utf-8")
        parts = raw_payload.split(":")
        if len(parts) < 3:
            return False

        timestamp = int(parts[1])
        now = int(time.time())

        # Check token expiration
        if (now - timestamp) > max_age_seconds or timestamp > (now + 300):
            return False

        return True
    except Exception:
        return False


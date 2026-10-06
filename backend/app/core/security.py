"""
Security helpers: password hashing (bcrypt) and login tokens (JWT).

bcrypt  - a deliberately SLOW one-way hash. We never store the real password,
          only the hash. To check a login we hash the typed password again
          and compare. Slowness makes guessing passwords expensive.
JWT     - JSON Web Token. A signed string the server hands out after login.
          It contains {who you are, your role, when it expires}. The browser
          sends it back with every request, and the server verifies the
          signature with JWT_SECRET. Nobody can edit the token without
          knowing the secret.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt

from ..config import JWT_ALGORITHM, JWT_EXPIRE_MINUTES, JWT_SECRET


def hash_password(plain: str) -> str:
    """Return a salted bcrypt hash (the salt is stored inside the hash string)."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """True if `plain` matches `hashed`. Never raises on bad input."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


# Used when a login email does not exist, so "unknown email" and "wrong password"
# take the same amount of time (otherwise an attacker could discover which
# emails are registered by timing the responses).
DUMMY_HASH = hash_password("dummy-password-for-timing-only-1")


def create_access_token(user_id: int, role: str) -> str:
    """Create a signed JWT for this user. role is 'student' or 'company'."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),                 # "subject": who the token is about
        "role": role,
        "iat": now,                          # issued at
        "exp": now + timedelta(minutes=JWT_EXPIRE_MINUTES),  # expires at
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    """Return the token's payload, or None if it is forged, malformed or expired."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None
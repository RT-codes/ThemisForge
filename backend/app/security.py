import asyncio
import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

from .config import settings

_hasher = PasswordHash.recommended()
_ALGORITHM = "HS256"


async def hash_password(password: str) -> str:
    return await asyncio.to_thread(_hasher.hash, password)


async def verify_password(password: str, hashed: str) -> bool:
    return await asyncio.to_thread(_hasher.verify, password, hashed)


def create_token(user_id: int) -> str:
    expires = datetime.now(UTC) + timedelta(minutes=settings.access_token_minutes)
    return jwt.encode({"sub": str(user_id), "exp": expires}, settings.secret_key, algorithm=_ALGORITHM)


def decode_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[_ALGORITHM])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


def hash_secret(secret: str) -> str:
    # fast on purpose: the secret is 256 random bits, so there is nothing to guess and nothing for a slow hash to protect
    return hashlib.sha256(secret.encode()).hexdigest()


def new_secret() -> tuple[str, str, str]:
    """A random secret (an invite, a webhook address, a control token), its hash (what is looked up) and its last
    characters (what is shown to tell them apart)."""
    secret = secrets.token_urlsafe(32)
    return secret, hash_secret(secret), secret[-6:]

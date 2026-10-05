import base64

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .config import settings


def _fernet() -> Fernet:
    # Derived from THEMIS_SECRET_KEY, so rotating that key makes stored secrets unreadable.
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"themisforge-secrets-v1").derive(
        settings.secret_key.encode()
    )
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token: str) -> str | None:
    """The plaintext, or None when the token was written under a different secret key."""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return None


def hint_for(value: str) -> str:
    """A short, non-reversible tail so the UI can tell keys apart without exposing them."""
    return f"…{value[-4:]}" if len(value) >= 12 else "…"

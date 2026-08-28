"""Symmetric encryption for sensitive DB columns that must be decrypted
later (unlike a password or the password-reset token in
models/password_reset_token.py, which only ever need to be *verified*
against, never read back in plaintext). A per-business Google Calendar
refresh token is the first user of this -- the app has to hand the real
plaintext token to Google's API on every calendar call, so hashing (which
is one-way) can't work here; this needs real, reversible encryption.

Python note for a reader new to Python's cryptography ecosystem: Fernet is
a standard "just works" symmetric encryption recipe (AES under the hood,
with built-in authentication so tampering is detected, not just
confidentiality) -- the same category of tool as `crypto.createCipheriv`
in Node, but with the mode/padding/HMAC choices already made for you
correctly, which is why it's used here instead of hand-assembling AES.
"""

from cryptography.fernet import Fernet, InvalidToken

from .config import settings


class DecryptionError(Exception):
    """Raised when decrypt() is given ciphertext that doesn't verify --
    wrong key (e.g. TOKEN_ENCRYPTION_KEY was rotated) or the value was
    corrupted/tampered with. Callers should treat this as "this stored
    token is no longer usable" (e.g. prompt the business to reconnect
    their calendar), not retry."""


def _fernet() -> Fernet:
    # Built fresh per call rather than once at import time -- settings.
    # token_encryption_key is read here, not cached, so a test that
    # monkeypatches it (see tests) takes effect immediately.
    return Fernet(settings.token_encryption_key.encode())


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise DecryptionError("Stored value could not be decrypted -- wrong key or corrupted data.") from exc

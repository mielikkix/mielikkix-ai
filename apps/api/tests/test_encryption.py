"""core/encryption.py -- symmetric encryption for values the app must read
back in plaintext later (e.g. a per-business Google Calendar refresh
token), unlike a password/reset-token hash which only ever needs
verifying. No real Google account or network call happens here.
"""

import pytest
from cryptography.fernet import Fernet

from app.core import encryption
from app.core.config import settings


def test_round_trips_a_plaintext_value():
    ciphertext = encryption.encrypt("my-refresh-token")
    assert encryption.decrypt(ciphertext) == "my-refresh-token"


def test_ciphertext_does_not_contain_the_plaintext():
    ciphertext = encryption.encrypt("super-secret-value")
    assert "super-secret-value" not in ciphertext


def test_two_encryptions_of_the_same_value_differ():
    # Fernet includes a random IV per call -- same plaintext, different
    # ciphertext each time. Confirms this isn't a naive deterministic
    # cipher (which would leak "these two tokens are the same value" to
    # anyone who can read the column, even without the key).
    a = encryption.encrypt("same-value")
    b = encryption.encrypt("same-value")
    assert a != b
    assert encryption.decrypt(a) == encryption.decrypt(b) == "same-value"


def test_decrypt_raises_on_wrong_key(monkeypatch):
    ciphertext = encryption.encrypt("my-refresh-token")
    monkeypatch.setattr(settings, "token_encryption_key", Fernet.generate_key().decode())

    with pytest.raises(encryption.DecryptionError):
        encryption.decrypt(ciphertext)


def test_decrypt_raises_on_corrupted_ciphertext():
    with pytest.raises(encryption.DecryptionError):
        encryption.decrypt("not-a-real-fernet-token")

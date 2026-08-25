"""
Tests for app/core/config.py's model-level validators. Settings() is
constructed with explicit kwargs (not by relying on the real .env this repo
ships) for exactly the fields each test cares about -- pydantic-settings
gives init kwargs priority over the .env file, so these stay isolated from
whatever this checkout's own .env happens to contain.
"""

import pytest
from pydantic import ValidationError

from app.core.config import Settings

_VALID_SECRET_KEY = "x" * 32


def test_twilio_auth_token_required_outside_debug_when_voice_configured():
    """A Twilio account/number configured with no auth token leaves the
    webhooks unauthenticated (see agents_voice.py's
    _assert_valid_twilio_request) -- must fail startup, not boot silently
    open."""
    with pytest.raises(ValidationError, match="TWILIO_AUTH_TOKEN"):
        Settings(
            secret_key=_VALID_SECRET_KEY,
            debug=False,
            twilio_account_sid="ACfakefakefakefakefakefakefakefake",
            twilio_auth_token="",
            twilio_phone_number="",
        )


def test_twilio_auth_token_not_required_when_voice_not_configured():
    """Most deployments don't have Twilio configured at all yet -- apps/api
    is one shared process for every feature, so this must not block
    startup for everyone else."""
    Settings(
        secret_key=_VALID_SECRET_KEY,
        debug=False,
        twilio_account_sid="",
        twilio_auth_token="",
        twilio_phone_number="",
    )


def test_twilio_auth_token_not_required_in_debug_mode():
    Settings(
        secret_key=_VALID_SECRET_KEY,
        debug=True,
        twilio_account_sid="ACfakefakefakefakefakefakefakefake",
        twilio_auth_token="",
        twilio_phone_number="",
    )

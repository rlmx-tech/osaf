"""Tests for startup configuration validation."""

import pytest
from pydantic import ValidationError

from app.config import MIN_SECRET_KEY_LENGTH, Settings


def _settings(secret_key: str) -> Settings:
    """Build Settings with everything required supplied except the key under test."""
    return Settings(
        secret_key=secret_key,
        postgres_password="test-postgres-password",
    )


def test_accepts_a_strong_secret_key():
    strong = "a" * MIN_SECRET_KEY_LENGTH
    assert _settings(strong).secret_key == strong


def test_rejects_short_secret_key():
    with pytest.raises(ValidationError, match="at least 32 characters"):
        _settings("a" * (MIN_SECRET_KEY_LENGTH - 1))


def test_rejects_empty_secret_key():
    with pytest.raises(ValidationError):
        _settings("")


@pytest.mark.parametrize(
    "placeholder",
    [
        # Shipped in .env.example / deploy/.env.example. Padded past the length
        # floor so the test proves the placeholder check fires on its own rather
        # than being masked by the length check.
        "changeme-generate-strong-secret-padded-out",
        "CHANGEME-GENERATE-STRONG-SECRET-PADDED-OUT",
        "change-me-to-something-real-and-long-enough",
        "your-secret-key-goes-right-here-padding-pad",
        "replace-me-with-a-real-key-padding-padding-",
    ],
)
def test_rejects_placeholder_secret_key(placeholder):
    assert len(placeholder) >= MIN_SECRET_KEY_LENGTH  # not caught by length alone
    with pytest.raises(ValidationError, match="example placeholder"):
        _settings(placeholder)

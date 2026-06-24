"""Unit test configuration for OSAF.

Overrides the session-scoped setup_database and cleanup_db fixtures from
tests/conftest.py with no-ops so unit tests run without PostgreSQL/PostGIS.
"""

import os

# Set env vars before any app imports
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5432")
os.environ.setdefault("POSTGRES_DB", "osaf")
os.environ.setdefault("POSTGRES_USER", "osaf")
os.environ.setdefault("POSTGRES_PASSWORD", "testpassword")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")

import pytest
import pytest_asyncio

# Fix passlib/bcrypt 4.x incompatibility:
# passlib's detect_wrap_bug() sends a 73-byte password to bcrypt, but bcrypt 4.x
# raises ValueError for passwords > 72 bytes. Patch bcrypt.hashpw to silently
# truncate so passlib's wrap-bug detection succeeds without error.
try:
    import bcrypt as _bcrypt_mod
    _orig_hashpw = _bcrypt_mod.hashpw

    def _safe_hashpw(password: bytes, salt: bytes) -> bytes:
        if isinstance(password, bytes) and len(password) > 72:
            password = password[:72]
        return _orig_hashpw(password, salt)

    _bcrypt_mod.hashpw = _safe_hashpw
except Exception:
    pass


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_database():
    """No-op override: unit tests don't require a live database."""
    yield


@pytest_asyncio.fixture(autouse=True)
async def cleanup_db():
    """No-op override: unit tests manage their own state."""
    yield

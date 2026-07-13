"""Test configuration and fixtures for OSAF backend tests.

Requires the Docker Compose stack to be running (PostgreSQL+PostGIS on localhost:5432).
Tests use the same database with table cleanup between tests for isolation.
"""

import os

# Set environment variables BEFORE any app imports
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5432")
os.environ.setdefault("POSTGRES_DB", "osaf")
os.environ.setdefault("POSTGRES_USER", "osaf")
os.environ.setdefault("POSTGRES_PASSWORD", os.environ.get("POSTGRES_PASSWORD", "testpassword"))
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("APP_ENV", "development")

from datetime import date, time
from uuid import UUID

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Base, async_session, engine, get_db
from app.main import app
from app.models import Incident, IncidentAuditLog, IncidentSource, SharkSpecies, User
from app.services.auth_service import create_access_token, hash_password
from app.utils.geo import point_from_coords


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_database():
    """Create all tables at session start, drop at session end."""
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(autouse=True)
async def cleanup_db():
    """Clean all table data after each test for isolation."""
    yield
    async with async_session() as session:
        # Delete in reverse dependency order
        await session.execute(text("DELETE FROM news_items"))
        await session.execute(text("DELETE FROM incident_audit_log"))
        await session.execute(text("DELETE FROM incident_sources"))
        await session.execute(text("DELETE FROM incidents"))
        await session.execute(text("DELETE FROM users"))
        await session.execute(text("DELETE FROM shark_species"))
        await session.commit()


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    """Provide a database session for direct DB operations in tests."""
    async with async_session() as session:
        yield session


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    """Provide an async HTTP test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# --- Helper fixtures ---


@pytest_asyncio.fixture
async def test_user(db: AsyncSession) -> User:
    """Create a standard public user."""
    user = User(
        email="testuser@example.com",
        username="testuser",
        password_hash=hash_password("password123"),
        display_name="Test User",
        role="public",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def admin_user(db: AsyncSession) -> User:
    """Create an admin user."""
    user = User(
        email="admin@example.com",
        username="admin",
        password_hash=hash_password("adminpass123"),
        display_name="Admin User",
        role="admin",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def verified_user(db: AsyncSession) -> User:
    """Create a verified contributor user."""
    user = User(
        email="verified@example.com",
        username="verified_contributor",
        password_hash=hash_password("verifiedpass123"),
        display_name="Verified Contributor",
        role="verified_contributor",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def auth_header(user: User) -> dict[str, str]:
    """Generate Authorization header for a user."""
    token = create_access_token(user.id, user.role)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def sample_incident(db: AsyncSession) -> Incident:
    """Create a sample verified incident with coordinates and a source."""
    incident = Incident(
        case_number="OSAF-2025-0001",
        incident_date=date(2025, 1, 15),
        incident_time=time(10, 30),
        location_description="New Smyrna Beach, Florida",
        country="United States",
        state_province="Florida",
        county_region="Volusia County",
        body_of_water="Atlantic Ocean",
        coordinates=point_from_coords(-80.927, 29.026),
        classification="unprovoked",
        classification_subtype="hit_and_run",
        shark_species_suspected="Carcharhinus limbatus",
        species_identification_method="witness",
        victim_activity="surfing",
        victim_injury_severity="minor",
        victim_injury_description="Lacerations to right foot",
        victim_age=25,
        victim_sex="male",
        fatal=False,
        description="Surfer bitten on foot while waiting for waves.",
        verification_status="verified",
    )
    source = IncidentSource(
        source_type="news_article",
        source_title="Shark bite at New Smyrna Beach",
        source_publisher="Local News",
        source_date=date(2025, 1, 15),
    )
    incident.sources.append(source)
    db.add(incident)
    await db.commit()
    await db.refresh(incident)
    return incident


@pytest_asyncio.fixture
async def sample_species(db: AsyncSession) -> list[SharkSpecies]:
    """Seed a few shark species for testing."""
    species_list = [
        SharkSpecies(
            common_name="Great White Shark",
            scientific_name="Carcharodon carcharias",
            family="Lamnidae",
            danger_rating="high",
            max_size_meters=6.1,
        ),
        SharkSpecies(
            common_name="Tiger Shark",
            scientific_name="Galeocerdo cuvier",
            family="Carcharhinidae",
            danger_rating="high",
            max_size_meters=5.5,
        ),
        SharkSpecies(
            common_name="Bull Shark",
            scientific_name="Carcharhinus leucas",
            family="Carcharhinidae",
            danger_rating="high",
            max_size_meters=3.5,
        ),
    ]
    for sp in species_list:
        db.add(sp)
    await db.commit()
    for sp in species_list:
        await db.refresh(sp)
    return species_list


SAMPLE_INCIDENT_PAYLOAD = {
    "incident_date": "2025-03-15",
    "incident_time": "14:30:00",
    "location_description": "Bondi Beach, south end",
    "country": "Australia",
    "state_province": "New South Wales",
    "body_of_water": "Tasman Sea",
    "coordinates": {"longitude": 151.274, "latitude": -33.891},
    "classification": "unprovoked",
    "classification_subtype": "hit_and_run",
    "shark_species_suspected": "Carcharhinus brachyurus",
    "victim_activity": "swimming",
    "victim_injury_severity": "moderate",
    "victim_age": 30,
    "victim_sex": "female",
    "fatal": False,
    "description": "Swimmer bitten while swimming near shore.",
    "sources": [
        {
            "source_type": "news_article",
            "source_title": "Shark bite at Bondi",
            "source_publisher": "Sydney Morning Herald",
            "source_date": "2025-03-15",
        }
    ],
}

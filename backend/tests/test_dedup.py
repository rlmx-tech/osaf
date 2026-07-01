import pytest
from app.models.incident import Incident
from app.schemas.incident import CoordinatesSchema, IncidentCreate
from app.services.dedup_service import find_duplicate_incident
from app.utils.geo import point_from_coords


async def _add_incident(db, *, case_number, classification="unprovoked", date="2026-06-25",
                        lon=-77.3434, lat=25.0764, date_precision="exact",
                        victim_age=None, victim_sex=None, verification_status="verified"):
    from datetime import date as _d
    y, m, d = (int(x) for x in date.split("-"))
    inc = Incident(
        case_number=case_number, incident_date=_d(y, m, d), date_precision=date_precision,
        location_description="Bahamas", country="Bahamas", location_precision="approximate",
        classification=classification, fatal=False, victim_age=victim_age, victim_sex=victim_sex,
        coordinates=point_from_coords(lon, lat), verification_status=verification_status,
    )
    db.add(inc)
    await db.commit()
    await db.refresh(inc)
    return inc


def _create(**kw):
    base = dict(location_description="Bahamas", country="Bahamas", classification="unprovoked",
                incident_date="2026-06-25", date_precision="exact",
                coordinates=CoordinatesSchema(longitude=-77.3434, latitude=25.0764))
    base.update(kw)
    return IncidentCreate(**base)


@pytest.mark.asyncio
async def test_matches_same_event(db):
    inc = await _add_incident(db, case_number="OSAF-2026-0001")
    match = await find_duplicate_incident(db, _create())
    assert match is not None and match.id == inc.id


@pytest.mark.asyncio
async def test_no_match_when_date_precision_not_exact(db):
    await _add_incident(db, case_number="OSAF-2026-0002")
    assert await find_duplicate_incident(db, _create(date_precision="month")) is None


@pytest.mark.asyncio
async def test_no_match_when_far_apart(db):
    await _add_incident(db, case_number="OSAF-2026-0003")
    # ~1 degree away (>100 km)
    far = _create(coordinates=CoordinatesSchema(longitude=-78.5, latitude=25.0764))
    assert await find_duplicate_incident(db, far) is None


@pytest.mark.asyncio
async def test_victim_age_guard_blocks(db):
    await _add_incident(db, case_number="OSAF-2026-0004", victim_age=12)
    assert await find_duplicate_incident(db, _create(victim_age=40)) is None


@pytest.mark.asyncio
async def test_victim_sex_guard_blocks(db):
    await _add_incident(db, case_number="OSAF-2026-0008", victim_sex="male")
    assert await find_duplicate_incident(db, _create(victim_sex="female")) is None


@pytest.mark.asyncio
async def test_no_match_without_coords(db):
    await _add_incident(db, case_number="OSAF-2026-0005")
    assert await find_duplicate_incident(db, _create(coordinates=None)) is None


@pytest.mark.asyncio
async def test_lowest_case_number_wins(db):
    await _add_incident(db, case_number="OSAF-2026-0009")
    await _add_incident(db, case_number="OSAF-2026-0007")
    match = await find_duplicate_incident(db, _create())
    assert match.case_number == "OSAF-2026-0007"


@pytest.mark.asyncio
async def test_submission_dedup_attaches_source(db, verified_user):
    from app.schemas.incident import IncidentCreate, CoordinatesSchema, SourceCreate
    from app.services.submission_service import SubmissionService
    svc = SubmissionService(db)

    def mk(pub, url):
        return IncidentCreate(
            location_description="Bahamas", country="Bahamas", classification="unprovoked",
            incident_date="2026-06-25", date_precision="exact",
            coordinates=CoordinatesSchema(longitude=-77.3434, latitude=25.0764),
            sources=[SourceCreate(source_type="news_article", source_url=url,
                                  source_title="t", source_publisher=pub)],
        )

    first = await svc.submit_incident(mk("Yahoo", "https://y/1"), verified_user)
    second = await svc.submit_incident(mk("WCIA", "https://w/2"), verified_user)

    # Same incident returned, no new case number
    assert second.case_number == first.case_number
    # Both outlets are now sources on the one incident
    assert len(second.sources) == 2
    pubs = {s.source_publisher for s in second.sources}
    assert pubs == {"Yahoo", "WCIA"}


@pytest.mark.asyncio
async def test_rejected_not_matched(db):
    """A re-report of a rejected incident must NOT merge into the rejected record."""
    await _add_incident(db, case_number="OSAF-2026-0010", verification_status="rejected")
    result = await find_duplicate_incident(db, _create())
    assert result is None


@pytest.mark.asyncio
async def test_submission_distinct_event_creates_new(db, verified_user):
    from app.schemas.incident import IncidentCreate, CoordinatesSchema, SourceCreate
    from app.services.submission_service import SubmissionService
    svc = SubmissionService(db)

    def mk(date, url):
        return IncidentCreate(
            location_description="Bahamas", country="Bahamas", classification="unprovoked",
            incident_date=date, date_precision="exact",
            coordinates=CoordinatesSchema(longitude=-77.3434, latitude=25.0764),
            sources=[SourceCreate(source_type="news_article", source_url=url, source_title="t")],
        )

    a = await svc.submit_incident(mk("2026-06-25", "https://y/1"), verified_user)
    b = await svc.submit_incident(mk("2026-07-04", "https://y/2"), verified_user)  # different date
    assert a.case_number != b.case_number

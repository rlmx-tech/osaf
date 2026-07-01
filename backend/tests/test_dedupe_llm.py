import pytest
from datetime import date, timedelta
from app.models.incident import Incident
import scripts.dedupe_llm as ddl
from scripts.dedupe_llm import candidate_clusters


async def _inc(db, case, d, country="Bahamas", cls="unprovoked"):
    i = Incident(case_number=case, incident_date=d, date_precision="exact",
                 location_description="X", country=country, location_precision="approximate",
                 classification=cls, fatal=False, verification_status="verified")
    db.add(i); await db.commit(); await db.refresh(i)
    return i


@pytest.mark.asyncio
async def test_clusters_within_window(db):
    await _inc(db, "OSAF-1", date(2026, 6, 25))
    await _inc(db, "OSAF-2", date(2026, 6, 26))      # 1 day apart, same country+class
    clusters = await candidate_clusters(db)
    assert len(clusters) == 1 and len(clusters[0]) == 2


@pytest.mark.asyncio
async def test_no_cluster_outside_window(db):
    await _inc(db, "OSAF-1", date(2026, 6, 25))
    await _inc(db, "OSAF-2", date(2026, 7, 10))      # >3 days
    assert await candidate_clusters(db) == []


@pytest.mark.asyncio
async def test_no_cluster_across_classification(db):
    await _inc(db, "OSAF-1", date(2026, 6, 25), cls="unprovoked")
    await _inc(db, "OSAF-2", date(2026, 6, 26), cls="provoked")
    assert await candidate_clusters(db) == []


@pytest.mark.asyncio
async def test_oversize_cluster_skipped(db):
    for n in range(12):
        await _inc(db, f"OSAF-{n:02d}", date(2026, 6, 25) + timedelta(days=n))  # chain within 3d
    assert await candidate_clusters(db, max_cluster=10) == []


# adjudicate() tests

class _I:  # lightweight incident stand-in for adjudicate() (case_number + fields used in prompt)
    def __init__(self, case):
        self.case_number = case
        self.incident_date = date(2026, 6, 25)
        self.location_description = "Bahamas"; self.state_province = None; self.body_of_water = None
        self.latitude = None; self.longitude = None
        self.victim_age = None; self.victim_sex = None; self.victim_activity = None
        self.shark_species_suspected = None; self.description = "d"; self.sources = []


def _async(val):
    async def _c():
        return val
    return _c()


@pytest.mark.asyncio
async def test_adjudicate_valid_group(monkeypatch):
    monkeypatch.setattr(ddl, "_call_ollama", lambda p: _async('{"groups": [["OSAF-1", "OSAF-2"]]}'))
    groups = await ddl.adjudicate([_I("OSAF-1"), _I("OSAF-2"), _I("OSAF-3")])
    assert groups == [["OSAF-1", "OSAF-2"]]


@pytest.mark.asyncio
async def test_adjudicate_drops_hallucinated_case(monkeypatch):
    # OSAF-9 not in the cluster -> dropped; group then has <2 valid -> discarded
    monkeypatch.setattr(ddl, "_call_ollama", lambda p: _async('{"groups": [["OSAF-1", "OSAF-9"]]}'))
    assert await ddl.adjudicate([_I("OSAF-1"), _I("OSAF-2")]) == []


@pytest.mark.asyncio
async def test_adjudicate_no_groups(monkeypatch):
    monkeypatch.setattr(ddl, "_call_ollama", lambda p: _async('{"groups": []}'))
    assert await ddl.adjudicate([_I("OSAF-1"), _I("OSAF-2")]) == []


@pytest.mark.asyncio
async def test_adjudicate_llm_failure(monkeypatch):
    monkeypatch.setattr(ddl, "_call_ollama", lambda p: _async(None))
    assert await ddl.adjudicate([_I("OSAF-1"), _I("OSAF-2")]) == []


@pytest.mark.asyncio
async def test_adjudicate_unparseable_response(monkeypatch):
    # LLM returns non-JSON garbage -> _parse_json_response yields None -> no merge
    monkeypatch.setattr(ddl, "_call_ollama", lambda p: _async("sorry, I cannot help with that"))
    assert await ddl.adjudicate([_I("OSAF-1"), _I("OSAF-2")]) == []

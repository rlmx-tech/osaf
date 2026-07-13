# Attack-Stats Exclusion (SP5) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make all stats aggregates count only genuine shark-on-human bite events, so sightings and other non-attack classifications stop inflating the attack numbers.

**Architecture:** A single `ATTACK_CLASSIFICATIONS` constant plus a `WHERE classification IN (...)` clause added to every aggregate query in `stats_service.py`. No schema change, no migration; Map/Database/News unchanged.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, PostgreSQL, pytest.

## Global Constraints

- `ATTACK_CLASSIFICATIONS = ("unprovoked", "provoked", "boat_bite", "scavenge", "aquaria")` — verbatim. Everything else (`sighting, near_miss, equipment_bite, unverified_report, doubtful, no_assignment, not_confirmed`) is excluded from attack counts.
- Filter applies to EVERY aggregate in `stats_service.py`: overview (total, fatal, top_country, top_species, year range), by_year, by_country, by_species, by_activity, fatality_trends.
- Scope = stats only. Do not touch incident list / map / news / CRUD.
- No schema/migration change. Response shapes unchanged.
- Backend tests: `cd ~/claude/OSAF/backend && POSTGRES_DB=osaf_test .venv/bin/python -m pytest <args>` (PostGIS `osaf_test` on localhost:5432; `backend/.env`).
- Conventional commits; attribution disabled (no Co-Authored-By trailer).

---

## Task 1: Filter all stats aggregates to attack classifications

**Files:**
- Modify: `backend/app/services/stats_service.py`
- Test: `backend/tests/test_stats.py` (append)

**Interfaces:**
- Produces: module constant `ATTACK_CLASSIFICATIONS`; every `StatsService` aggregate counts only rows whose `classification` is in it.

- [ ] **Step 1: Write the failing test** (append to `backend/tests/test_stats.py`)

```python
import pytest
from datetime import date
from app.models.incident import Incident


async def _seed_mix(db):
    # 2 attacks (1 fatal) + 2 sightings + 1 near_miss, same year/country/activity
    rows = [
        Incident(case_number="OSAF-2099-0001", incident_date=date(2099, 1, 1), date_precision="exact",
                 location_description="X", country="Testland", location_precision="approximate",
                 classification="unprovoked", fatal=True, victim_activity="surfing",
                 shark_species_suspected="Carcharodon carcharias", verification_status="verified"),
        Incident(case_number="OSAF-2099-0002", incident_date=date(2099, 1, 2), date_precision="exact",
                 location_description="X", country="Testland", location_precision="approximate",
                 classification="provoked", fatal=False, victim_activity="surfing",
                 shark_species_suspected="Carcharodon carcharias", verification_status="verified"),
        Incident(case_number="OSAF-2099-0003", incident_date=date(2099, 1, 3), date_precision="exact",
                 location_description="X", country="Testland", location_precision="approximate",
                 classification="sighting", fatal=False, victim_activity="swimming",
                 shark_species_suspected="Galeocerdo cuvier", verification_status="verified"),
        Incident(case_number="OSAF-2099-0004", incident_date=date(2099, 1, 4), date_precision="exact",
                 location_description="X", country="Testland", location_precision="approximate",
                 classification="sighting", fatal=False, victim_activity="swimming",
                 shark_species_suspected="Galeocerdo cuvier", verification_status="verified"),
        Incident(case_number="OSAF-2099-0005", incident_date=date(2099, 1, 5), date_precision="exact",
                 location_description="X", country="Testland", location_precision="approximate",
                 classification="near_miss", fatal=False, victim_activity="diving",
                 verification_status="verified"),
    ]
    for r in rows:
        db.add(r)
    await db.commit()


@pytest.mark.asyncio
async def test_overview_counts_attacks_only(db):
    from app.services.stats_service import StatsService
    await _seed_mix(db)
    ov = (await StatsService(db).overview())["data"]
    assert ov["total_incidents"] == 2          # 2 attacks, not 5
    assert ov["total_fatal"] == 1
    assert ov["fatality_rate"] == 50.0


@pytest.mark.asyncio
async def test_breakdowns_exclude_non_attacks(db):
    from app.services.stats_service import StatsService
    await _seed_mix(db)
    svc = StatsService(db)
    by_year = (await svc.by_year())["data"]
    assert sum(r["count"] for r in by_year) == 2
    activities = {r["activity"] for r in (await svc.by_activity())["data"]}
    assert "swimming" not in activities          # sighting activity excluded
    assert "diving" not in activities            # near_miss activity excluded
    assert activities == {"surfing"}
    species = {r["species"] for r in (await svc.by_species())["data"]}
    assert "Galeocerdo cuvier" not in species     # only sightings had tiger shark
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/claude/OSAF/backend && POSTGRES_DB=osaf_test .venv/bin/python -m pytest tests/test_stats.py -k "attacks_only or exclude_non_attacks" -v`
Expected: FAIL — `total_incidents == 5`, activities include swimming/diving.

- [ ] **Step 3: Implement — add the constant + filter every query**

At the top of `backend/app/services/stats_service.py`, after the imports, add:
```python
# Genuine shark-on-human bite events — the only classifications that count as
# "attacks" in stats. Excludes sighting, near_miss, equipment_bite,
# unverified_report, doubtful, no_assignment, not_confirmed.
ATTACK_CLASSIFICATIONS = ("unprovoked", "provoked", "boat_bite", "scavenge", "aquaria")

_ATTACK_FILTER = Incident.classification.in_(ATTACK_CLASSIFICATIONS)
```

Then add `_ATTACK_FILTER` to the WHERE of every query. Full method bodies:

`overview`:
```python
    async def overview(self) -> dict:
        total = (await self.db.execute(
            select(func.count()).select_from(Incident).where(_ATTACK_FILTER)
        )).scalar_one()

        fatal_count = (await self.db.execute(
            select(func.count()).select_from(Incident)
            .where(_ATTACK_FILTER, Incident.fatal.is_(True))
        )).scalar_one()

        top_country = (await self.db.execute(
            select(Incident.country)
            .where(_ATTACK_FILTER)
            .group_by(Incident.country)
            .order_by(func.count().desc())
            .limit(1)
        )).scalar_one_or_none()

        species_label = self._species_label()
        top_species = (await self.db.execute(
            select(species_label)
            .where(_ATTACK_FILTER, species_label.is_not(None))
            .group_by(species_label)
            .order_by(func.count().desc())
            .limit(1)
        )).scalar_one_or_none()

        min_year = (await self.db.execute(
            select(func.min(extract("year", Incident.incident_date))).where(_ATTACK_FILTER)
        )).scalar_one()

        max_year = (await self.db.execute(
            select(func.max(extract("year", Incident.incident_date))).where(_ATTACK_FILTER)
        )).scalar_one()

        year_range = None
        if min_year and max_year:
            year_range = f"{int(min_year)}-{int(max_year)}"

        return {
            "data": {
                "total_incidents": total,
                "total_fatal": fatal_count,
                "fatality_rate": round(fatal_count / total * 100, 1) if total > 0 else 0,
                "most_active_country": top_country,
                "most_common_species": top_species,
                "year_range": year_range,
            }
        }
```

`by_year` — add `_ATTACK_FILTER` to its `.where(...)`:
```python
            .where(_ATTACK_FILTER, Incident.incident_date.is_not(None))
```
`by_country` — add a `.where(_ATTACK_FILTER)` before `.group_by`:
```python
            )
            .where(_ATTACK_FILTER)
            .group_by(Incident.country)
```
`by_species` — extend its where:
```python
            .where(_ATTACK_FILTER, species_label.is_not(None))
```
`by_activity` — extend its where:
```python
            .where(_ATTACK_FILTER, Incident.victim_activity.is_not(None))
```
`fatality_trends` — extend its where:
```python
            .where(_ATTACK_FILTER, Incident.incident_date.is_not(None))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/claude/OSAF/backend && POSTGRES_DB=osaf_test .venv/bin/python -m pytest tests/test_stats.py -v`
Expected: the two new tests PASS and all pre-existing `test_stats.py` tests still pass.

- [ ] **Step 5: Commit**

```bash
cd ~/claude/OSAF
git add backend/app/services/stats_service.py backend/tests/test_stats.py
git commit -m "feat(backend): stats count only attack classifications (exclude sightings)"
```

---

## Task 2: Full-suite check + changelog

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Run the full backend suite**

Run: `cd ~/claude/OSAF/backend && POSTGRES_DB=osaf_test .venv/bin/python -m pytest -q`
Expected: no NEW failures beyond the 6 known pre-existing (`test_register` ×3, `test_login` ×2, `test_create_incident_invalid_classification`).

- [ ] **Step 2: Append CHANGELOG entry** under `## [Unreleased]` → `### Fixed`:

```markdown
- **Stats counted sightings as attacks (SP5).** `StatsService` aggregated over
  every incident regardless of classification, so the ~108 sightings (plus
  near-miss/doubtful/etc.) inflated the headline attack numbers. All aggregates
  (overview total/fatal/fatality-rate, by-year/country/species/activity,
  fatality-trends) now filter to `ATTACK_CLASSIFICATIONS`
  (`unprovoked, provoked, boat_bite, scavenge, aquaria`). Sightings remain in the
  DB and on the Map/Database/News; they just no longer skew the stats.
```

- [ ] **Step 3: Commit**

```bash
cd ~/claude/OSAF
git add CHANGELOG.md
git commit -m "docs: changelog — SP5 attack-stats exclusion"
```

---

## Deployment (after merge — not a subagent task)

Deploy a rebuilt backend image on the production host. Verify `/api/v1/stats/overview` — `total_incidents` should drop by the count of non-attack classifications.

---

## Notes

- If the attack set should shift (e.g., exclude `scavenge`), it's the single `ATTACK_CLASSIFICATIONS` tuple.
- Frontend stat labels still read "incidents"; the numbers now mean attacks. Copy tweak is optional and out of scope.

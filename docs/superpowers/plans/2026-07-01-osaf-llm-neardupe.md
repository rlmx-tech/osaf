# LLM Near-Duplicate Merge (SP4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A scheduled backend batch job that uses the LLM to merge same-event duplicate incidents SP3's deterministic signature misses (drifted date/coords).

**Architecture:** SP3's per-cluster merge is refactored into a shared `merge_cluster`. A new `scripts/dedupe_llm.py` blocks candidate incidents by `(country, classification)` within a ±3-day window, asks glm-5.2:cloud which are the same event, and merges confirmed groups via `merge_cluster`. Dry-run default; nightly cron after a manual first validation.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, PostgreSQL+PostGIS, httpx (Ollama Cloud), pytest.

## Global Constraints

- Runs in the **backend container** (direct DB, transactional). LLM = Ollama Cloud via `httpx`.
- Block by `(country, classification)` + transitive **±3-day** date window; coords NOT a block key; cluster size cap **10** (larger → skipped, logged). Same-classification only (no cross-classification merges).
- **Guardrails:** LLM uses ONLY provided data; groups ONLY clearly-same events; defaults to NOT grouping; returned case numbers **allowlisted to the cluster's own** (drop hallucinated); groups with <2 valid members discarded; any LLM error/parse failure → skip cluster (never merge on uncertainty).
- Merge reuses SP3 machinery: canonical = **lowest case number**, enrich canonical from absorbed non-null fields, move sources (dedup by URL), delete absorbed `backfill:*` news + re-point others, `IncidentAuditLog(action="merged_llm")`, delete absorbed. Per-cluster transaction; idempotent.
- **Dry-run default**, `--apply` gated.
- New backend settings: `OLLAMA_URL` (default `https://ollama.com`), `OLLAMA_API_KEY` (default ""), `OLLAMA_MODEL` (default `glm-5.2:cloud`). Add `httpx` to backend deps.
- No schema/migration change. Backend tests: `cd ~/claude/OSAF/backend && POSTGRES_DB=osaf_test .venv/bin/python -m pytest <args>`. Conventional commits; no Co-Authored-By.

---

## File Structure
- Modify `backend/app/services/dedup_service.py` — add `_ENRICH_FIELDS`, `_enrich`, `_would_fill`, `merge_cluster` (moved from the script).
- Modify `backend/scripts/dedupe_incidents.py` — use the shared helpers (behavior unchanged).
- Create `backend/app/services/llm.py` — `_call_ollama`, `_parse_json_response`.
- Modify `backend/app/config.py` — `OLLAMA_*` settings. Modify `backend/pyproject.toml` — add `httpx`.
- Create `backend/scripts/dedupe_llm.py` — `candidate_clusters`, `adjudicate`, `run`, CLI.
- Tests: `backend/tests/test_merge_cluster.py`, `test_llm.py`, `test_dedupe_llm.py`.

---

## Task 1: Refactor SP3 merge into shared `merge_cluster`

**Files:**
- Modify: `backend/app/services/dedup_service.py`
- Modify: `backend/scripts/dedupe_incidents.py`
- Test: `backend/tests/test_merge_cluster.py`

**Interfaces:**
- Produces: `merge_cluster(db, incident_ids: list[UUID], action: str) -> int` (merges into lowest-case canonical, commits, returns absorbed count); `_would_fill(canonical, absorbed) -> list[str]` (pure, no mutation); `_enrich`, `_ENRICH_FIELDS`.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_merge_cluster.py`:
```python
import pytest
from datetime import date
from sqlalchemy import select
from app.models.incident import Incident
from app.models.news import NewsItem
from app.models.source import IncidentSource
from app.utils.geo import point_from_coords
from app.services.dedup_service import merge_cluster, _would_fill


async def _inc(db, case, url, pub, desc=None, age=None):
    i = Incident(case_number=case, incident_date=date(2026, 6, 25), date_precision="exact",
                 location_description="Bahamas", country="Bahamas", location_precision="approximate",
                 classification="unprovoked", fatal=False, description=desc, victim_age=age,
                 coordinates=point_from_coords(-77.34, 25.07), verification_status="verified")
    i.sources.append(IncidentSource(source_type="news_article", source_url=url, source_publisher=pub))
    db.add(i); await db.commit(); await db.refresh(i)
    db.add(NewsItem(dedup_key=f"backfill:{i.id}", source_platform="web_scrape", source_name=pub,
                    source_url=url, title=f"t {pub}", event_type="attack", promoted_incident_id=i.id))
    await db.commit()
    return i


@pytest.mark.asyncio
async def test_merge_cluster_merges_into_lowest_case(db):
    a = await _inc(db, "OSAF-2026-0002", "https://w/2", "WCIA", desc=None, age=12)
    b = await _inc(db, "OSAF-2026-0005", "https://y/5", "Yahoo", desc="Fuller account.", age=None)
    n = await merge_cluster(db, [a.id, b.id], "merged_llm")
    assert n == 1
    incs = (await db.execute(select(Incident))).scalars().all()
    assert len(incs) == 1 and incs[0].case_number == "OSAF-2026-0002"   # lowest case kept
    assert incs[0].description == "Fuller account."                      # enriched from absorbed
    pubs = {s.source_publisher for s in (await db.execute(select(IncidentSource))).scalars().all()}
    assert pubs == {"WCIA", "Yahoo"}                                     # sources merged
    assert len((await db.execute(select(NewsItem))).scalars().all()) == 1  # backfill news collapsed


def test_would_fill_is_pure():
    class F:  # minimal stand-ins
        pass
    canon = F(); absorbed = F()
    for f in ["description", "victim_age", "victim_sex", "victim_name", "body_of_water",
              "state_province", "county_region", "incident_time", "classification_subtype",
              "provocation_subtype", "shark_species_confirmed", "shark_species_suspected",
              "shark_size_estimate", "species_identification_method", "victim_activity",
              "victim_injury_severity", "victim_injury_description"]:
        setattr(canon, f, None); setattr(absorbed, f, None)
    canon.fatal = False; absorbed.fatal = True
    canon.description = None; absorbed.description = "x"
    filled = _would_fill(canon, absorbed)
    assert "description" in filled and "fatal" in filled
    assert canon.description is None   # pure: not mutated
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/claude/OSAF/backend && POSTGRES_DB=osaf_test .venv/bin/python -m pytest tests/test_merge_cluster.py -v`
Expected: FAIL — `cannot import name 'merge_cluster'`.

- [ ] **Step 3: Add the shared helpers to `dedup_service.py`**

Add these imports to `backend/app/services/dedup_service.py` (merge into existing lines):
```python
from sqlalchemy import cast, delete, func, select, update
from app.models.news import NewsItem
```
(It already imports `IncidentAuditLog`, `IncidentSource`, `Incident`.)

Append to `backend/app/services/dedup_service.py`:
```python
_ENRICH_FIELDS = [
    "incident_time", "state_province", "county_region", "body_of_water",
    "classification_subtype", "provocation_subtype", "shark_species_confirmed",
    "shark_species_suspected", "shark_size_estimate", "species_identification_method",
    "victim_activity", "victim_injury_severity", "victim_injury_description",
    "victim_age", "victim_sex", "victim_name", "description",
]


def _would_fill(canonical, absorbed) -> list[str]:
    """Field names that would be filled on canonical from absorbed (no mutation)."""
    filled = [f for f in _ENRICH_FIELDS
              if getattr(canonical, f) is None and getattr(absorbed, f) is not None]
    if absorbed.fatal and not canonical.fatal:
        filled.append("fatal")
    return filled


def _enrich(canonical, absorbed) -> list[str]:
    """Fill canonical's NULL fields from absorbed's non-null values. Returns filled names."""
    filled: list[str] = []
    for f in _ENRICH_FIELDS:
        if getattr(canonical, f) is None and getattr(absorbed, f) is not None:
            setattr(canonical, f, getattr(absorbed, f))
            filled.append(f)
    if absorbed.fatal and not canonical.fatal:
        canonical.fatal = True
        filled.append("fatal")
    return filled


async def merge_cluster(db, incident_ids, action: str) -> int:
    """Merge the given incidents into the lowest-case-number canonical. Commits.
    Moves sources (dedup by URL), prunes absorbed backfill news + re-points others,
    enriches canonical, audit-logs, deletes absorbed. Returns absorbed count."""
    rows = (
        await db.execute(
            select(Incident).where(Incident.id.in_(incident_ids)).order_by(Incident.case_number.asc())
        )
    ).scalars().all()
    if len(rows) < 2:
        return 0
    canonical = rows[0]
    canon_urls = {
        s.source_url
        for s in (
            await db.execute(select(IncidentSource).where(IncidentSource.incident_id == canonical.id))
        ).scalars().all()
        if s.source_url
    }
    absorbed_count = 0
    for inc in rows[1:]:
        srcs = (
            await db.execute(select(IncidentSource).where(IncidentSource.incident_id == inc.id))
        ).scalars().all()
        for s in srcs:
            if s.source_url and s.source_url in canon_urls:
                await db.execute(delete(IncidentSource).where(IncidentSource.id == s.id))
            else:
                await db.execute(
                    update(IncidentSource).where(IncidentSource.id == s.id).values(incident_id=canonical.id)
                )
                if s.source_url:
                    canon_urls.add(s.source_url)
        await db.execute(
            delete(NewsItem).where(
                NewsItem.promoted_incident_id == inc.id, NewsItem.dedup_key.like("backfill:%")
            )
        )
        await db.execute(
            update(NewsItem).where(NewsItem.promoted_incident_id == inc.id).values(
                promoted_incident_id=canonical.id
            )
        )
        db.add(IncidentAuditLog(incident_id=canonical.id, action=action,
                                notes=f"Absorbed duplicate {inc.case_number}"))
        if _enrich(canonical, inc):
            db.add(canonical)
        await db.execute(delete(Incident).where(Incident.id == inc.id))
        absorbed_count += 1
    await db.commit()
    return absorbed_count
```

- [ ] **Step 4: Update `dedupe_incidents.py` to use the shared helpers**

In `backend/scripts/dedupe_incidents.py`: delete its local `_ENRICH_FIELDS` and `_enrich`; import from the service:
```python
from app.services.dedup_service import _victim_conflict, _would_fill, merge_cluster
```
Replace the body of the `for ids in await _clusters(db):` loop's merge section so it uses `merge_cluster` on apply and `_would_fill` for dry-run reporting:
```python
        for ids in await _clusters(db):
            rows = (
                await db.execute(
                    select(Incident).where(Incident.id.in_(ids)).order_by(Incident.case_number.asc())
                )
            ).scalars().all()
            if len(rows) < 2:
                continue
            canonical = rows[0]
            absorbed = [inc for inc in rows[1:] if not _victim_conflict(canonical, _as_create(inc))]
            if not absorbed:
                continue
            clusters += 1
            if apply:
                merged += await merge_cluster(db, [canonical.id] + [i.id for i in absorbed], "merged")
            else:
                for inc in absorbed:
                    print(f"  merge {inc.case_number} -> {canonical.case_number}")
                    wf = _would_fill(canonical, inc)
                    if wf:
                        print(f"    would fill from {inc.case_number}: {', '.join(wf)}")
                    merged += 1
```
Remove the now-unused imports from `dedupe_incidents.py` (`delete`, `update`, `NewsItem`, `IncidentSource`, `IncidentAuditLog` — keep only what the file still uses: `Numeric, func, select`, `ST_X/ST_Y`, `Incident`, `async_session`, `_as_create`'s deps). Verify with the test run.

- [ ] **Step 5: Run tests**

Run: `cd ~/claude/OSAF/backend && POSTGRES_DB=osaf_test .venv/bin/python -m pytest tests/test_merge_cluster.py tests/test_dedupe_script.py -v`
Expected: new merge_cluster tests PASS and all SP3 `test_dedupe_script.py` tests still PASS (refactor preserved behavior).

- [ ] **Step 6: Commit**

```bash
cd ~/claude/OSAF
git add backend/app/services/dedup_service.py backend/scripts/dedupe_incidents.py backend/tests/test_merge_cluster.py
git commit -m "refactor(backend): extract shared merge_cluster for reuse by LLM dedup"
```

---

## Task 2: Backend Ollama client + settings

**Files:**
- Create: `backend/app/services/llm.py`
- Modify: `backend/app/config.py`, `backend/pyproject.toml`
- Test: `backend/tests/test_llm.py`

**Interfaces:**
- Produces: `async _call_ollama(prompt: str) -> str | None`; `_parse_json_response(text: str) -> dict | None`. Settings `ollama_url`, `ollama_api_key`, `ollama_model`.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_llm.py`:
```python
from app.services.llm import _parse_json_response


def test_parse_plain_json():
    assert _parse_json_response('{"groups": [["A", "B"]]}') == {"groups": [["A", "B"]]}


def test_parse_markdown_fenced():
    txt = "Here you go:\n```json\n{\"groups\": []}\n```\n"
    assert _parse_json_response(txt) == {"groups": []}


def test_parse_embedded_braces():
    assert _parse_json_response('noise {"groups": [["X"]]} trailing') == {"groups": [["X"]]}


def test_parse_garbage_returns_none():
    assert _parse_json_response("not json at all") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/claude/OSAF/backend && POSTGRES_DB=osaf_test .venv/bin/python -m pytest tests/test_llm.py -v`
Expected: FAIL — `No module named 'app.services.llm'`.

- [ ] **Step 3: Add settings + deps + module**

In `backend/app/config.py`, add to `Settings` (after `cors_origins`):
```python
    # Ollama Cloud (used by the LLM near-dupe batch job)
    ollama_url: str = "https://ollama.com"
    ollama_api_key: str = ""
    ollama_model: str = "glm-5.2:cloud"
    ollama_timeout: int = 300
```

In `backend/pyproject.toml`, add `"httpx>=0.28",` to the main `dependencies` list (backend prod image currently lacks httpx).

Create `backend/app/services/llm.py`:
```python
"""Ollama Cloud client for backend batch jobs (LLM near-dupe adjudication)."""

import json
import logging
import re

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


async def _call_ollama(prompt: str) -> str | None:
    headers: dict[str, str] = {}
    if settings.ollama_api_key:
        headers["Authorization"] = f"Bearer {settings.ollama_api_key}"
    try:
        async with httpx.AsyncClient(timeout=settings.ollama_timeout) as client:
            resp = await client.post(
                f"{settings.ollama_url}/api/generate",
                headers=headers,
                json={
                    "model": settings.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "think": False,
                    "options": {"temperature": 0.1, "num_predict": 2048},
                },
            )
            resp.raise_for_status()
            return resp.json().get("response", "")
    except httpx.HTTPError:
        logger.exception("llm: ollama request failed")
        return None


def _parse_json_response(text: str) -> dict | None:
    """Extract a JSON object from an LLM response (plain, fenced, or embedded)."""
    text = (text or "").strip()
    try:
        val = json.loads(text)
        return val if isinstance(val, dict) else None
    except json.JSONDecodeError:
        pass
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if m:
        try:
            val = json.loads(m.group(1).strip())
            return val if isinstance(val, dict) else None
        except json.JSONDecodeError:
            pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            val = json.loads(text[start : end + 1])
            return val if isinstance(val, dict) else None
        except json.JSONDecodeError:
            pass
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/claude/OSAF/backend && POSTGRES_DB=osaf_test .venv/bin/python -m pytest tests/test_llm.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/claude/OSAF
git add backend/app/services/llm.py backend/app/config.py backend/pyproject.toml backend/tests/test_llm.py
git commit -m "feat(backend): Ollama Cloud client + settings for batch LLM jobs"
```

---

## Task 3: Candidate blocking

**Files:**
- Create: `backend/scripts/dedupe_llm.py` (partial — `candidate_clusters`)
- Test: `backend/tests/test_dedupe_llm.py`

**Interfaces:**
- Produces: `async candidate_clusters(db, window_days=3, max_cluster=10) -> list[list[Incident]]`.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_dedupe_llm.py`:
```python
import pytest
from datetime import date, timedelta
from app.models.incident import Incident
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/claude/OSAF/backend && POSTGRES_DB=osaf_test .venv/bin/python -m pytest tests/test_dedupe_llm.py -k cluster -v`
Expected: FAIL — `No module named 'scripts.dedupe_llm'`.

- [ ] **Step 3: Create `dedupe_llm.py` with `candidate_clusters`**

`backend/scripts/dedupe_llm.py`:
```python
"""LLM-adjudicated near-duplicate incident merge (batch).

Blocks candidates by (country, classification) within a +/-N-day window, asks the
LLM which are the same real-world event, and merges confirmed groups via the shared
merge_cluster. Deterministic exact-signature dupes are already handled by
dedupe_incidents.py; this catches near-dupes (drifted date/coords).

Dry-run by default; pass --apply to perform merges.
    python -m scripts.dedupe_llm [--apply] [--window N]
"""

import asyncio
import json
import sys
from itertools import groupby

from sqlalchemy import select

from app.database import async_session
from app.models.incident import Incident
from app.services.dedup_service import merge_cluster
from app.services.llm import _call_ollama, _parse_json_response


async def candidate_clusters(db, window_days: int = 3, max_cluster: int = 10):
    """Groups of >=2 incidents sharing (country, classification) within a transitive
    +/-window_days date chain. Clusters larger than max_cluster are skipped (logged)."""
    incs = (
        await db.execute(
            select(Incident)
            .where(Incident.date_precision == "exact", Incident.incident_date.isnot(None))
            .order_by(Incident.country, Incident.classification, Incident.incident_date)
        )
    ).scalars().all()

    clusters: list[list[Incident]] = []
    for _key, grp in groupby(incs, key=lambda i: (i.country, i.classification)):
        cur: list[Incident] = []
        for inc in grp:
            if not cur:
                cur = [inc]
            elif (inc.incident_date - cur[-1].incident_date).days <= window_days:
                cur.append(inc)
            else:
                if len(cur) >= 2:
                    clusters.append(cur)
                cur = [inc]
        if len(cur) >= 2:
            clusters.append(cur)

    out = []
    for c in clusters:
        if len(c) > max_cluster:
            print(f"  [skip] cluster of {len(c)} in {c[0].country}/{c[0].classification} > max {max_cluster}")
        else:
            out.append(c)
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/claude/OSAF/backend && POSTGRES_DB=osaf_test .venv/bin/python -m pytest tests/test_dedupe_llm.py -k cluster -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/claude/OSAF
git add backend/scripts/dedupe_llm.py backend/tests/test_dedupe_llm.py
git commit -m "feat(backend): candidate blocking for LLM near-dupe job"
```

---

## Task 4: LLM adjudication + guardrails

**Files:**
- Modify: `backend/scripts/dedupe_llm.py` (add `_build_prompt`, `adjudicate`)
- Test: `backend/tests/test_dedupe_llm.py` (append)

**Interfaces:**
- Consumes: `_call_ollama`, `_parse_json_response` (Task 2).
- Produces: `_build_prompt(cluster) -> str`; `async adjudicate(cluster) -> list[list[str]]` (validated same-event case-number groups; allowlisted; ≥2 members).

- [ ] **Step 1: Write the failing tests** (append to `backend/tests/test_dedupe_llm.py`)

```python
import scripts.dedupe_llm as ddl


class _I:  # lightweight incident stand-in for adjudicate() (case_number + fields used in prompt)
    def __init__(self, case):
        self.case_number = case
        self.incident_date = date(2026, 6, 25)
        self.location_description = "Bahamas"; self.state_province = None; self.body_of_water = None
        self.latitude = None; self.longitude = None
        self.victim_age = None; self.victim_sex = None; self.victim_activity = None
        self.shark_species_suspected = None; self.description = "d"; self.sources = []


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


def _async(val):
    async def _c():
        return val
    return _c()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/claude/OSAF/backend && POSTGRES_DB=osaf_test .venv/bin/python -m pytest tests/test_dedupe_llm.py -k adjudicate -v`
Expected: FAIL — `module 'scripts.dedupe_llm' has no attribute 'adjudicate'`.

- [ ] **Step 3: Add `_build_prompt` + `adjudicate` to `dedupe_llm.py`**

```python
_PROMPT_HEADER = (
    "You are deduplicating shark incident records. The incidents below are close in "
    "time and share a country and classification. Identify which records describe the "
    "SAME real-world event (same victim, location, and circumstances) — typically the "
    "same event reported by different outlets.\n\n"
    "Rules:\n"
    "- Use ONLY the data provided below. Do not use outside knowledge.\n"
    "- Group records ONLY if they clearly describe the same event. When unsure, do NOT group.\n"
    "- A record that is its own distinct event must not appear in any group.\n"
    "- Respond with ONLY valid JSON: {\"groups\": [[\"CASE\", \"CASE\"], ...]}. "
    "Use the exact case_number strings. Omit singletons. If none match, return {\"groups\": []}.\n\n"
    "INCIDENTS:\n"
)


def _build_prompt(cluster) -> str:
    items = [
        {
            "case_number": inc.case_number,
            "date": str(inc.incident_date),
            "location": inc.location_description,
            "state": inc.state_province,
            "body_of_water": inc.body_of_water,
            "lat": inc.latitude, "lon": inc.longitude,
            "victim_age": inc.victim_age, "victim_sex": inc.victim_sex,
            "activity": inc.victim_activity, "species": inc.shark_species_suspected,
            "description": (inc.description or "")[:500],
            "source_titles": [getattr(s, "source_title", None) for s in getattr(inc, "sources", [])][:5],
        }
        for inc in cluster
    ]
    return _PROMPT_HEADER + json.dumps(items, default=str, indent=2)


async def adjudicate(cluster) -> list[list[str]]:
    """Return LLM-confirmed same-event groups of case numbers (allowlisted, >=2)."""
    resp = await _call_ollama(_build_prompt(cluster))
    if not resp:
        return []
    data = _parse_json_response(resp)
    if not data:
        return []
    valid = {inc.case_number for inc in cluster}
    out: list[list[str]] = []
    for group in data.get("groups", []) or []:
        if not isinstance(group, list):
            continue
        members = list(dict.fromkeys(c for c in group if c in valid))  # allowlist + de-dup, keep order
        if len(members) >= 2:
            out.append(members)
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/claude/OSAF/backend && POSTGRES_DB=osaf_test .venv/bin/python -m pytest tests/test_dedupe_llm.py -k adjudicate -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/claude/OSAF
git add backend/scripts/dedupe_llm.py backend/tests/test_dedupe_llm.py
git commit -m "feat(backend): LLM adjudication + guardrails for near-dupe grouping"
```

---

## Task 5: `run` + CLI + end-to-end

**Files:**
- Modify: `backend/scripts/dedupe_llm.py` (add `run` + `__main__`)
- Test: `backend/tests/test_dedupe_llm.py` (append)

**Interfaces:**
- Produces: `async run(apply: bool, window_days: int = 3) -> dict` → `{clusters_examined, llm_groups, incidents_merged}`; CLI `python -m scripts.dedupe_llm [--apply] [--window N]`.

- [ ] **Step 1: Write the failing test** (append)

```python
@pytest.mark.asyncio
async def test_run_merges_confirmed_group(db, monkeypatch):
    a = await _inc(db, "OSAF-2026-0001", date(2026, 6, 25))
    b = await _inc(db, "OSAF-2026-0002", date(2026, 6, 26))  # near-dupe (1 day)

    async def fake_adjudicate(cluster):
        return [[i.case_number for i in cluster]]  # LLM says: same event
    monkeypatch.setattr(ddl, "adjudicate", fake_adjudicate)

    dry = await ddl.run(apply=False)
    assert dry["llm_groups"] == 1
    assert len((await db.execute(select(Incident))).scalars().all()) == 2  # dry-run: unchanged

    applied = await ddl.run(apply=True)
    assert applied["incidents_merged"] == 1
    incs = (await db.execute(select(Incident))).scalars().all()
    assert len(incs) == 1 and incs[0].case_number == "OSAF-2026-0001"


@pytest.mark.asyncio
async def test_run_no_groups_no_merge(db, monkeypatch):
    await _inc(db, "OSAF-2026-0001", date(2026, 6, 25))
    await _inc(db, "OSAF-2026-0002", date(2026, 6, 26))
    monkeypatch.setattr(ddl, "adjudicate", lambda c: _async([]))
    applied = await ddl.run(apply=True)
    assert applied["incidents_merged"] == 0
    assert len((await db.execute(select(Incident))).scalars().all()) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/claude/OSAF/backend && POSTGRES_DB=osaf_test .venv/bin/python -m pytest tests/test_dedupe_llm.py -k run -v`
Expected: FAIL — `module 'scripts.dedupe_llm' has no attribute 'run'`.

- [ ] **Step 3: Add `run` + CLI**

```python
async def run(apply: bool, window_days: int = 3) -> dict:
    examined = 0
    llm_groups = 0
    merged = 0
    async with async_session() as db:
        clusters = await candidate_clusters(db, window_days=window_days)
        for cluster in clusters:
            examined += 1
            for group in await adjudicate(cluster):
                llm_groups += 1
                canonical = min(group)
                print(f"  LLM same-event group: {', '.join(sorted(group))} -> canonical {canonical}")
                if apply:
                    ids = [inc.id for inc in cluster if inc.case_number in group]
                    merged += await merge_cluster(db, ids, "merged_llm")
    print(
        f"dedupe_llm: {'APPLIED' if apply else 'DRY-RUN'} — "
        f"clusters_examined={examined}, llm_groups={llm_groups}, incidents_merged={merged}"
    )
    return {"clusters_examined": examined, "llm_groups": llm_groups, "incidents_merged": merged}


if __name__ == "__main__":
    _apply = "--apply" in sys.argv
    _window = 3
    if "--window" in sys.argv:
        _window = int(sys.argv[sys.argv.index("--window") + 1])
    asyncio.run(run(apply=_apply, window_days=_window))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/claude/OSAF/backend && POSTGRES_DB=osaf_test .venv/bin/python -m pytest tests/test_dedupe_llm.py -v`
Expected: all PASS (cluster + adjudicate + run).

- [ ] **Step 5: Commit**

```bash
cd ~/claude/OSAF
git add backend/scripts/dedupe_llm.py backend/tests/test_dedupe_llm.py
git commit -m "feat(backend): dedupe_llm run (dry-run default) + CLI"
```

---

## Task 6: Full-suite check + changelog

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Run the full backend suite**

Run: `cd ~/claude/OSAF/backend && POSTGRES_DB=osaf_test .venv/bin/python -m pytest -q`
Expected: no NEW failures beyond the 6 known pre-existing.

- [ ] **Step 2: Append CHANGELOG entry** under `## [Unreleased]` → `### Added`:

```markdown
- **LLM near-duplicate merge (SP4).** A backend batch job
  (`scripts/dedupe_llm.py`, dry-run default, `--apply`) catches same-event
  duplicate incidents the deterministic signature misses (drifted date/coords).
  It blocks candidates by `(country, classification)` within a ±3-day window,
  asks glm-5.2:cloud which records are the same real-world event (guardrailed:
  data-only, conservative, case-number allowlist), and merges confirmed groups
  via the shared `merge_cluster` (audit `action="merged_llm"`). Run first pass
  manually (dry-run → review → apply), then nightly cron. Spec/plan:
  `docs/superpowers/specs/2026-07-01-osaf-llm-neardupe-design.md`,
  `docs/superpowers/plans/2026-07-01-osaf-llm-neardupe.md`.
```

- [ ] **Step 3: Commit**

```bash
cd ~/claude/OSAF
git add CHANGELOG.md
git commit -m "docs: changelog — SP4 LLM near-dupe merge"
```

---

## Deployment (after merge — not a subagent task)

On CT 102: add `OLLAMA_URL`, `OLLAMA_API_KEY`, `OLLAMA_MODEL` to `/opt/osaf/.env` (reuse the collector's Ollama key), then `git pull` and **rebuild** the backend image (httpx dep + scripts baked):
`docker compose -f docker-compose.yml up -d --build backend`. Run the first pass manually: `docker compose -f docker-compose.yml exec -T backend python -m scripts.dedupe_llm` (dry-run) → review the proposed groups → `--apply`. Then add a nightly host cron: `docker compose -f docker-compose.yml exec -T backend python -m scripts.dedupe_llm --apply`.

---

## Notes / deviations

- `merge_cluster` lives in `app/services/dedup_service.py` (imported by both scripts + already imported by the incident/submission services), keeping merge logic in one reviewed place.
- `dedupe_llm` does NOT apply the victim guard (the LLM's judgment supersedes for near-dupes); `dedupe_incidents` keeps its victim guard when forming clusters before calling `merge_cluster`.
- Backend gains `httpx` as a runtime dep (was collector-only); the deploy rebuilds the backend image for it.

# OSAF — Incident Deduplication (SP3)

**Date:** 2026-07-01
**Status:** Approved design (pre-implementation)
**Scope:** Backend. Prevent and clean up duplicate incidents created when multiple news outlets cover the same real-world event, and collapse the Shark News feed to one row per event.

---

## Problem

Syndicated coverage of one shark event (e.g., a Bahamas attack carried by Yahoo, WCIA, WFLA, KOIN, …) produces **one incident per outlet**. The collector dedups only by **source URL** (`dedup_key = "{platform}:{url}"`), so different URLs for the same event are treated as new incidents. The AI `is_duplicate_likely` check only compares an extraction against its own article text — it never checks the existing incident database.

Observed on prod (CT 102): two records for the same Jun 25 Bahamas attack (OSAF-2026-6574 Yahoo / OSAF-2026-6568 WCIA) with **identical coordinates** (25.0764, −77.3434). A conservative "same date + identical coords" scan finds **202 clusters / ~288 excess incidents** out of 6,587. The SP2 feed backfill (one `news_item` per incident) surfaced these duplicates prominently.

## Goal

1. **Prevention:** stop new duplicate incidents — same-event coverage attaches as additional sources to the existing incident.
2. **Feed:** show one row per event in Shark News.
3. **Cleanup:** merge the existing duplicate incidents into canonical records (preserving all outlet sources), safely (dry-run first, audit-logged).

## Non-Goals (SP3)

- LLM-based same-event adjudication — documented as a future layer; SP3 is deterministic-signature only.
- Deduping fuzzy cases the strict signature misses (different geocoded coords, non-exact dates) — left separate (safe).
- Any schema/migration change — none needed.
- Merging historical GSAF month-precision clusters — deliberately excluded by the `date_precision='exact'` guard.

---

## Matching: the event signature

Two incidents are the **same event** when ALL hold:
- `date_precision == 'exact'` AND `incident_date` is not null (excludes month/year-precision historical data → avoids false merges),
- both have coordinates AND they are within **150 m** (`ST_DWithin` on `geography`; syndicated stories geocode from the same location string to identical points, so this is conservative),
- same `classification`,
- **victim guard:** NOT a match if both have `victim_age` and they differ, or both have `victim_sex` and they differ. (Absent values don't block.)

Deterministic, explainable, no AI. Anything not meeting all criteria stays a separate incident (safe default).

---

## Components

### 1. `backend/app/services/dedup_service.py` (new)
- `async find_duplicate_incident(db, data: IncidentCreate) -> Incident | None` — returns an existing incident matching the signature of `data`, else `None`.
- If `data.date_precision != 'exact'`, `data.incident_date is None`, or `data.coordinates is None` → return `None` immediately (no dedup).
- Query: incidents with same `incident_date` and `classification`, `ST_DWithin(coordinates::geography, point::geography, 150)`; apply the victim guard in Python (or SQL); return the match with the **lowest case number** or `None`.

### 2. Prevention hook (modify `submission_service.py` + `incident_service.py`)
Both `SubmissionService.submit_incident` and `IncidentService.create_incident` call `find_duplicate_incident(db, data)` before creating. On match:
- Append `data.sources` to the existing incident as new `IncidentSource` rows, skipping any whose `source_url` already exists on that incident.
- Add an `IncidentAuditLog` row: `action="source_merged"`, `notes` naming the merged outlet(s) and origin case (if any).
- Commit and return the **existing** incident's `IncidentResponse` — no new incident, no new case number.
On no match: current behavior unchanged.
A shared private helper (e.g., `_attach_sources_to_incident(db, incident, sources, actor)`) avoids duplicating the merge logic across the two services.

### 3. Feed collapse (modify `news_service.py::list_news`)
Return **one row per event** for promoted items:
- Promoted rows (`promoted_incident_id IS NOT NULL`): `DISTINCT ON (promoted_incident_id)`, keeping the newest `captured_at`.
- General rows (`promoted_incident_id IS NULL`): all kept.
- Union, order by `captured_at DESC`, paginate. `meta.total` reflects the collapsed count.
This makes the feed correct even before cleanup runs, and keeps it correct as the live collector captures multiple articles per event. Existing filters (event_type/country/search/date) still apply.

### 4. `backend/scripts/dedupe_incidents.py` (new, one-off)
- Clusters incidents by the strict signature (same `incident_date` [exact precision], rounded coords ~3 dp ≈ 111 m — the practical batch-clustering equivalent of prevention's 150 m radius, same `classification`, victim guard).
- Per cluster (>1): canonical = **lowest case number**. For each absorbed incident:
  - move its `incident_sources` to the canonical (skip duplicate URLs),
  - re-point `news_items.promoted_incident_id` from absorbed → canonical,
  - delete the absorbed incident's `backfill:*` `news_item` (feed collapses; read-side collapse also covers this),
  - `IncidentAuditLog` (`action="merged"`, notes absorbed case number) on the canonical,
  - delete the absorbed incident.
- **Dry-run by default** — prints each cluster (canonical case + absorbed cases + row counts + total to be merged). `--apply` performs the merges inside a transaction. Idempotent (re-run after apply finds nothing).

---

## Testing

Backend (`pytest`, `osaf_test` DB):
- `find_duplicate_incident`: matches same-signature; returns None when `date_precision != 'exact'`; returns None when coords >150 m apart; victim-age/sex guard blocks a mismatch; None when no coords.
- Prevention: submitting a second same-event incident (via the service) attaches its source to the first, creates **no** new incident, returns the original case number, and writes a `source_merged` audit row; a genuinely different event still creates a new incident.
- `list_news`: two promoted news_items on the same incident collapse to one feed row; general news not collapsed; pagination/total correct.
- `dedupe_incidents`: seed a 2-incident cluster (+ sources + backfill news_items) → dry-run reports it and changes nothing; `--apply` merges (sources moved+deduped, news collapsed, audit written, absorbed incident gone); re-run apply is a no-op.

No migration. Coverage bar: new modules ≥80%.

---

## Build order

1. `dedup_service.find_duplicate_incident` + tests.
2. Shared `_attach_sources_to_incident` helper + wire into `submission_service` (+ `incident_service`) + tests.
3. `list_news` feed collapse + tests.
4. `dedupe_incidents.py` script + tests.
5. Deploy to CT 102 (pull + rebuild backend), run cleanup dry-run → `--apply`, verify feed.

## Risks

- **False merges:** mitigated by the exact-date-precision + 150 m + classification + victim guards; strict by design (misses some true dupes rather than merging distinct events). LLM layer can catch the remainder later.
- **Case-number churn:** canonical = lowest case number, so surviving numbers are the earliest; absorbed numbers retire (audit-logged).
- **Feed `DISTINCT ON` + pagination:** must compute `total` on the collapsed set (count of distinct promoted incidents + general rows) so paging is correct.
- **Cleanup on prod data:** dry-run gate + per-merge audit log + single transaction; run during low traffic.

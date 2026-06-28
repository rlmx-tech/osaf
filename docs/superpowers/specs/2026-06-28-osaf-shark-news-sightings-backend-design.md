# OSAF — Shark News + Sightings Capture Backend (SP1)

**Date:** 2026-06-28
**Status:** Approved design (pre-implementation)
**Scope:** Sub-project 1 of 2. Backend + collector + data model only. The public "Shark News" feed page and frontend map/stats surfacing are **SP2** (separate spec).

---

## Problem

OSAF is missing real-world shark events. The trigger case was a YouTube sighting
(https://youtu.be/Vw_bQq-Siwc?t=367) that the collector never captured. Root cause is structural, not model quality:

1. The collector's extractor has a single `is_relevant` gate. Anything that isn't a bite/attack is judged "not relevant" and dropped.
2. A **sighting** (shark observed, nobody bitten) does not map to OSAF's attack-centric incident model, so a correct classifier *will* discard it.
3. There is **no capture store**. `state.py` is a JSON dedup ledger — when an item is skipped it records only `{skipped: true, reason}` and the actual content is discarded. Missed items leave no trace.

Swapping the human reviewer for a smarter model (glm-5.2) does not fix this — the model would also correctly judge a sighting as "not an incident." The fix is to (a) **expand OSAF's mission to track sightings as data** and (b) **persist everything shark-related** so nothing is silently lost.

## Goal

Expand OSAF to capture and track shark **sightings** as first-class data, and persist **all** shark-related content the pollers find into a queryable store that will back a public news feed (SP2). AI (glm-5.2) auto-promotes qualifying items with no human in the loop.

## Non-Goals (SP1)

- The public "Shark News" feed **page** / UI — SP2.
- Map legend, DB table, and stats changes to display sightings — SP2 (backend already serves them via existing endpoints).
- New poller sources — out of scope; existing pollers feed the new path.
- Replacing `state.py`'s JSON dedup ledger — left as-is to avoid risk.

---

## Architecture: two-tier capture-then-promote

```
RawItem (poller)
  │
  ▼
[dedup check — state.py]  ── seen ──▶ skip
  │ new
  ▼
GATE 1: shark-relevant?  (cheap keyword/regex pre-filter)
  │ no ──▶ mark_skipped("not_shark")   (truly off-topic, dropped)
  │ yes
  ▼
UPSERT news_items  (idempotent on dedup_key)   ◀── nothing shark-related is ever lost
  │
  ▼
GATE 2: discrete event?  (AI — glm-5.2)
  ├─ "news"     ──▶ news-only; mark_seen; done   (research/policy/documentary/aggregation)
  ├─ "attack"   ──▶ extract incident fields, promote
  └─ "sighting" ──▶ extract sighting fields, promote
                       │
                       ▼
              confidence + verify (existing logic, unchanged)
                       │
                       ▼
              submit ──▶ incidents row (auto-published)
                       │
                       ▼
              PATCH news_item.promoted_incident_id
```

`news_items` holds **everything shark-related** (the feed). `incidents` holds only the
promotable subset (attacks + sightings), linked back via `promoted_incident_id`.
The two stores are cleanly decoupled.

---

## Data model

### New table: `news_items`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `dedup_key` | String, **unique, not null** | `"{platform}:{source_url}"` — same as `RawItem.dedup_key`; idempotent inserts |
| `source_platform` | String, not null | youtube / reddit / twitter / news_rss / web_scrape |
| `source_name` | String, not null | feed / channel name |
| `source_url` | Text, not null | canonical link |
| `title` | Text, not null | |
| `summary` | Text, nullable | description / snippet / transcript excerpt |
| `author` | String, nullable | publisher / channel |
| `image_url` | Text, nullable | thumbnail for SP2 feed cards; pollers fill when available |
| `published_at` | timestamptz, nullable | from source |
| `captured_at` | timestamptz, not null, default now | ingestion time |
| `event_type` | String, not null | gate-2 result: `attack` / `sighting` / `news` |
| `country` | String, nullable | AI-extracted; feed location filtering |
| `ai_confidence` | float, nullable | gate-2 confidence |
| `promoted_incident_id` | UUID FK → incidents.id, nullable | set when promoted |

Constraints / indexes:
- `CHECK (event_type IN ('attack','sighting','news'))`
- `UNIQUE (dedup_key)`
- Index on `captured_at DESC` (feed ordering)
- Index on `event_type`
- Index on `country`

This table is **purely additive**. No change to `state.py`.

### Sightings: no schema change to `incidents`

A sighting is an `incidents` row with `classification = 'sighting'`. The schema already
supports this:
- The `incidents.classification` CHECK constraint already includes `'sighting'`
  (alongside `near_miss`, `equipment_bite`, `unverified_report`).
- `collector/config.py` `VALID_CLASSIFICATIONS` already includes `'sighting'`.
- Victim fields, `fatal`, coordinates, and time are all already nullable.

A sighting is **who/what/where/when minus the victim**: extract `incident_date`,
`location_description`, `country`, `state_province`, `coordinates`, and
`shark_species_suspected`; leave victim/injury/`fatal` null.

**Implementation verification required:** confirm the backend incident create
schema (`app/schemas/incident.py`) and the `/incidents` route accept
`classification='sighting'` with null victim fields. The DB CHECK allows it; verify
Pydantic validation does too.

---

## Pipeline & extractor changes

### `collector/models.py` — `ExtractedIncident`
- Add `event_type: str` with values `"attack" | "sighting" | "news"`. This supersedes
  the binary relevance decision. (`is_relevant=False` now means "not shark at all" and
  the item is dropped before extraction; it is not stored.)
- For `event_type="sighting"`: extractor sets `classification="sighting"` and leaves
  victim/injury/`fatal` null while still extracting date/location/country/coords/species.

### `collector/pipeline.py` — `process_items`
- After dedup, run **GATE 1** (keyword pre-filter). Pass → upsert `news_items` via the
  new `NewsClient`. Fail → `mark_skipped("not_shark")`.
- Run **GATE 2** (AI). `news` → mark_seen, done. `attack`/`sighting` → existing
  extract → confidence → verify → submit path.
- On successful submit, PATCH the news row's `promoted_incident_id`.
- Extend `stats` dict with `captured_news`, `promoted_sighting`, `promoted_attack`,
  `skipped_not_shark`.

### Gate 1 — keyword pre-filter
A fast regex/keyword screen over `title + summary`: `shark`, common species names
(reuse `COMMON_TO_SCIENTIFIC` keys), and event terms (`bite`, `attack`, `sighting`,
`encounter`, `spotted`, `beach closed`, ...). Since pollers already query shark terms,
most items pass; this just removes obvious off-topic noise before spending AI tokens.

### Prompt guardrails (extend existing OSAF AI rules)
- Gate 2 prompt defines the three categories explicitly:
  - *attack* = physical contact with a person or vessel.
  - *sighting* = a shark observed by people with no bite/contact.
  - *news* = general coverage (research, policy, documentary, aggregated lists) — neither.
- Preserve existing anti-hallucination rules: extract only what is stated, null for
  unknowns, 4000-char truncation, curly-brace escaping.

---

## API surface

### New: `app/api/v1/news.py`
- `POST /api/v1/news` — **collector-authenticated**. Upserts a `news_item`
  (idempotent on `dedup_key`; on conflict, update `event_type`, `ai_confidence`, and
  `promoted_incident_id`). Returns row id. Promotion linking reuses this same upsert
  (second POST with `promoted_incident_id` set) — there is no separate PATCH endpoint.
- `GET /api/v1/news` — **public**. Filters: `event_type`, `country`,
  `source_platform`, `date_from`, `date_to`, `search`, `page`, `per_page`.
  Sort `captured_at DESC`. Standard `{data, meta:{total,page,per_page}}` envelope.
  This is the backend SP2's feed page consumes.

Pydantic schemas: `app/schemas/news.py` (`NewsItemCreate`, `NewsItemRead`, list meta).
Register the router in `app/api/v1/router.py`.

### Sightings: reuse existing endpoints
- `GET /api/v1/incidents?classification=sighting` (the param is already comma-separated).
- `GET /api/v1/incidents/map`, stats endpoints — all aggregate by classification already.

---

## Auto-publish (no human in the loop)

AI-promoted records publish immediately:
- Promote the `collector` user to role `verified_contributor`.
- Collector posts promoted records to `POST /api/v1/incidents` (auto-published as
  `verified`, audit-logged) **instead of** `/submissions` (the `pending` review queue).
- Applies to both attacks and sightings.

**Implementation verification required:** confirm `verified_contributor` may POST
`/incidents` and that path auto-publishes + writes an audit log entry.

---

## Collector wiring

- New `collector/news_client.py` — `NewsClient`, mirroring `OsafSubmitter`'s JWT auth +
  401-retry pattern. `upsert(news_item)` → `POST /api/v1/news` (returns id);
  `mark_promoted(dedup_key, incident_id)` → same `POST` upsert with
  `promoted_incident_id` set.
- `OsafSubmitter.submit` switches target from `/submissions` to `/incidents`.
- Wire `NewsClient` into the pipeline alongside `submitter` and `state`.

---

## Testing

Matches existing `pytest` layout (`collector/tests`, `backend/tests`, `conftest.py`).

**Collector unit:**
- Gate-1 keyword filter: shark vs non-shark items.
- Extractor `event_type` routing with mocked AI (attack / sighting / news).
- `process_items` routing: news-only is captured-not-promoted; attack & sighting are
  captured + promoted; non-shark is dropped (not stored).
- `NewsClient.upsert` idempotency (same `dedup_key` twice → one row).

**Backend:**
- `POST /news` requires auth; idempotent on `dedup_key`.
- `GET /news` filters + pagination + envelope shape.
- `GET /incidents?classification=sighting` returns sighting rows; sighting create
  accepts null victim fields.
- Alembic migration applies cleanly (`alembic upgrade head`) and downgrades.

Target: maintain existing coverage bar; new modules covered ≥80%.

---

## Migration

Single Alembic revision: create `news_items` table with columns, unique constraint,
CHECK, and three indexes. No data backfill (table starts empty; pollers populate going
forward). Optional follow-up (not SP1): re-scan `state.py` skip tombstones to seed
historical news — deferred.

---

## Build order within SP1

1. Migration + `NewsItem` model + `news` schemas.
2. Backend `POST`/`GET /news` endpoints + router registration.
3. Verify + enable `classification='sighting'` create path; flip collector to `/incidents`; promote `collector` user role.
4. Collector: `NewsClient`, extractor `event_type`, gate-1 filter, pipeline rewrite.
5. Tests across both layers.

## Risks

- **False-positive auto-publish:** with no human gate, a mis-promoted attack/sighting
  goes live. Mitigated by existing confidence thresholds + verify pass; sightings are
  lower-stakes. Audit log enables retroactive correction.
- **Sighting volume:** drone channels (DroneSharkApp, etc.) post daily — sightings could
  dominate. Acceptable for SP1; SP2 feed/stats can segment by `classification`/`event_type`.
- **Dedup split-brain:** `news_items.dedup_key` and `state.py` are two ledgers. Kept
  intentionally separate; both keyed identically, both idempotent, so divergence is benign.

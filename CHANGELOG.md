# Changelog

All notable changes to OSAF are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Fixed

- **Collector source filtering now preserves contextual shark reports.** Curated
  shark channels such as SharksHappen may omit the word "shark" from titles
  like "Matawan River Attacks Revisited." Trusted-source incident language now
  supplies that context, while unrelated videos remain excluded. YouTube and
  Reddit also share the broader species-aware relevance vocabulary, and trust
  metadata survives the pipeline's second relevance gate.

- **Shark News now sorts by publication date, newest first.** The feed previously
  sorted by collector capture time, causing backfilled older stories to appear
  above newer reporting. Items without a publication timestamp fall back to
  capture time, with deterministic tie-breaking for stable pagination.

- **Long aggregator URLs no longer fail evidence capture.** Deduplication keys
  longer than the database/API limit now use a stable SHA-256 URL fingerprint.

- **Fresh database migrations now install PostGIS before creating geometry
  columns.** A clean `alembic upgrade head` previously failed because the
  initial migration assumed the extension already existed.

- **Stats counted sightings as attacks (SP5).** `StatsService` aggregated over
  every incident regardless of classification, so the ~108 sightings (plus
  near-miss/doubtful/etc.) inflated the headline attack numbers. All aggregates
  (overview total/fatal/fatality-rate, by-year/country/species/activity,
  fatality-trends) now filter to `ATTACK_CLASSIFICATIONS`
  (`unprovoked, provoked, boat_bite, scavenge, aquaria`). Sightings remain in the
  DB and on the Map/Database/News; they just no longer skew the stats.

- **Statistics — "Incidents by Species" counted only confirmed species.**
  `StatsService.by_species()` and the overview `most_common_species` aggregated
  on `shark_species_confirmed`, which is populated for only ~6 of 6,580
  incidents. The collector writes the species it infers to
  `shark_species_suspected` (~2,080 populated), so the species donut and the
  "Most Common Species" card reflected just 6 incidents and reported
  "Bull Shark." Both queries now aggregate on a shared
  `StatsService._species_label()` =
  `COALESCE(shark_species_confirmed, shark_species_suspected)`. The card now
  correctly reports "Great White" (*Carcharodon carcharias*) and the donut shows
  the full ~2,000-incident distribution (Great White → Tiger → Bull → …).
  Commit `65d02c8`.

- **Statistics — "Incidents by Country" hid the #1 country.** The chart rendered
  all 20 returned countries in a fixed 300px height, so Recharts thinned the
  Y-axis labels to every other tick and skipped index 0 — the United States, the
  highest-count country — making Australia (#2) appear to lead with the longest
  bar. `AttacksByCountry` now slices to the top 10 countries and forces every
  label (`YAxis interval={0}`), so the United States renders at the top with its
  bar labeled. The underlying data and API ordering were always correct; only
  the rendering hid the leader. Commit `ca65913`.

- **Collector — classification mis-mapping.** `_validate_field()` matched a value
  as a substring of an option, so `"provoked"` collapsed into `"unprovoked"` and
  silently reclassified provoked incidents. Exact match now wins first; the
  remaining fuzzy step only matches an option as a substring of a longer phrase.
  Commit `ec931da`.

- **Backend — input hardening.** Role updates validate against an allowlist;
  the full-text `search` param is length-capped; `ILIKE` metacharacters in
  search are escaped so user input is matched literally. Commit `8877882`.

### Added

- **Durable evidence ingestion and incident candidates.** Collector input now
  passes through immutable `source_documents`, leased/retryable
  `collection_jobs`, versioned `extracted_observations`, and reviewable
  `incident_candidates`. Existing `news_items` are backfilled into the evidence
  layer during migration. Exact event keys group independent observations, and
  every promoted candidate links to its canonical incident. The admin panel
  adds an Evidence Queue with publish/reject controls and private operational
  health metrics. Collector item completion is no longer stored in a local JSON
  file; PostgreSQL owns deduplication, leases, exponential retry state, and dead
  letters. AI extraction no longer publishes canonical incidents directly;
  publication and case-number assignment happen only after an administrator
  approves the candidate. Migration: `f6a7b8c9d0e1`.

- **LLM near-duplicate merge (SP4).** A backend batch job
  (`scripts/dedupe_llm.py`, dry-run default, `--apply`) catches same-event
  duplicate incidents the deterministic signature misses (drifted date/coords).
  It blocks candidates by `(country, classification)` within a ±3-day window,
  asks glm-5.2:cloud which records are the same real-world event (guardrailed:
  data-only, conservative, returned case numbers allowlisted to the cluster),
  and merges confirmed groups via the shared `merge_cluster` (audit
  `action="merged_llm"`). SP3's merge logic was refactored into that shared
  `merge_cluster`. Backend gained an Ollama Cloud client (`app/services/llm.py`,
  `OLLAMA_*` settings, `httpx`). Run first pass manually (dry-run → review →
  apply), then nightly cron. Spec/plan:
  `docs/superpowers/specs/2026-07-01-osaf-llm-neardupe-design.md`,
  `docs/superpowers/plans/2026-07-01-osaf-llm-neardupe.md`.

- **Incident deduplication (SP3).** Multiple outlets covering one shark event no
  longer create duplicate incidents: a deterministic event signature (exact-date +
  coordinates within 150 m + classification, with a victim age/sex guard) attaches
  syndicated coverage as extra sources to the existing incident instead of creating
  a new one (`dedup_service.find_duplicate_incident`, wired into both the submission
  and direct-create paths). The Shark News feed now shows one row per event
  (`list_news` collapses promoted items by incident via a `row_number()` window). A
  one-off `scripts/dedupe_incidents.py` (dry-run default, `--apply` to execute)
  merges pre-existing duplicate clusters — moving sources onto the canonical (lowest
  case number), re-pointing/pruning their `news_items`, and audit-logging each merge.
  Spec/plan: `docs/superpowers/specs/2026-07-01-osaf-incident-dedup-design.md`,
  `docs/superpowers/plans/2026-07-01-osaf-incident-dedup.md`.

- **Shark News feed page (SP2).** Public recency-first feed at `/news` consuming
  `GET /api/v1/news`: media-list rows (thumbnail, event-type chip, title, source
  link-out, relative time, "incident" link on promoted items), event-type tabs
  (All/Sightings/Attacks/News), debounced search, and load-more paging
  (`useNews`, with ref-guarded in-flight + `AbortController` for stale-request
  cancellation). All external URLs pass through a new `safeUrl()` http(s) guard
  (discharges the SP1-deferred XSS item). Adds a minimal Vitest harness for the
  pure logic (`safeUrl`, `relativeTime`, news paging helpers). Sightings already
  render across the map/DB/stats via the existing classification constants — no
  frontend change needed there. Spec/plan:
  `docs/superpowers/specs/2026-06-30-osaf-shark-news-feed-page-design.md`,
  `docs/superpowers/plans/2026-06-30-osaf-shark-news-feed-page.md`.

- **Shark News capture + AI auto-promotion of sightings & attacks (SP1).** New
  additive `news_items` table captures *every* shark-relevant item the collector
  finds, so nothing is silently dropped at the old relevance gate (the original
  motivation: missed sightings). The collector pipeline is now two-tier — a cheap
  keyword gate (`collector/relevance.py`) decides what gets captured into
  `news_items`, then the existing AI extractor decides what gets promoted; results
  are tagged `attack` / `sighting` / `news` (`derive_event_type`). Sightings are
  tracked as first-class data: an `incidents` row with `classification='sighting'`
  (no schema change — already legal). Promoted records auto-publish (the `collector`
  user becomes a `verified_contributor`; `backend/scripts/promote_collector.py`).
  New endpoints: public `GET /api/v1/news` (filters + pagination) and
  contributor-only `POST /api/v1/news` (idempotent upsert via `ON CONFLICT`,
  resolving `promoted_case_number` → `promoted_incident_id`). Backend:
  `app/models/news.py`, `app/schemas/news.py`, `app/services/news_service.py`,
  `app/api/v1/news.py`, migration `d4e5f6a1b2c3`. Collector: `relevance.py`,
  `news_client.py`, rewritten `pipeline.py`. Design + plan:
  `docs/superpowers/specs/2026-06-28-osaf-shark-news-sightings-backend-design.md`,
  `docs/superpowers/plans/2026-06-28-osaf-shark-news-sightings-backend.md`.
  This is the backend half; the public Shark News feed page is SP2.

- **Map — coastline snapping for vague-location incidents.** Incidents located
  only to a country/region geocoded to the inland country centroid (e.g. a "South
  Africa" pin in the interior). New `collector/coastline.py` snaps such points to
  the nearest coast using vendored Natural Earth land polygons, but only when a
  point is vaguely located **and** on land **and** ≥25 km inland — so offshore and
  specific-location (incl. genuine inland river) incidents are never moved.
  `collector/backfill_coast_snap.py` re-snapped 86 existing incidents. Design
  spec: `docs/superpowers/specs/2026-06-24-osaf-coastline-snapping-design.md`.
  Commit `510354e`.

- **Collector — country-name canonicalization.** `COUNTRY_ALIASES` maps variants
  like `USA`/`U.S.`/`RSA` to canonical names so country stats and filters don't
  fragment. Commit `ec931da`.

### Changed

- **Collector — extraction model.** Switched from `qwen3-coder:480b` (a code
  model) to `glm-5.2:cloud`, a general instruction-following model better suited
  to prose extraction, served via `https://ollama.com`. A `"think": false` guard
  prevents reasoning tokens from truncating the JSON output. Commit `8877882`.

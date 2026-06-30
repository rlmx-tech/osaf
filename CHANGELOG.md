# Changelog

All notable changes to OSAF are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Fixed

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

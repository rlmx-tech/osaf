# Changelog

All notable changes to OSAF are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Security

- **Public statistics counted unverified and rejected incidents.** Every
  `StatsService` aggregate filtered on classification alone, while
  `list_incidents` and the map service both carry a verified-only filter.
  Registration is open and any authenticated user can submit, so a pending
  submission moved `total_incidents`, `fatality_rate`, `most_active_country`,
  the species donut, and every trend line the moment it was created — and an
  incident an admin had rejected as a hoax kept counting forever. Now one
  combined `_PUBLIC_ATTACK_FILTER`, so a query added later cannot pick up the
  classification filter and miss the verification one.

- **Map endpoints ignored `location_precision`.** `get_geojson` rounded every
  point to 3 decimals (~110 m) regardless, and `get_clusters` published raw
  centroids unrounded, so a grid cell holding one incident echoed that
  incident's exact coordinate. Incidents marked approximate or region are
  marked that way deliberately. The rule now lives once in
  `utils.geo.round_coord`, shared by list, detail, GeoJSON, and clusters.

- **Direct incident writes left no audit trail.** `POST /incidents` and
  `PUT /incidents/{id}` are reachable by any admin or verified contributor and
  wrote nothing to `incident_audit_log`, so `/admin/audit-log` showed nothing
  for them. Both now log, attributed to the authenticated user, with updates
  recording a per-field `{from, to}` diff and no entry at all for a no-op.
  `DELETE /incidents/{id}` is covered too — see the entry under Fixed for why
  that one needed a schema change to be possible at all.

- **`SECRET_KEY` had no strength validation.** Compose's `${SECRET_KEY:?...}`
  only rejects unset or empty, so the `.env.example` placeholder would boot a
  healthy-looking app signing every HS256 token with a guessable value.
  Startup now refuses keys under 32 characters or matching known placeholders.

- **`users.role` had no database CHECK constraint**, unlike every enum-like
  column on `incidents` — the column deciding who can publish and delete
  relied entirely on API-layer allowlists. Migration `a1b2c3d4e5f6` normalizes
  any out-of-range role to `public` (the least-privileged value) and adds the
  constraint.

- **Collector followed redirects without re-checking the host.** The tracker
  poller validated the initial URL against an allowlist, but `httpx` does not
  re-validate on redirect, so a compromised upstream could bounce the fetch to
  a LAN or metadata address. The final resolved host is now checked.

- **`collector/submitter.py` removed.** Unreferenced, and predating the
  evidence-ingestion rework — if rewired to the verified-contributor account
  the deploy docs describe, it would have auto-published LLM output with no
  review gate.

- **Frontend dependencies: `npm audit` now reports zero vulnerabilities**, down
  from 5 (2 HIGH, 3 moderate). `postcss` 8.5.18 → 8.5.28 and a transitive
  refresh cleared nanoid and browserslist; `react-router-dom` 6.30.4 → 7.18.3
  cleared the remaining two (see Fixed).

### Fixed

- **Half of all verification passes were being thrown away as "no response from
  Ollama".** glm-5.3-flash reasons before it answers, and `num_predict` caps the
  reasoning and the answer together — it is not a limit on the reply alone. The
  verification prompt asks the model to check five things against the article, and
  measured 2026-09-08 against the live API it spent 5,392-9,354 characters
  thinking about that. On the long runs the 2048-token budget was gone before it
  wrote a single character of JSON, so the API returned HTTP 200 with an empty
  `response` and `done_reason: "length"`. Four of eight identical calls came back
  empty. The pipeline read that as an outage, marked the incident invalid, and
  downgraded it to 0% confidence — failing in the safe direction, but silently
  suppressing real incidents and looking like Ollama was down. The budget is now
  a setting (`COLLECTOR_OLLAMA_NUM_PREDICT`) and truncation is logged by name,
  with the token count it actually reached, rather than folded into the generic
  no-response path. 4096 cut the production rate from 38.6% to 14.3% but not to
  zero — real articles reason further than the clean synthetic one the first
  measurement used — so the default is 8192. The value is a ceiling and not an
  allocation: a call that stops early is billed for what it generated, so
  headroom is free on every request that does not need it. Measured across three
  production cycles against the same feeds: 22 of 57 calls empty at 2048, 6 of 42
  at 4096, 0 of 45 at 8192.

- **The promotion gate passed aggregator stubs as if they were articles.** A
  live run showed 60 Google News items clearing the 400-character floor. Their
  summaries turned out to be an HTML `<ol>` of *related headlines* running
  470-862 characters: long enough to pass a length check, containing no article
  whatsoever. That is precisely the fabrication input the gate exists to stop,
  and feeding it to the extractor made the model more confident, not less
  (0.80 against 0.30 on the same incident). Three things are checked now. A
  poller that went looking for an article and came back empty says so in
  `extra["has_article_body"]`, and that answer wins outright. Markup is
  stripped before measuring, because tags are not prose. The title is removed,
  because a stub is the headline repeated and raw length would let repetition
  clear the floor. Items that fail are still captured into Shark News — nothing
  is lost from the feed, they simply cannot become incidents. After the fix,
  Google News drops to 0 promotable of 75 and Bing contributes 22 real bodies
  of 1,201-12,253 characters.

- **`qwen3-coder:480b` was a latent landmine in the shipped defaults.** Ollama
  Cloud retired it on 2026-07-15; it now answers `HTTP 410`. It was the
  `docker-compose.yml` default and the value in both `.env.example` files, so
  any fresh deploy — or any host whose `.env` did not override it — would have
  had every extraction call fail. `_call_ollama` catches the error, logs it,
  and returns `None`, so the pipeline would have dropped every item while the
  container stayed healthy. It also contradicted `extractor.py`'s own docstring,
  which specifies a general instruction-following model rather than a code
  model. Both services now use `glm-5.3-flash:cloud`, verified end to end
  against the live API.

  For the record: the production host was not affected. Its `.env` set
  `glm-5.2:cloud`, which works — 8732 collection jobs completed with none
  failed or dead-lettered.

- **`think: False` broke JSON extraction on glm-5.3 models.** The parameter was
  correct for glm-5.2 but inverts on glm-5.3: measured against the real
  extraction prompt, `think: False` made the model emit its reasoning as
  ordinary prose ahead of the JSON (~8000 characters, and `glm-5.3:cloud`
  became unparseable outright), while omitting the key returned bare JSON in
  ~700 characters. `think: True` parses but runs about 3x slower for no gain.
  The key is no longer sent, and a test asserts it stays that way.

- **The collector now preflights its model at startup.** A retired or
  misspelled model tag previously failed silently on every item. Startup makes
  one cheap call and exits with a clear message on `401/403/404/410`, while
  treating a network blip or `5xx` as transient and continuing.

- **Undated incidents led the public incident list.** Postgres defaults a DESC
  sort to NULLS FIRST, so the default `?sort=incident_date&order=desc` put
  records with no date — often with no coordinates either — at the top of the
  page everyone lands on. Both directions now sort NULLS LAST, with
  `case_number` as a tiebreaker so paging cannot repeat or skip a record when
  many incidents share a date.

- **Collector dropped incidents on non-object LLM output.** The collector's
  `_parse_json_response` lacked the `isinstance(dict)` guard its backend twin
  has, so valid JSON that is not an object — an array, a bare string, a number
  — reached callers that call `.get()` and raised `AttributeError`. Contained
  by the pipeline's broad except, so the effect was silent data loss.

- **`OLLAMA_API_KEY` was optional against a remote endpoint.** Empty meant no
  auth header, a 401 on every call, and a collector reporting healthy while
  collecting nothing. Now required when the Ollama URL is remote; still
  optional for a local instance.

- **`DELETE /incidents/{id}` is now audited, and the entry survives the
  delete.** `incident_audit_log.incident_id` was `ON DELETE CASCADE`, so an
  audit row written for a deletion was destroyed along with the incident it
  described — the one action most worth auditing erased its own evidence. The
  FK is now `ON DELETE SET NULL` with a nullable `incident_id`, and each entry
  carries its own `case_number` so it still identifies its subject once the
  incident is gone. Deletion entries include a field snapshot of what was
  destroyed, deliberately excluding `victim_name` and injury detail so the
  audit log is not a backdoor around the public disclosure boundary. Migration
  `b2c3d4e5f6a7` backfills `case_number` for existing history. Chose this over
  soft-delete: soft-delete would have required a `deleted_at` filter on every
  query, and one missed filter leaks a deleted record — the same class of bug
  as the stats leak above.

- **Relevance matching ignored word boundaries.** `is_shark_relevant` tested
  species names as plain substrings, so short names matched inside unrelated
  words: an r/newzealand bird-of-the-year post was captured because the
  submitter's username was `/u/makoextinct`, and "korimako" would do the same.
  Terms are now matched on word boundaries with plural and possessive forms
  allowed, so "sharks" and "a shark's tooth" still count. Three items in the
  live feed came in this way. The gate remains deliberately recall-favoring;
  matching a fragment of an unrelated word was never recall, only noise.

- **`react-router-dom` upgraded 6.30.6 → 7.18.3**, clearing the last two npm
  advisories (open redirect via backslash, and `deserializeErrors` constructor
  injection). `npm audit` now reports zero vulnerabilities. The app uses only
  declarative APIs — `BrowserRouter`, `Routes`, `Route`, `Link`, `NavLink`,
  `Navigate`, `useNavigate`, `useParams` — so the upgrade was drop-in; build,
  tests, and a module-graph transform check all pass.

- **`deploy/deploy.sh` left the site 502 after every deploy.** nginx resolves
  the backend's container IP once at startup. `docker compose up -d` gives the
  rebuilt backend a new IP but does not recreate nginx, whose image and config
  are unchanged, so it kept proxying to an address nobody was listening on.
  The stack reported healthy while the site was down. The script now restarts
  nginx after bringing the stack up, and its health check goes through nginx on
  the real bind port rather than straight at the backend — the proxy path is
  the one that breaks.

### Known issues

- **632 incident candidates are waiting on admin approval.** The
  evidence-ingestion rework made publication require an explicit admin action,
  and none has happened since the day it shipped: the last candidate published
  was 2026-07-13, against 6543 published before the cutover and a newest
  candidate created hours ago. The pipeline itself is healthy end to end —
  8732 collection jobs completed, none failed or dead-lettered — so this is a
  workflow gap, not a defect. It needs a decision on whether high-confidence
  candidates should auto-publish or whether the queue gets worked through
  manually.


- **The backend test suite is runnable again, and can no longer drop a real
  database.** 142 of its 306 tests errored with `ConnectionRefusedError`
  because they need PostgreSQL+PostGIS and the `db` service publishes no
  ports — correctly, since production keeps Postgres off the host. Rather
  than weaken that, a new `docker-compose.test.yml` runs a disposable
  tmpfs-backed `postgis/postgis:16-3.4` bound to `127.0.0.1:5432` (same major
  version as production; `fsync=off` since the data is discarded anyway).
  Separately, `conftest.py` set its connection details with
  `os.environ.setdefault`, which yields to anything already exported, while
  its session fixture calls `Base.metadata.drop_all` on teardown — so a stray
  `export POSTGRES_HOST=...` on a machine that also administers production
  turned `pytest` into a production table drop. The suite now refuses to start
  unless the host is local and the database name ends in `_test`/`_testing`,
  and exits 1 so CI cannot read a refusal as a pass. Default test database
  renamed `osaf` → `osaf_test`. Full suite: 306 passed.

- **Marine incidents no longer accept arbitrary inland geocodes.** Nominatim
  candidates are state-bounded, ranked by coastal plausibility, and nearby
  coastal place centroids are snapped to the waterline. Australian state
  abbreviations, qualified landmarks ("near", "north of", "west of"), and
  known ambiguous place names are normalized before lookup. Explicit river,
  lake, canal, and aquarium incidents remain eligible for inland coordinates.
  Vague state/country descriptions are now left unmapped rather than assigned
  a misleading coastline guess. Collector coordinates publish as approximate.
  A reviewed 21-record 2026 repair manifest corrects named locations and clears
  four unsupported guesses.

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

- **The collector fetches real article bodies.** Until now every news item
  carried only the headline and the feed's own summary, which is what let a
  wrapper link with no article behind it reach the extractor at all.
  `collector/article_fetch.py` retrieves the publisher page and runs it through
  trafilatura, and both the news poller and the new GDELT poller use it. This
  is the collector's first outbound fetch to arbitrary third-party domains —
  every earlier fetch went to an operator-configured feed or the one
  allowlisted tracker — so the SSRF guard carries real weight: `is_global`
  address checks plus an explicit 100.64.0.0/10 block, revalidated on every
  redirect hop rather than only on the URL first supplied. Responses are capped
  at 2 MB and 20 seconds. Bodies are memoized in a bounded LRU that remembers
  misses as well as hits, because a paywall or a JavaScript shell will not
  start yielding text on the next poll and retrying it every ten minutes is
  abuse of the publisher with none of the payoff.

- **Bing News RSS feeds (5).** Google News wrapper links do not redirect to the
  publisher, so those feeds can never supply an article. Bing's wrappers do,
  measured 2026-09-08, and they now contribute the bodies that make an incident
  possible. Quoted-phrase queries return nothing there, so these stay as bare
  keyword searches.

- **GDELT document API poller.** Discovery across GDELT's indexed news
  worldwide rather than the handful of RSS endpoints, throttled to one request
  per 6 seconds and abandoning the rest of a cycle on a 429 instead of pressing
  a refusal. Note that as of 2026-09-08 the GDELT doc 2.0 API is returning 429
  to every caller — confirmed from two unrelated hosts on a first request — so
  the poller contributes nothing until that clears. It degrades to zero items,
  not to errors.

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

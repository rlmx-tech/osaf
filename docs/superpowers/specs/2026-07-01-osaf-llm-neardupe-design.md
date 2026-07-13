# OSAF — LLM Near-Duplicate Merge Layer (SP4)

**Date:** 2026-07-01
**Status:** Approved design (pre-implementation)
**Scope:** Backend batch job. Catch same-event duplicate incidents that SP3's deterministic signature misses (drifted date or coordinates), using an LLM to adjudicate, and merge them with SP3's machinery.

---

## Problem

SP3's `find_duplicate_incident` merges only exact-signature matches (same `incident_date` + coords within 150 m + classification). Near-duplicates slip through when different outlets' articles yield a slightly different **extracted date** (e.g., the Bahamas 12-year-old reported as Jun 24 vs Jun 25) or drifted geocoded coordinates. These remain as separate incidents / separate feed rows. SP3's design explicitly deferred these to a "future LLM layer."

## Goal

A scheduled backend batch job that finds plausibly-same-event incident groups (blocked to bound cost), asks the LLM (glm-5.2:cloud) which are truly the same real-world event, and merges the confirmed groups using SP3's existing merge machinery — conservatively, dry-run-first, audit-logged.

## Non-Goals (SP4)

- Live/at-ingest dedup — this is a scheduled batch (near-dupes don't need instant merging).
- Cross-classification merges (e.g., an "attack" and a "sighting" of the same shark) — blocked within the same classification for v1.
- Replacing SP3's deterministic layer — SP4 runs *after* it and only handles what it misses.
- No schema/migration change.

---

## Architecture

Runs in the **backend container** (direct DB, transactional merges), reusing SP3's merge code. Gains Ollama Cloud access via `httpx` (mirroring the collector's `_call_ollama`).

Flow:
1. **Block candidates.** Load incidents with `date_precision='exact'` and a non-null date. Group by `(country, classification)`. Within each group, form candidate clusters of incidents whose dates fall within a **±3-day transitive window** and size ≥2. Coordinates are NOT a block key (near-dupes have drifted coords). Cap cluster size at ~10; larger clusters are chunked or skipped with a warning (avoids over-broad prompts / over-merging).
2. **LLM adjudication.** For each candidate cluster, send the LLM a compact JSON of each incident: `{case_number, incident_date, location_description, state_province, body_of_water, latitude, longitude, victim_age, victim_sex, victim_activity, shark_species_suspected, description(truncated), source_titles}`. Prompt asks it to return groups of `case_number`s that **clearly describe the same real-world event**, omitting singletons.
3. **Merge.** Each returned group of 2+ → merge via the shared SP3 `merge_cluster` function.

---

## Components

### 1. Refactor SP3 merge into a shared function
Extract the per-cluster merge body from `scripts/dedupe_incidents.py` into a reusable `merge_cluster(db, incident_ids: list[UUID], action: str) -> int` (in a shared module, e.g. `app/services/dedup_service.py` or `scripts/_merge.py`): canonical = lowest case number; enrich canonical from absorbed non-null fields; move sources (dedup by URL); delete absorbed `backfill:*` news_items + re-point others; `IncidentAuditLog(action=...)`; delete absorbed incident. Per-cluster transaction. `dedupe_incidents.py` is updated to call it (behavior unchanged; SP3 tests still pass).

### 2. `scripts/dedupe_llm.py` (new)
- `async candidate_clusters(db, window_days=3, max_cluster=10) -> list[list[Incident]]` — pure-ish blocking by `(country, classification)` + transitive ±window date grouping; excludes clusters > max_cluster (logged).
- `async adjudicate(cluster) -> list[list[str]]` — calls the LLM, returns validated same-event groups of case numbers.
- `async run(apply: bool, window_days=3) -> dict` returning `{clusters_examined, llm_groups, incidents_merged}`. Dry-run default; `--apply` performs merges (audit `action="merged_llm"`). CLI `python -m scripts.dedupe_llm [--apply] [--window N]`.
- Dry-run prints each LLM-confirmed group (canonical + absorbed) and the would-fill fields (SP3 dry-run style).

### 3. LLM call + guardrails (per OSAF AI rules)
- `_call_ollama(prompt) -> str | None` in the backend (httpx `POST {OLLAMA_URL}/api/generate`, `think=false`, `temperature=0.1`, `stream=false`; Bearer `OLLAMA_API_KEY`), plus `_parse_json_response` (reuse the collector's tolerant parser shape).
- New backend settings: `OLLAMA_URL` (default `https://ollama.com`), `OLLAMA_API_KEY`, `OLLAMA_MODEL` (default `glm-5.2:cloud`).
- **Guardrails:** prompt instructs "use ONLY the provided incident data; group ONLY if clearly the same event (same victim / location / circumstances); when unsure, do NOT group." Descriptions truncated (e.g. 500 chars each), curly braces escaped. **Allowlist:** returned case numbers are intersected with the cluster's own case numbers — hallucinated/foreign case numbers are dropped; a group with <2 valid members is discarded. On LLM failure / unparseable output → skip the cluster (never merge on uncertainty).

---

## Safety, rollout, scheduling

- **Dry-run default**, `--apply` gated; every merge audit-logged (`action="merged_llm"`); per-cluster transaction; idempotent.
- **Rollout:** run the first pass **manually** — dry-run → review the LLM's proposed groupings → `--apply` — to validate the model's judgment on real data. **Then** enable a **nightly cron on the production host** that runs it with `--apply` (e.g., host cron → `docker compose exec -T backend python -m scripts.dedupe_llm --apply`). Human-in-the-loop for the first validation, automated thereafter.

---

## Testing

Backend (`pytest`, `osaf_test`):
- `candidate_clusters`: same country+classification within ±3 days → one cluster; >3 days apart → separate; different classification/country → not clustered; cluster > max → excluded.
- `adjudicate` with a **mocked** `_call_ollama`: valid group returned → parsed; hallucinated case number not in cluster → dropped; group with 1 valid member → discarded; LLM returns "no groups"/garbage → empty.
- `merge_cluster` (refactor): SP3 tests still green; a direct test merges a 2-incident group (sources moved, enrich, backfill news pruned, audit written).
- End-to-end `run` with mocked LLM: two near-dupe incidents (dates 1 day apart, same event) → LLM groups them → `--apply` merges to one; "no groups" → nothing merged; dry-run → nothing mutated.

No migration.

---

## Build order

1. Refactor SP3 merge → shared `merge_cluster` (+ confirm SP3 tests pass).
2. Backend Ollama access (`_call_ollama` + settings) + tests (mocked).
3. `candidate_clusters` blocking + tests.
4. `adjudicate` (LLM + guardrails + allowlist) + tests (mocked).
5. `dedupe_llm.run` (dry-run/apply, CLI) + end-to-end test (mocked).
6. Deploy: add `OLLAMA_*` environment variables on the production host; run the first pass manually (dry-run → review → apply); then add nightly cron.

## Risks

- **LLM false-merge:** mitigated by conservative prompt (only clearly-same, default to not-grouping), case-number allowlist, same-classification blocking, per-merge audit log, and manual first-run validation before scheduling.
- **Cost/latency:** bounded by blocking (only clusters of 2+ within ±3 days incur a call) + cluster-size cap; the batch runs off the request path.
- **Cross-classification same events** (one outlet "sighting", another "attack") are not caught in v1 — documented; can extend blocking later.
- **Ollama Cloud dependency in backend:** the script degrades safe (skip cluster) on any LLM error; the API request path is untouched (script is offline/batch).

# OSAF — Exclude Non-Attack Classifications from Stats (SP5)

**Date:** 2026-07-01
**Status:** Approved design (pre-implementation)
**Scope:** Backend stats only. Stop sightings (and other non-bite classifications) from inflating the attack numbers.

---

## Problem

SP1 stores sightings as `incidents` rows with `classification='sighting'` (reusing the whole incident stack). `stats_service` counts **every** incident with no classification filter — `total = count(*)`, and `by_year`/`by_country`/`by_species`/`by_activity`/`fatality_trends`/overview all include sightings, near-misses, doubtful, etc. So the ~108 sightings (plus other non-bite classifications) inflate the headline "attack" numbers.

## Goal

Make all stats aggregates count only genuine shark-on-human bite events, so the numbers reflect real attacks. Sightings remain stored and visible on the Map/Database/News (with their type + filters) — this fixes the *numbers*, not visibility.

## Non-Goals

- No schema change, no migration, no separate `sightings` table (considered and rejected in favor of this cheap, low-risk fix).
- Map / Database / News list behavior is unchanged (they intentionally show sightings per SP1).
- The incident CRUD/search endpoints are unchanged.

---

## Design

### Attack classification set
Add a module-level constant (in `backend/app/services/stats_service.py`, or a small shared `app/constants.py` if cleaner):
```python
ATTACK_CLASSIFICATIONS = ("unprovoked", "provoked", "boat_bite", "scavenge", "aquaria")
```
These are the real shark-on-human bite events. **Excluded** from attack counts: `sighting`, `near_miss`, `equipment_bite`, `unverified_report`, `doubtful`, `no_assignment`, `not_confirmed` (non-bite, gear-only, or unconfirmed). The set is a single constant, trivially adjustable.

### Apply the filter to every aggregate
In `stats_service`, add `Incident.classification.in_(ATTACK_CLASSIFICATIONS)` to the WHERE of each query:
- `overview`: `total`, `fatal_count` (→ `fatality_rate`), `top_country`, `most_common_species`.
- `by_year`, `by_country`, `by_species`, `by_activity`, `fatality_trends`.

`fatality_rate` is then fatal-attacks / total-attacks. `most_active_country` and species/activity breakdowns count only attacks.

### Consistency
Every stats query uses the same constant so the numbers are internally consistent (e.g., by-year totals sum to the overview total). No endpoint signature changes; response shapes unchanged.

---

## Testing

Backend (`pytest`, `osaf_test`):
- Seed a mix: N attack incidents (various attack classifications, some fatal) + M sightings (+ a `near_miss`, a `doubtful`).
- `overview.total == N` (not N+M); `total_fatal` counts only fatal attacks; `fatality_rate` computed over N.
- `by_year` / `by_country` / `by_activity` / `fatality_trends` sums equal the attack-only counts (sightings excluded).
- A sighting with a populated species/activity does NOT appear in `by_species`/`by_activity`.

No migration.

---

## Build order

1. `ATTACK_CLASSIFICATIONS` constant + filter every `stats_service` aggregate + tests.
2. Deploy a rebuilt backend image to the production host; verify `/api/v1/stats/overview` total dropped by the sighting/non-attack count.

## Risks

- **Choice of attack set** is a judgment call; it's one constant, easy to change if the definition should shift (e.g., include/exclude `scavenge`).
- Existing frontend stat labels say "incidents" — the numbers now mean "attacks." Acceptable; copy tweak is optional and out of scope.

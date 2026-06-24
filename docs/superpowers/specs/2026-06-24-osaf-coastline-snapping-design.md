# OSAF Coastline Snapping — Design Spec

**Date:** 2026-06-24
**Status:** Approved (design)
**Component:** `collector/` (geocoding pipeline)

## Problem

Shark incidents whose location is too vague to pin to a real place (e.g. a
`location_description` of just `"South Africa"` or `"Australia"`, with no
state) are geocoded by Nominatim to the **country centroid**, which lands deep
inland. On the map these appear as incidents in the middle of the Northern Cape
or the Australian outback — clearly wrong, since every shark incident is in or
near water.

### Measured scope (live data, 2026-06-24)

- 6,573 incidents total; 4,230 have coordinates.
- **158 incidents** have `location_description` equal to their `country` (no
  state) and sit on the country centroid. Examples:
  - `OSAF-2026-6444` "South Africa" → `(-30.559, 22.938)` (interior)
  - `OSAF-2026-0362` "Australia" → `(-24.776, 134.755)` (dead-center outback)

This 158 is the **floor** — points with a specific `location_description` can
also land inland via an inland namesake match, but those are out of scope here
(see Non-Goals).

### Root causes

1. `geocoder._in_state_bounds()` returns `True` whenever `state_province` is
   missing, so country centroids pass validation unchecked.
2. Nothing ever verifies a geocoded point is on/near water.

## Goals

- Relocate **only clearly-wrong** vague-location incidents to the nearest
  coastline, so they appear in plausible (approximate) coastal positions.
- Fix both **new** incidents (live pipeline) and the **existing** 158 (backfill).
- Never move incidents that have a specific location — genuine inland
  river/lake (bull shark) incidents must survive untouched.
- No backend/database schema changes. All logic lives in the `collector`
  package and is unit-testable with fixed coordinates.

## Non-Goals

- General re-geocoding of specific-location incidents (the existing
  `backfill_geocode.py` covers Nominatim refinement).
- Snapping to inland water bodies (rivers/lakes). Out of scope by decision:
  we only touch obvious errors, so river incidents are left alone rather than
  risk a heavier water-body dataset.
- Reverse-geocoding / "is this water" API calls.

## Approach

Bundle a coarse **land-polygon** dataset and snap eligible points to the
nearest coastline (the land-polygon boundary), entirely within the collector.

### Why land polygons, not a coastline line

Distance-from-coastline is large both far **inland** and far **offshore**, so a
"far from coast → snap" rule would wrongly drag legitimate offshore points onto
land. A land polygon lets us test *is this point on land* first; offshore points
fail that test and are never moved. The polygon boundary is the coastline, so we
get the snap target for free.

### Snap rule

An incident is snapped **iff all three hold**:

1. **Vague location** — `is_vague_location()` is true: the normalized
   `location_description` is empty, or equals the normalized `country`, or
   equals the normalized `state_province`.
2. **On land** — the current point lies inside a land polygon.
3. **Clearly inland** — the point is `>= 25 km` from the nearest coastline.

When all hold, the point is replaced with the nearest point on the coastline.
Otherwise the original coordinates are kept.

(Conditions 2 and 3 prevent moving a vague point that is already offshore or
already at the coast. Condition 1 protects every specific-location incident.)

## Components

### New module: `collector/coastline.py`

Owns the dataset and all geometry. No knowledge of incidents or the API.

```python
def is_vague_location(
    location_description: str | None,
    country: str | None,
    state_province: str | None,
) -> bool: ...

def snap_if_inland(
    lat: float, lon: float, *, threshold_km: float = 25.0,
) -> tuple[float, float, float] | None:
    """Return (new_lat, new_lon, moved_km) if the point is on land and
    >= threshold_km inland, else None (caller keeps original coords).
    Returns None (no-op) if the dataset failed to load."""
```

Internals:
- Load `collector/data/ne_50m_land.geojson` once at module import into a
  shapely `MultiPolygon` / list of polygons, plus an `STRtree` index over them
  for fast nearest/contains queries.
- On-land test: `STRtree` candidate lookup → `polygon.contains(point)`.
- Nearest coast: nearest point on the nearest polygon's exterior
  (`shapely.ops.nearest_points(point, boundary)`).
- Distance: reuse `geocoder.haversine_km` (geographic km) for the threshold
  check and the reported `moved_km`. Nearest-point search is done in planar
  lon/lat space — acceptable at the few-km precision these approximate points
  warrant; documented as a limitation for high latitudes.
- If the dataset is missing or fails to parse: log an error once and make
  `snap_if_inland` a no-op (returns `None`) so the pipeline never crashes.

### Integration point 1: `collector/extractor.py`

In `extract_incident`, after `geocode_incident` returns coords:

```python
coords = await geocode_incident(...)
if coords and is_vague_location(location_desc, country, state_province):
    snapped = snap_if_inland(coords[0], coords[1])
    if snapped:
        coords = (snapped[0], snapped[1])
        logger.info("extractor: snapped vague %r %.0fkm to coast", location_desc, snapped[2])
latitude, longitude = coords if coords else (None, None)
```

### Integration point 2: `collector/backfill_coast_snap.py` (new)

One-shot script mirroring `backfill_geocode.py`'s structure (auth → paginate
incidents → per-incident action → summary counts), with `--dry-run` and
`--limit`. For each incident it re-evaluates the snap rule against the
**stored** coordinates — **no Nominatim call** — so it is instant and not
rate-limited. Eligible points are updated via `PUT /incidents/{id}` with
`{"coordinates": {...}}`. Per-incident `try/except`; failures are counted and
logged, never fatal.

Usage:
```
docker compose exec collector python -m collector.backfill_coast_snap --dry-run
```

### Dependency & dataset

- Add `shapely>=2.0` to `collector/pyproject.toml` dependencies. Its
  manylinux wheels bundle GEOS, so `collector/Dockerfile` needs **no** new
  apt packages.
- Vendor `collector/data/ne_50m_land.geojson` (Natural Earth 1:50m land,
  public domain, ~few MB) into the repo so builds are hermetic/offline. The
  existing `COPY . .` in the Dockerfile ships it into the image.

## Data Flow

```
New incident:   raw text → extract (Nominatim geocode) → [vague? on land? inland?] → snap → store
Existing 158:   stored coords → [vague? on land? inland?] → snap → PUT update
Offshore/specific/coastal points: rule fails → unchanged
```

## Error Handling

| Failure | Behavior |
|---|---|
| Dataset missing / parse error | Log once; `snap_if_inland` is a no-op; pipeline continues with original coords |
| shapely geometry error on a point | Caught; treated as no-op for that point |
| Backfill: API auth fails | Abort with clear error (same as existing backfill) |
| Backfill: single incident update fails | Count + log, continue |

## Testing

`collector/tests/test_coastline.py`:

- `is_vague_location`: location == country (vague), == state (vague), empty
  (vague), specific place (not vague), case/whitespace-insensitive.
- `snap_if_inland` against a **synthetic** land polygon fixture (deterministic,
  fast): inland point → snapped to boundary with expected `moved_km`; offshore
  point → `None`; near-coast point (< threshold) → `None`; on-land just over
  threshold → snapped.
- One smoke test against the **real** vendored dataset: the South Africa
  centroid `(-30.559, 22.938)` returns a snapped point that is (a) closer to
  the coast than the original and (b) within South African coastal bounds.
- Decision integration: a vague + inland fixture snaps; a specific-location
  inland fixture (simulated river incident) is left unchanged.

Target: keep the conservative rule fully covered so future changes can't
silently start moving good data.

## Rollout

1. Land the code + tests.
2. Deploy collector image to CT 102.
3. Run `backfill_coast_snap --dry-run`, review the moves (expect ~158).
4. Run for real; spot-check the SA and AU incidents on the map.

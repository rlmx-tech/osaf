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


async def run(apply: bool, window_days: int = 3) -> dict:
    """Run the LLM-adjudicated dedupe pipeline. Returns stats dict."""
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

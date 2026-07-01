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

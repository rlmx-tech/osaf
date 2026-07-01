import pytest
from datetime import date
from sqlalchemy import select
from app.models.incident import Incident
from app.models.news import NewsItem
from app.models.source import IncidentSource
from app.utils.geo import point_from_coords
from app.services.dedup_service import merge_cluster, _would_fill


async def _inc(db, case, url, pub, desc=None, age=None):
    i = Incident(case_number=case, incident_date=date(2026, 6, 25), date_precision="exact",
                 location_description="Bahamas", country="Bahamas", location_precision="approximate",
                 classification="unprovoked", fatal=False, description=desc, victim_age=age,
                 coordinates=point_from_coords(-77.34, 25.07), verification_status="verified")
    i.sources.append(IncidentSource(source_type="news_article", source_url=url, source_publisher=pub))
    db.add(i); await db.commit(); await db.refresh(i)
    db.add(NewsItem(dedup_key=f"backfill:{i.id}", source_platform="web_scrape", source_name=pub,
                    source_url=url, title=f"t {pub}", event_type="attack", promoted_incident_id=i.id))
    await db.commit()
    return i


@pytest.mark.asyncio
async def test_merge_cluster_merges_into_lowest_case(db):
    a = await _inc(db, "OSAF-2026-0002", "https://w/2", "WCIA", desc=None, age=12)
    b = await _inc(db, "OSAF-2026-0005", "https://y/5", "Yahoo", desc="Fuller account.", age=None)
    n = await merge_cluster(db, [a.id, b.id], "merged_llm")
    assert n == 1
    incs = (await db.execute(select(Incident))).scalars().all()
    assert len(incs) == 1 and incs[0].case_number == "OSAF-2026-0002"   # lowest case kept
    assert incs[0].description == "Fuller account."                      # enriched from absorbed
    pubs = {s.source_publisher for s in (await db.execute(select(IncidentSource))).scalars().all()}
    assert pubs == {"WCIA", "Yahoo"}                                     # sources merged
    assert len((await db.execute(select(NewsItem))).scalars().all()) == 1  # backfill news collapsed


def test_would_fill_is_pure():
    class F:  # minimal stand-ins
        pass
    canon = F(); absorbed = F()
    for f in ["description", "victim_age", "victim_sex", "victim_name", "body_of_water",
              "state_province", "county_region", "incident_time", "classification_subtype",
              "provocation_subtype", "shark_species_confirmed", "shark_species_suspected",
              "shark_size_estimate", "species_identification_method", "victim_activity",
              "victim_injury_severity", "victim_injury_description"]:
        setattr(canon, f, None); setattr(absorbed, f, None)
    canon.fatal = False; absorbed.fatal = True
    canon.description = None; absorbed.description = "x"
    filled = _would_fill(canon, absorbed)
    assert "description" in filled and "fatal" in filled
    assert canon.description is None   # pure: not mutated

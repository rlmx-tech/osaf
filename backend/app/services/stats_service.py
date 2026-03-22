from sqlalchemy import case, extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.incident import Incident


class StatsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def overview(self) -> dict:
        total = (await self.db.execute(
            select(func.count()).select_from(Incident)
        )).scalar_one()

        fatal_count = (await self.db.execute(
            select(func.count()).select_from(Incident).where(Incident.fatal.is_(True))
        )).scalar_one()

        top_country = (await self.db.execute(
            select(Incident.country)
            .group_by(Incident.country)
            .order_by(func.count().desc())
            .limit(1)
        )).scalar_one_or_none()

        top_species = (await self.db.execute(
            select(Incident.shark_species_confirmed)
            .where(Incident.shark_species_confirmed.is_not(None))
            .group_by(Incident.shark_species_confirmed)
            .order_by(func.count().desc())
            .limit(1)
        )).scalar_one_or_none()

        min_year = (await self.db.execute(
            select(func.min(extract("year", Incident.incident_date)))
        )).scalar_one()

        max_year = (await self.db.execute(
            select(func.max(extract("year", Incident.incident_date)))
        )).scalar_one()

        year_range = None
        if min_year and max_year:
            year_range = f"{int(min_year)}-{int(max_year)}"

        return {
            "data": {
                "total_incidents": total,
                "total_fatal": fatal_count,
                "fatality_rate": round(fatal_count / total * 100, 1) if total > 0 else 0,
                "most_active_country": top_country,
                "most_common_species": top_species,
                "year_range": year_range,
            }
        }

    async def by_year(self) -> dict:
        result = await self.db.execute(
            select(
                extract("year", Incident.incident_date).label("year"),
                func.count().label("count"),
                func.sum(case((Incident.fatal.is_(True), 1), else_=0)).label("fatal"),
            )
            .where(Incident.incident_date.is_not(None))
            .group_by("year")
            .order_by("year")
        )
        rows = result.all()
        return {
            "data": [
                {"year": int(r.year), "count": r.count, "fatal": r.fatal}
                for r in rows
            ]
        }

    async def by_country(self) -> dict:
        result = await self.db.execute(
            select(
                Incident.country,
                func.count().label("count"),
                func.sum(case((Incident.fatal.is_(True), 1), else_=0)).label("fatal"),
            )
            .group_by(Incident.country)
            .order_by(func.count().desc())
            .limit(20)
        )
        rows = result.all()
        return {
            "data": [
                {"country": r.country, "count": r.count, "fatal": r.fatal}
                for r in rows
            ]
        }

    async def by_species(self) -> dict:
        result = await self.db.execute(
            select(
                Incident.shark_species_confirmed.label("species"),
                func.count().label("count"),
            )
            .where(Incident.shark_species_confirmed.is_not(None))
            .group_by(Incident.shark_species_confirmed)
            .order_by(func.count().desc())
            .limit(15)
        )
        rows = result.all()
        return {
            "data": [{"species": r.species, "count": r.count} for r in rows]
        }

    async def by_activity(self) -> dict:
        result = await self.db.execute(
            select(
                Incident.victim_activity.label("activity"),
                func.count().label("count"),
            )
            .where(Incident.victim_activity.is_not(None))
            .group_by(Incident.victim_activity)
            .order_by(func.count().desc())
            .limit(15)
        )
        rows = result.all()
        return {
            "data": [{"activity": r.activity, "count": r.count} for r in rows]
        }

    async def fatality_trends(self) -> dict:
        result = await self.db.execute(
            select(
                extract("year", Incident.incident_date).label("year"),
                func.sum(case((Incident.fatal.is_(True), 1), else_=0)).label("fatal"),
                func.sum(case((Incident.fatal.is_(False), 1), else_=0)).label("non_fatal"),
            )
            .where(Incident.incident_date.is_not(None))
            .group_by("year")
            .order_by("year")
        )
        rows = result.all()
        return {
            "data": [
                {"year": int(r.year), "fatal": r.fatal, "non_fatal": r.non_fatal}
                for r in rows
            ]
        }

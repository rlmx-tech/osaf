from datetime import date

from geoalchemy2.functions import ST_AsGeoJSON, ST_MakeEnvelope, ST_SnapToGrid, ST_Centroid, ST_Collect, ST_X, ST_Y
from sqlalchemy import Float, cast, case, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.incident import Incident


def _parse_bbox(bbox: str) -> tuple[float, float, float, float]:
    """Parse 'west,south,east,north' string into floats."""
    parts = [float(x.strip()) for x in bbox.split(",")]
    if len(parts) != 4:
        raise ValueError("bbox must have exactly 4 values: west,south,east,north")
    return parts[0], parts[1], parts[2], parts[3]


def _apply_filters(query, *, classification, species=None, fatal, date_from, date_to, activity=None, severity=None):
    """Apply common filters to a query."""
    # Only include incidents with coordinates
    query = query.where(Incident.coordinates.is_not(None))
    # Only show verified incidents on map
    query = query.where(Incident.verification_status == "verified")

    if classification:
        values = [v.strip() for v in classification.split(",")]
        query = query.where(Incident.classification.in_(values))

    if species:
        query = query.where(
            or_(
                Incident.shark_species_confirmed == species,
                Incident.shark_species_suspected == species,
            )
        )

    if fatal is not None:
        query = query.where(Incident.fatal == fatal)

    if date_from:
        query = query.where(Incident.incident_date >= date.fromisoformat(date_from))

    if date_to:
        query = query.where(Incident.incident_date <= date.fromisoformat(date_to))

    if activity:
        values = [v.strip() for v in activity.split(",")]
        query = query.where(Incident.victim_activity.in_(values))

    if severity:
        values = [v.strip() for v in severity.split(",")]
        query = query.where(Incident.victim_injury_severity.in_(values))

    return query


class MapService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_geojson(
        self,
        bbox: str | None = None,
        classification: str | None = None,
        species: str | None = None,
        fatal: bool | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        activity: str | None = None,
        severity: str | None = None,
    ) -> dict:
        query = select(
            Incident.id,
            Incident.case_number,
            Incident.incident_date,
            Incident.classification,
            Incident.classification_subtype,
            Incident.shark_species_confirmed,
            Incident.shark_species_suspected,
            Incident.victim_activity,
            Incident.victim_injury_severity,
            Incident.fatal,
            Incident.location_description,
            Incident.country,
            ST_AsGeoJSON(Incident.coordinates).label("geojson"),
        )

        query = _apply_filters(
            query,
            classification=classification,
            species=species,
            fatal=fatal,
            date_from=date_from,
            date_to=date_to,
            activity=activity,
            severity=severity,
        )

        if bbox:
            west, south, east, north = _parse_bbox(bbox)
            envelope = ST_MakeEnvelope(west, south, east, north, 4326)
            query = query.where(Incident.coordinates.ST_Within(envelope))

        result = await self.db.execute(query)
        rows = result.all()

        features = []
        for row in rows:
            import json
            geometry = json.loads(row.geojson)
            features.append({
                "type": "Feature",
                "geometry": geometry,
                "properties": {
                    "id": str(row.id),
                    "case_number": row.case_number,
                    "incident_date": row.incident_date.isoformat() if row.incident_date else None,
                    "classification": row.classification,
                    "classification_subtype": row.classification_subtype,
                    "species": row.shark_species_confirmed or row.shark_species_suspected,
                    "activity": row.victim_activity,
                    "severity": row.victim_injury_severity,
                    "fatal": row.fatal,
                    "location": row.location_description,
                    "country": row.country,
                },
            })

        return {
            "type": "FeatureCollection",
            "features": features,
        }

    async def get_clusters(
        self,
        bbox: str | None = None,
        zoom: int = 3,
        classification: str | None = None,
        fatal: bool | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> dict:
        # Grid size decreases as zoom increases (more detail at higher zoom)
        grid_size = 180.0 / (2 ** zoom)

        # Snap points to grid, then group
        snapped = ST_SnapToGrid(Incident.coordinates, grid_size)

        query = select(
            ST_X(ST_Centroid(ST_Collect(Incident.coordinates))).label("lon"),
            ST_Y(ST_Centroid(ST_Collect(Incident.coordinates))).label("lat"),
            func.count().label("count"),
            func.sum(case((Incident.fatal.is_(True), 1), else_=0)).label("fatal_count"),
            # Dominant classification = most common in cluster
            func.mode().within_group(Incident.classification).label("dominant_classification"),
        ).group_by(snapped)

        query = _apply_filters(
            query,
            classification=classification,
            fatal=fatal,
            date_from=date_from,
            date_to=date_to,
        )

        if bbox:
            west, south, east, north = _parse_bbox(bbox)
            envelope = ST_MakeEnvelope(west, south, east, north, 4326)
            query = query.where(Incident.coordinates.ST_Within(envelope))

        result = await self.db.execute(query)
        rows = result.all()

        clusters = []
        for row in rows:
            clusters.append({
                "longitude": row.lon,
                "latitude": row.lat,
                "count": row.count,
                "fatal_count": row.fatal_count,
                "dominant_classification": row.dominant_classification,
            })

        return {"data": clusters}

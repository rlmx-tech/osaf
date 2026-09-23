"""Which incidents count as historical, and how the public API filters them.

An incident is historical when OSAF first recorded it more than a year after it
happened: a GSAF import of a 1960 bite, or a news piece looking back at one.
The flag is about when OSAF learned of an event, not where the record came
from. The first version tagged anything with a GSAF source, and that hid
current incidents the GSAF delta backfill had also cited.

Measured against submitted_at, which never changes, so the tag stays the same
until someone corrects the incident date.
"""

from datetime import UTC, date, datetime, timedelta
from typing import Literal

from app.models.incident import Incident

HISTORICAL_LAG = timedelta(days=365)

# exclude: current-era only. only: historical only. all: no filter.
HistoricalMode = Literal["exclude", "only", "all"]
DEFAULT_HISTORICAL_MODE: HistoricalMode = "all"


def recorded_late(incident_date: date | None, recorded_at: datetime) -> bool:
    """True when the incident was first recorded more than a year after it happened.

    An undated incident is never historical: with no date there is no lag to measure.
    """
    if incident_date is None:
        return False
    return recorded_at.astimezone(UTC).date() - incident_date > HISTORICAL_LAG


def apply_historical_filter(query, mode: HistoricalMode):
    """Narrow an Incident query to the requested mode."""
    if mode == "only":
        return query.where(Incident.is_historical.is_(True))
    if mode == "exclude":
        return query.where(Incident.is_historical.is_(False))
    return query

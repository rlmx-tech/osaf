import pytest
from collector.models import ExtractedIncident
from collector.pipeline import derive_event_type


def _incident(classification: str) -> ExtractedIncident:
    return ExtractedIncident(
        location_description="X", country="Y", classification=classification,
        source_url="https://u", source_title="t",
    )


@pytest.mark.parametrize("inc,expected", [
    (None, "news"),
    (_incident("sighting"), "sighting"),
    (_incident("unprovoked"), "attack"),
    (_incident("boat_bite"), "attack"),
    (_incident("not_confirmed"), "attack"),
])
def test_derive_event_type(inc, expected):
    assert derive_event_type(inc) == expected

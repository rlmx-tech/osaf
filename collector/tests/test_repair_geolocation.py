import httpx

from collector.coastline import inland_distance_km
from collector.repair_geolocation_2026 import CORRECTIONS, _auth_headers


def test_secure_login_cookie_is_promoted_to_bearer_header():
    response = httpx.Response(
        200,
        headers={"set-cookie": "access_token=test-token; Secure; HttpOnly"},
        request=httpx.Request("POST", "http://backend/api/v1/auth/login"),
    )

    assert _auth_headers(response) == {"Authorization": "Bearer test-token"}


def test_repair_manifest_has_unique_expected_scope():
    assert len(CORRECTIONS) == 21


def test_verified_repair_points_are_not_far_inland():
    for correction in CORRECTIONS.values():
        if correction.latitude is None:
            continue
        assert correction.longitude is not None
        assert inland_distance_km(
            correction.latitude, correction.longitude
        ) < 25.0


def test_unsupported_locations_are_explicitly_cleared():
    cleared = {
        case for case, correction in CORRECTIONS.items()
        if correction.latitude is None
    }
    assert cleared == {
        "OSAF-2026-0001",
        "OSAF-2026-0060",
        "OSAF-2026-6391",
        "OSAF-2026-6455",
    }

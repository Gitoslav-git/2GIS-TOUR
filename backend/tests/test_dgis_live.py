import os

import pytest

from gulyay.geo import DgisGeoProvider
from gulyay.models import QueryPreview


pytestmark = pytest.mark.integration


@pytest.mark.parametrize("city_id", ["tula", "vladimir", "moscow", "borovsk"])
def test_live_places_and_walking_route_for_pilot_city(city_id):
    if not os.getenv("DGIS_PLACES_API_KEY") or not os.getenv("DGIS_ROUTING_API_KEY"):
        pytest.skip("2GIS server keys are not configured")
    provider = DgisGeoProvider()
    center = provider.resolve_city_center(city_id)
    preview = QueryPreview(
        cityId=city_id, durationMinutes=180, durationSource="text",
        interests=["достопримечательности"], includeFood=False, withChildren=False,
        unusualPlaces=False, centerOnly=True, locationHint="центр", warnings=[],
    )
    area = provider.resolve_search_area(city_id, preview.locationHint, center)
    places = provider.search_places(city_id, preview, area)
    assert places
    leg = provider.walking_leg(center, (places[0].lat, places[0].lon), 0, 1)
    assert leg.distanceMeters >= 0
    assert leg.durationSeconds >= 0
    assert len(leg.geometry) >= 2

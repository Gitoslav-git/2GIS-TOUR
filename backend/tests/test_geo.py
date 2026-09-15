import json

import httpx
import pytest

from gulyay.geo import (DgisGeoProvider, GeoAuthenticationError,
                        GeoInvalidResponse, GeoRateLimited, GeoRouteNotFound,
                        GeoUnavailable, clear_geo_caches)
from gulyay.models import QueryPreview


def response(request: httpx.Request) -> httpx.Response:
    if request.url.host == "catalog.api.2gis.com":
        query = request.url.params.get("q")
        if query == "Тула":
            items = [{"id": "city-2gis", "name": "Тула", "point": {"lat": 54.193, "lon": 37.617}}]
        elif query == "Заречье, Тула":
            items = [{"id": "area-2gis", "name": "Заречье", "full_name": "Заречье, Тула",
                      "point": {"lat": 54.225, "lon": 37.62}}]
        else:
            items = [{
                "id": "real-2gis-place", "name": "Тульский кремль",
                "point": {"lat": 54.196, "lon": 37.619},
                "rubrics": [{"name": "Достопримечательности"}], "schedule": {"is_24x7": True},
                "is_routing_available": True,
            }]
        return httpx.Response(200, json={"meta": {"code": 200}, "result": {"items": items}})
    assert request.url.host == "routing.api.2gis.com"
    body = json.loads(request.content)
    assert body["transport"] == "walking"
    assert all(point["type"] == "walking" for point in body["points"])
    return httpx.Response(200, json={
        "status": "OK", "result": [{"total_distance": 430, "total_duration": 330,
            "begin_pedestrian_path": {"geometry": {"selection": "LINESTRING(37.617 54.193, 37.618 54.194)"}},
            "maneuvers": [{"outcoming_path": {"geometry": [
                {"selection": "LINESTRING(37.618 54.194 100, 37.619 54.196 110)"}]}}]}],
    })


def preview(center=True):
    return QueryPreview(cityId="tula", durationMinutes=180, durationSource="text",
                        interests=["кремль"], includeFood=False, withChildren=False,
                        unusualPlaces=False, centerOnly=center,
                        locationHint="центр" if center else None, warnings=[])


@pytest.fixture(autouse=True)
def clean_caches():
    clear_geo_caches()
    yield
    clear_geo_caches()


def test_places_and_walking_route_use_real_provider_payloads():
    provider = DgisGeoProvider("places-secret", "routing-secret", httpx.MockTransport(response))
    center = provider.resolve_city_center("tula")
    assert center == (54.193, 37.617)
    area = provider.resolve_search_area("tula", "центр", center)
    places = provider.search_places("tula", preview(), area)
    assert places[0].placeId == "real-2gis-place"
    leg = provider.walking_leg(center, (places[0].lat, places[0].lon), 0, 1)
    assert leg.distanceMeters == 430 and leg.durationSeconds == 330
    assert leg.geometry == [(37.617, 54.193), (37.618, 54.194), (37.619, 54.196)]


def test_center_request_uses_smaller_search_radius():
    radii = []
    def capture(request):
        if request.url.host == "catalog.api.2gis.com":
            radii.append(request.url.params.get("radius"))
        return response(request)
    provider = DgisGeoProvider("p", "r", httpx.MockTransport(capture))
    center = (54.193, 37.617)
    provider.search_places("tula", preview(center=True), provider.resolve_search_area("tula", "центр", center))
    provider.search_places("tula", preview(center=False), provider.resolve_search_area("tula", None, center))
    assert radii == ["3500", "12000"]


def test_direction_and_named_area_become_explicit_search_anchors():
    provider = DgisGeoProvider("p", "r", httpx.MockTransport(response))
    center = (54.193, 37.617)
    north = provider.resolve_search_area("tula", "север города", center)
    named = provider.resolve_search_area("tula", "Заречье", center)
    assert north.source == "direction" and north.lat > center[0]
    assert north.label == "Север города"
    assert named.source == "2gis" and named.label == "Заречье, Тула"


def test_places_and_routing_results_are_cached():
    calls = {"places": 0, "routing": 0}
    def capture(request):
        calls["places" if request.url.host == "catalog.api.2gis.com" else "routing"] += 1
        return response(request)
    provider = DgisGeoProvider("p", "r", httpx.MockTransport(capture))
    provider.resolve_city_center("tula")
    provider.resolve_city_center("tula")
    provider.walking_leg((54.193, 37.617), (54.196, 37.619), 0, 1)
    provider.walking_leg((54.193, 37.617), (54.196, 37.619), 4, 5)
    assert calls == {"places": 1, "routing": 1}


def test_rate_limit_retries_then_opens_circuit(monkeypatch):
    monkeypatch.setenv("DGIS_MAX_RETRIES", "1")
    calls, sleeps = [], []
    def limited(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "3"}, json={})
    provider = DgisGeoProvider("p", "r", httpx.MockTransport(limited),
                                sleeper=sleeps.append, clock=lambda: 100.0)
    with pytest.raises(GeoRateLimited) as first:
        provider.resolve_city_center("tula")
    assert first.value.retry_after_seconds == 3
    assert sleeps == [3] and len(calls) == 2
    with pytest.raises(GeoRateLimited):
        provider.resolve_city_center("tula")
    assert len(calls) == 2


@pytest.mark.parametrize("status,error", [(401, GeoAuthenticationError), (500, GeoUnavailable)])
def test_provider_errors_never_become_fake_places(status, error):
    transport = httpx.MockTransport(lambda request: httpx.Response(status, json={}))
    provider = DgisGeoProvider("p", "r", transport)
    with pytest.raises(error):
        provider.resolve_city_center("tula")


def test_routing_without_geometry_is_rejected():
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={
        "status": "OK", "result": [{"total_distance": 20, "total_duration": 10}]}))
    with pytest.raises(GeoInvalidResponse):
        DgisGeoProvider("p", "r", transport).walking_leg((1, 2), (3, 4), 0, 1)


def test_missing_pedestrian_route_is_explicit():
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={
        "status": "ROUTE_NOT_FOUND", "result": []}))
    with pytest.raises(GeoRouteNotFound):
        DgisGeoProvider("p", "r", transport).walking_leg((1, 2), (3, 4), 0, 1)

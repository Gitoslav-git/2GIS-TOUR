import json

import httpx
import pytest

from gulyay.geo import (DgisGeoProvider, GeoAuthenticationError,
                        GeoInvalidResponse, GeoPlaceNotFound, GeoRateLimited,
                        GeoRouteNotFound, GeoUnavailable, clear_geo_caches)
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


def test_borovsk_city_center_is_resolved_by_exact_city_name():
    def borovsk(request):
        assert request.url.params.get("q") == "Боровск"
        return httpx.Response(200, json={
            "meta": {"code": 200},
            "result": {"items": [{
                "id": "borovsk-city", "name": "Боровск",
                "point": {"lat": 55.2073, "lon": 36.4833},
            }]},
        })

    provider = DgisGeoProvider("p", "r", httpx.MockTransport(borovsk))
    assert provider.resolve_city_center("borovsk") == (55.2073, 36.4833)


def test_large_routing_geometry_is_bounded_and_keeps_ends():
    coordinates = ", ".join(
        f"{36.48 + index * 0.00001:.5f} {55.20 + index * 0.00001:.5f}"
        for index in range(1000)
    )

    def large_route(request):
        return httpx.Response(200, json={
            "status": "OK", "result": [{
                "total_distance": 5000, "total_duration": 3600,
                "begin_pedestrian_path": {
                    "geometry": {"selection": f"LINESTRING({coordinates})"},
                },
            }],
        })

    provider = DgisGeoProvider("p", "r", httpx.MockTransport(large_route))
    leg = provider.walking_leg((55.20, 36.48), (55.20999, 36.48999), 0, 1)
    assert len(leg.geometry) == 300
    assert leg.geometry[0] == (36.48, 55.20)
    assert leg.geometry[-1] == (36.48999, 55.20999)


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


def test_generic_walk_searches_outdoor_places_to_fill_evening_route():
    queries = []
    def capture(request):
        if request.url.host == "catalog.api.2gis.com":
            queries.append(request.url.params.get("q"))
        return response(request)
    provider = DgisGeoProvider("p", "r", httpx.MockTransport(capture))
    generic = preview(center=True).model_copy(update={"interests": []})
    area = provider.resolve_search_area("tula", "центр", (54.193, 37.617))
    provider.search_places("tula", generic, area)
    assert queries == ["достопримечательности", "парки и скверы"]


def test_manual_search_returns_only_provider_candidates_near_selected_city():
    provider = DgisGeoProvider("p", "r", httpx.MockTransport(response))
    places = provider.search_candidates("tula", "кремль")
    assert [place.placeId for place in places] == ["real-2gis-place"]
    assert places[0].name == "Тульский кремль"


def test_automatic_search_rejects_ritual_and_unrelated_branches():
    def mixed(request):
        items = [
            {"id": "ritual", "name": "Ритуал, бюро ритуальных услуг",
             "point": {"lat": 54.194, "lon": 37.618},
             "rubrics": [{"name": "Ритуальные услуги"}], "is_routing_available": True},
            {"id": "shop", "name": "Магазин у дома",
             "point": {"lat": 54.195, "lon": 37.619},
             "rubrics": [{"name": "Продукты"}], "is_routing_available": True},
            {"id": "museum", "name": "Музей оружия",
             "point": {"lat": 54.196, "lon": 37.620},
             "rubrics": [{"name": "Музеи"}], "is_routing_available": True},
        ]
        return httpx.Response(200, json={"meta": {"code": 200}, "result": {"items": items}})
    provider = DgisGeoProvider("p", "r", httpx.MockTransport(mixed))
    area = provider.resolve_search_area("tula", "центр", (54.193, 37.617))
    places = provider.search_places("tula", preview(), area)
    assert [place.placeId for place in places] == ["museum"]


def test_food_search_does_not_turn_unrelated_branch_into_restaurant():
    def unrelated(request):
        item = {"id": "ritual", "name": "Ритуальные услуги",
                "point": {"lat": 54.194, "lon": 37.618},
                "rubrics": [{"name": "Ритуальные услуги"}], "is_routing_available": True}
        return httpx.Response(200, json={"meta": {"code": 200}, "result": {"items": [item]}})
    provider = DgisGeoProvider("p", "r", httpx.MockTransport(unrelated))
    food_preview = preview().model_copy(update={"includeFood": True})
    area = provider.resolve_search_area("tula", "центр", (54.193, 37.617))
    assert provider.search_places("tula", food_preview, area) == []


def test_resolve_places_batches_ids_and_restores_requested_order():
    calls = []
    def by_id(request):
        calls.append(request)
        if request.url.params.get("q") == "Тула":
            items = [{"id": "city", "name": "Тула", "point": {"lat": 54.193, "lon": 37.617}}]
        else:
            assert request.url.path.endswith("/items/byid")
            assert request.url.params.get("id") == "first,second"
            items = [
                {"id": "first", "name": "Кремль", "city_alias": "tula",
                 "point": {"lat": 54.196, "lon": 37.619}, "is_routing_available": True},
                {"id": "second", "name": "Набережная", "city_alias": "tula",
                 "point": {"lat": 54.197, "lon": 37.62}, "is_routing_available": True},
            ]
        return httpx.Response(200, json={"meta": {"code": 200}, "result": {"items": items}})
    provider = DgisGeoProvider("p", "r", httpx.MockTransport(by_id))
    resolved = provider.resolve_places("tula", ["second", "first"])
    assert [item.placeId for item in resolved] == ["second", "first"]
    assert len(calls) == 2


def test_resolve_places_rejects_another_city():
    def foreign(request):
        if request.url.params.get("q") == "Тула":
            items = [{"id": "city", "name": "Тула", "point": {"lat": 54.193, "lon": 37.617}}]
        else:
            items = [{"id": "foreign", "name": "Чужое место", "city_alias": "moscow",
                      "point": {"lat": 55.7558, "lon": 37.6173}}]
        return httpx.Response(200, json={"meta": {"code": 200}, "result": {"items": items}})
    provider = DgisGeoProvider("p", "r", httpx.MockTransport(foreign))
    with pytest.raises(GeoPlaceNotFound):
        provider.resolve_places("tula", ["foreign"])


def test_direction_and_named_area_become_explicit_search_anchors():
    provider = DgisGeoProvider("p", "r", httpx.MockTransport(response))
    center = (54.193, 37.617)
    north = provider.resolve_search_area("tula", "север города", center)
    named = provider.resolve_search_area("tula", "Заречье", center)
    assert north.source == "direction" and north.lat > center[0]
    assert north.label == "Север города"
    assert named.source == "2gis" and named.label == "Заречье, Тула"


def test_named_start_prefers_best_text_match_not_first_catalog_item():
    def stations(request):
        items = [
            {"id": "wrong", "name": "Кутузовский проспект",
             "full_name": "Москва, Кутузовский проспект", "point": {"lat": 55.74, "lon": 37.55}},
            {"id": "right", "name": "Кутузовская",
             "full_name": "МЦК Кутузовская, Москва", "point": {"lat": 55.74, "lon": 37.534}},
        ]
        return httpx.Response(200, json={"meta": {"code": 200}, "result": {"items": items}})
    provider = DgisGeoProvider("p", "r", httpx.MockTransport(stations))
    area = provider.resolve_search_area(
        "moscow", "МЦК Кутузовская", (55.7558, 37.6173),
    )
    assert area.label == "МЦК Кутузовская, Москва"
    assert area.lon == 37.534


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


def test_upstream_calls_are_globally_paced_when_enabled():
    now, sleeps = [100.0], []

    def sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={}))
    provider = DgisGeoProvider("p", "r", transport, sleeper=sleep, clock=lambda: now[0])
    provider.min_request_interval = 0.75
    provider._request("GET", "https://catalog.api.2gis.com/test")
    provider._request("GET", "https://catalog.api.2gis.com/test")
    assert sleeps == [0.75]


def test_rate_limit_does_not_retry_and_opens_circuit(monkeypatch):
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
    assert sleeps == [] and len(calls) == 1
    with pytest.raises(GeoRateLimited):
        provider.resolve_city_center("tula")
    assert len(calls) == 1


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

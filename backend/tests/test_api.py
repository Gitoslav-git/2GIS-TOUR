from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from gulyay.api import (IDEMPOTENT_REVISIONS, IDEMPOTENT_ROUTES, RECENT_ROUTES,
                        app, get_geo_provider, get_intent_provider,
                        get_route_repository)
from gulyay.geo import GeoRateLimited, GeoUnavailable
from gulyay.models import IntentExtraction, PlaceCandidate, RouteLeg, SearchArea
from gulyay.repository import RouteRepository

client = TestClient(app)
repository = RouteRepository(":memory:")


class FakeIntent:
    def __init__(self):
        self.calls = 0

    def extract(self, query):
        self.calls += 1
        return IntentExtraction(cityText="Тула", durationMinutes=120, interests=["история"],
                                includeFood=False, withChildren=False, unusualPlaces=False,
                                centerOnly=True, locationHint="центр")


class FakeGeo:
    def ensure_configured(self): pass
    def resolve_city_center(self, city_id): return 54.193, 37.617
    def resolve_search_area(self, city_id, location_hint, center):
        return SearchArea(label="Центр города", lat=center[0], lon=center[1],
                          radiusMeters=3500, source="city")
    def search_places(self, city_id, preview, area):
        return [PlaceCandidate(placeId="real-provider-id", name="Тульский кремль",
                               lat=54.196, lon=37.619, rubrics=["Достопримечательности"],
                               schedule={"is_24x7": True}, isFood=False)]
    def walking_leg(self, start, end, from_order, to_order):
        return RouteLeg(fromOrder=from_order, toOrder=to_order, distanceMeters=450,
                        durationSeconds=360, geometry=[[37.617, 54.193], [37.619, 54.196]])


class RateLimitedGeo(FakeGeo):
    def resolve_city_center(self, city_id):
        raise GeoRateLimited(17)


class MissingGeo:
    def ensure_configured(self):
        raise GeoUnavailable()


@pytest.fixture(autouse=True)
def reset_state():
    repository.clear()
    app.dependency_overrides[get_route_repository] = lambda: repository
    yield
    app.dependency_overrides.clear()
    IDEMPOTENT_ROUTES.clear()
    IDEMPOTENT_REVISIONS.clear()
    RECENT_ROUTES.clear()


def test_pilot_cities_are_explicit():
    response = client.get("/v1/cities")
    assert response.status_code == 200
    assert response.json() == {"cities": [
        {"cityId": "tula", "name": "Тула"},
        {"cityId": "vladimir", "name": "Владимир"},
    ]}


def test_never_publish_a_fabricated_route():
    app.dependency_overrides[get_geo_provider] = MissingGeo
    session = str(uuid4())
    response = client.post("/v1/routes", headers={"X-Device-Session": session,
        "X-Request-Id": str(uuid4())}, json={"cityId": "tula", "query": "Посмотреть кремль за четыре часа",
        "deviceSessionId": session})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "GEO_UNAVAILABLE"
    assert "points" not in response.json()


def test_builds_and_saves_real_provider_route_idempotently():
    intent = FakeIntent()
    app.dependency_overrides[get_intent_provider] = lambda: intent
    app.dependency_overrides[get_geo_provider] = FakeGeo
    session, request_id = str(uuid4()), str(uuid4())
    body = {"cityId": "tula", "query": "Тула, центр и история на два часа",
            "deviceSessionId": session}
    headers = {"X-Device-Session": session, "X-Request-Id": request_id}
    first = client.post("/v1/routes", headers=headers, json=body)
    second = client.post("/v1/routes", headers=headers, json=body)
    assert first.status_code == second.status_code == 200
    assert first.json()["routeId"] == second.json()["routeId"]
    assert first.json()["points"][0]["placeId"] == "real-provider-id"
    assert first.json()["legs"][0]["geometry"] == [[37.617, 54.193], [37.619, 54.196]]
    assert intent.calls == 1


def test_same_request_with_new_request_id_uses_recent_result_cache():
    intent = FakeIntent()
    app.dependency_overrides[get_intent_provider] = lambda: intent
    app.dependency_overrides[get_geo_provider] = FakeGeo
    session = str(uuid4())
    body = {"cityId": "tula", "query": "Тула, центр и история на два часа",
            "deviceSessionId": session}
    first = client.post("/v1/routes", headers={"X-Device-Session": session,
        "X-Request-Id": str(uuid4())}, json=body)
    second = client.post("/v1/routes", headers={"X-Device-Session": session,
        "X-Request-Id": str(uuid4())}, json=body)
    assert first.json()["routeId"] == second.json()["routeId"]
    assert intent.calls == 1


def test_change_query_creates_atomic_next_version():
    intent = FakeIntent()
    app.dependency_overrides[get_intent_provider] = lambda: intent
    app.dependency_overrides[get_geo_provider] = FakeGeo
    session = str(uuid4())
    headers = {"X-Device-Session": session, "X-Request-Id": str(uuid4())}
    created = client.post("/v1/routes", headers=headers, json={
        "cityId": "tula", "query": "История в центре два часа", "deviceSessionId": session})
    route_id = created.json()["routeId"]
    revised = client.post(f"/v1/routes/{route_id}/revisions", headers={
        "X-Device-Session": session, "X-Request-Id": str(uuid4())}, json={
        "baseVersion": 1, "mode": "CHANGE_QUERY", "query": "Архитектура на севере два часа"})
    assert revised.status_code == 200
    assert revised.json()["routeId"] == route_id
    assert revised.json()["routeVersion"] == 2
    assert revised.json()["query"] == "Архитектура на севере два часа"


def test_stale_revision_does_not_replace_current_route():
    app.dependency_overrides[get_intent_provider] = FakeIntent
    app.dependency_overrides[get_geo_provider] = FakeGeo
    session = str(uuid4())
    created = client.post("/v1/routes", headers={"X-Device-Session": session}, json={
        "cityId": "tula", "query": "История в центре два часа", "deviceSessionId": session})
    route_id = created.json()["routeId"]
    result = client.post(f"/v1/routes/{route_id}/revisions", headers={
        "X-Device-Session": session}, json={"baseVersion": 2, "mode": "CHANGE_QUERY",
        "query": "Другой маршрут на два часа"})
    assert result.status_code == 409
    assert result.json()["error"]["code"] == "VERSION_CONFLICT"
    stored = repository.get(UUID(route_id), UUID(session))
    assert stored is not None and stored[0].routeVersion == 1


def test_2gis_rate_limit_has_retry_contract():
    app.dependency_overrides[get_intent_provider] = FakeIntent
    app.dependency_overrides[get_geo_provider] = RateLimitedGeo
    session = str(uuid4())
    result = client.post("/v1/routes", headers={"X-Device-Session": session}, json={
        "cityId": "tula", "query": "История два часа", "deviceSessionId": session})
    assert result.status_code == 429
    assert result.headers["Retry-After"] == "17"
    assert result.json()["error"]["code"] == "RATE_LIMITED"
    assert result.json()["error"]["details"]["retryAfterSeconds"] == 17


def test_route_requires_matching_guest_session():
    response = client.post("/v1/routes", json={"cityId": "tula", "query": "Прогулка 4 часа",
                                              "deviceSessionId": str(uuid4())})
    assert response.status_code == 401


def test_rejects_unknown_filter_instead_of_ignoring_it():
    session = str(uuid4())
    response = client.post("/v1/routes", headers={"X-Device-Session": session}, json={
        "cityId": "tula", "query": "Прогулка 4 часа", "deviceSessionId": session,
        "filters": {"secretFallback": True}})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_rejects_whitespace_only_query():
    session = str(uuid4())
    response = client.post("/v1/routes", headers={"X-Device-Session": session}, json={
        "cityId": "vladimir", "query": "     ", "deviceSessionId": session})
    assert response.status_code == 400

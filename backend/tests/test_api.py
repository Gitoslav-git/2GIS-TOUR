from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from gulyay.api import (IDEMPOTENT_ROUTES, ROUTES, app, get_geo_provider,
                        get_intent_provider)
from gulyay.models import IntentExtraction, PlaceCandidate, RouteLeg

client = TestClient(app)


class FakeIntent:
    def __init__(self):
        self.calls = 0

    def extract(self, query):
        self.calls += 1
        return IntentExtraction(cityText="Тула", durationMinutes=120, interests=["история"],
                                includeFood=False, withChildren=False, unusualPlaces=False,
                                centerOnly=True)


class FakeGeo:
    def ensure_configured(self): pass
    def resolve_city_center(self, city_id): return 54.193, 37.617
    def search_places(self, city_id, preview, center):
        return [PlaceCandidate(placeId="real-provider-id", name="Тульский кремль",
                               lat=54.196, lon=37.619, rubrics=["Достопримечательности"],
                               schedule={"is_24x7": True}, isFood=False)]
    def walking_leg(self, start, end, from_order, to_order):
        return RouteLeg(fromOrder=from_order, toOrder=to_order, distanceMeters=450,
                        durationSeconds=360, geometry=[[37.617, 54.193], [37.619, 54.196]])


@pytest.fixture(autouse=True)
def reset_state():
    yield
    app.dependency_overrides.clear()
    ROUTES.clear()
    IDEMPOTENT_ROUTES.clear()


def test_pilot_cities_are_explicit():
    response = client.get("/v1/cities")
    assert response.status_code == 200
    assert response.json() == {"cities": [
        {"cityId": "tula", "name": "Тула"},
        {"cityId": "vladimir", "name": "Владимир"},
    ]}


def test_never_publish_a_fabricated_route():
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

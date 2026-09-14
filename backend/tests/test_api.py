from uuid import uuid4

from fastapi.testclient import TestClient

from gulyay.api import app

client = TestClient(app)


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

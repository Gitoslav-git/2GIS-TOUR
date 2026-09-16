from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from gulyay.api import app, get_intent_provider
from gulyay.intent import (IntentAuthenticationError, IntentInvalidResponse,
                           IntentUnavailable)
from gulyay.models import IntentExtraction

client = TestClient(app)


class FakeIntentProvider:
    def __init__(self, output=None, error=None):
        self.output = output
        self.error = error
        self.calls = 0

    def extract(self, query):
        self.calls += 1
        if self.error:
            raise self.error
        return self.output


def parsed(**updates):
    values = dict(cityText=None, durationMinutes=None, interests=[],
                  includeFood=None, withChildren=None, unusualPlaces=None, centerOnly=None,
                  locationHint=None, startLocationHint=None, directionHint=None,
                  startLocationAmbiguous=False, preferShortWalks=None)
    values.update(updates)
    return IntentExtraction.model_validate(values)


def request(**updates):
    session = str(uuid4())
    body = dict(cityId="tula", query="Хочу посмотреть храмы 2 часа и поесть",
                filters={}, deviceSessionId=session)
    body.update(updates)
    return client.post("/v1/routes/interpret", json=body,
                       headers={"X-Device-Session": session, "X-Request-Id": str(uuid4())})


@pytest.fixture(autouse=True)
def reset_overrides():
    yield
    app.dependency_overrides.clear()


def test_extracts_preferences_without_claiming_real_locations():
    provider = FakeIntentProvider(parsed(cityText="Тула", durationMinutes=120,
                                         interests=["храмы", "храмы"], includeFood=True))
    app.dependency_overrides[get_intent_provider] = lambda: provider
    result = request()
    assert result.status_code == 200
    assert result.json() == {
        "cityId": "tula", "durationMinutes": 120, "durationSource": "text",
        "interests": ["храмы"], "includeFood": True, "withChildren": False,
        "unusualPlaces": False, "centerOnly": False, "locationHint": None,
        "startLocationHint": None, "directionHint": None, "preferShortWalks": False,
        "warnings": [],
    }
    assert provider.calls == 1
    assert "placeId" not in result.text and "lat" not in result.text


def test_filter_takes_precedence_over_text_and_false_is_explicit():
    app.dependency_overrides[get_intent_provider] = lambda: FakeIntentProvider(
        parsed(durationMinutes=120, includeFood=True, withChildren=True))
    result = request(filters={"durationMinutes": 240, "includeFood": False,
                              "withChildren": False})
    assert result.status_code == 200
    assert result.json()["durationMinutes"] == 240
    assert result.json()["durationSource"] == "filter"
    assert result.json()["includeFood"] is False
    assert result.json()["withChildren"] is False


def test_default_duration_is_visible():
    app.dependency_overrides[get_intent_provider] = lambda: FakeIntentProvider(parsed())
    result = request()
    assert result.status_code == 200
    assert result.json()["durationMinutes"] == 180
    assert result.json()["durationSource"] == "default"
    assert result.json()["warnings"]


def test_center_preference_is_preserved():
    app.dependency_overrides[get_intent_provider] = lambda: FakeIntentProvider(
        parsed(durationMinutes=60, includeFood=True, centerOnly=False))
    result = request(query="Хочу гулять в ЦЕНТРЕ час с обедом")
    assert result.status_code == 200
    assert result.json()["centerOnly"] is True
    assert result.json()["locationHint"] == "центр"


@pytest.mark.parametrize("query,expected", [
    ("Хочу гулять на севере города два часа", "север города"),
    ("Хочу гулять на юго-западе города два часа", "юго-запад города"),
])
def test_direction_preference_is_preserved_even_if_llm_misses_it(query, expected):
    app.dependency_overrides[get_intent_provider] = lambda: FakeIntentProvider(
        parsed(durationMinutes=120, locationHint=None))
    result = request(query=query)
    assert result.status_code == 200
    assert result.json()["locationHint"] == expected


def test_named_area_from_llm_is_preserved():
    app.dependency_overrides[get_intent_provider] = lambda: FakeIntentProvider(
        parsed(durationMinutes=120, locationHint="Заречье"))
    result = request(query="Погулять по Заречью два часа")
    assert result.status_code == 200
    assert result.json()["locationHint"] == "Заречье"


def test_start_direction_and_short_walks_are_not_collapsed_into_center():
    app.dependency_overrides[get_intent_provider] = lambda: FakeIntentProvider(parsed(
        cityText="Москва", durationMinutes=120,
        startLocationHint="МЦК Кутузовская", directionHint="центр",
        centerOnly=False, preferShortWalks=True,
    ))
    result = request(cityId="moscow", query=(
        "Хочу погулять от МЦК Кутузовская в сторону ЦЕНТРА 2 часа, "
        "желательно чтобы до локаций идти было не далеко"
    ))
    assert result.status_code == 200
    assert result.json()["startLocationHint"] == "МЦК Кутузовская"
    assert result.json()["directionHint"] == "центр"
    assert result.json()["locationHint"] is None
    assert result.json()["centerOnly"] is False
    assert result.json()["preferShortWalks"] is True


def test_control_query_is_recovered_even_if_llm_misses_geo_semantics():
    app.dependency_overrides[get_intent_provider] = lambda: FakeIntentProvider(parsed(
        cityText="Москва", durationMinutes=120,
    ))
    result = request(cityId="moscow", query=(
        "Хочу погулять от МЦК Кутузовская в сторону ЦЕНТРА 2 часа, "
        "желательно чтобы до локаций идти было не далеко"
    ))
    assert result.status_code == 200
    assert result.json()["startLocationHint"] == "мцк кутузовская"
    assert result.json()["directionHint"] == "центр"
    assert result.json()["centerOnly"] is False
    assert result.json()["preferShortWalks"] is True


def test_ambiguous_personal_start_requires_clarification():
    app.dependency_overrides[get_intent_provider] = lambda: FakeIntentProvider(parsed(
        cityText="Москва", durationMinutes=120,
        startLocationHint="офис на Кутузе", startLocationAmbiguous=False,
    ))
    result = request(cityId="moscow", query="Хочу погулять от офиса на Кутузе два часа")
    assert result.status_code == 422
    assert result.json()["error"]["details"]["fields"] == ["startLocationHint"]


def test_city_conflict_asks_for_clarification():
    app.dependency_overrides[get_intent_provider] = lambda: FakeIntentProvider(parsed(cityText="Владимир"))
    result = request()
    assert result.status_code == 422
    assert result.json()["error"]["code"] == "QUERY_NEEDS_CLARIFICATION"
    assert result.json()["error"]["details"]["fields"] == ["cityId"]


def test_unknown_city_does_not_silently_route_to_selected_city():
    app.dependency_overrides[get_intent_provider] = lambda: FakeIntentProvider(parsed(cityText="Москва"))
    result = request()
    assert result.status_code == 422
    assert result.json()["error"]["details"]["fields"] == ["cityId"]


def test_out_of_range_duration_requires_clarification():
    app.dependency_overrides[get_intent_provider] = lambda: FakeIntentProvider(parsed(durationMinutes=20))
    assert request().json()["error"]["details"]["fields"] == ["durationMinutes"]


@pytest.mark.parametrize("error,code,status", [
    (IntentUnavailable(), "LLM_UNAVAILABLE", 503),
    (IntentAuthenticationError(), "LLM_AUTH_ERROR", 503),
    (IntentInvalidResponse(), "LLM_INVALID_RESPONSE", 502),
])
def test_external_errors_have_stable_codes(error, code, status):
    app.dependency_overrides[get_intent_provider] = lambda: FakeIntentProvider(error=error)
    result = request()
    assert result.status_code == status
    assert result.json()["error"]["code"] == code
    assert result.json()["error"]["requestId"]


def test_fake_provider_is_schema_checked_too():
    app.dependency_overrides[get_intent_provider] = lambda: FakeIntentProvider(
        output={"cityText": None, "durationMinutes": 120, "interests": [],
                "includeFood": False, "withChildren": False, "unusualPlaces": False,
                "centerOnly": False,
                "locationHint": None,
                "startLocationHint": None, "directionHint": None,
                "startLocationAmbiguous": False, "preferShortWalks": False,
                "madeUpPlaceId": "invented"})
    result = request()
    assert result.status_code == 502
    assert result.json()["error"]["code"] == "LLM_INVALID_RESPONSE"


def test_unauthorized_request_does_not_consume_llm_call():
    provider = FakeIntentProvider(parsed())
    app.dependency_overrides[get_intent_provider] = lambda: provider
    result = client.post("/v1/routes/interpret", json={"cityId": "tula", "query": "Тула на 2 часа",
                                                         "deviceSessionId": str(uuid4())})
    assert result.status_code == 401
    assert provider.calls == 0


def test_no_keys_cannot_be_mistaken_for_success(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    result = request()
    assert result.status_code == 503
    assert result.json()["error"]["code"] == "LLM_UNAVAILABLE"

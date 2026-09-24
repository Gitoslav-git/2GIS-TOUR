from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from gulyay.api import app, get_intent_provider
from gulyay.intent import (IntentAuthenticationError, IntentInvalidResponse,
                           IntentUnavailable, configured_model)
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
    duration_minutes = updates.pop("durationMinutes", None)
    clarification = updates.pop("clarificationFields", [])
    if duration_minutes is not None and not 30 <= duration_minutes <= 720:
        duration_minutes = None
        clarification = [*clarification, "durationMinutes"]
    raw_interests = updates.pop("interests", [])
    concept_map = {
        "храм": "RELIGIOUS_PLACES", "архитект": "ARCHITECTURE",
        "истор": "HISTORIC_PLACES", "музе": "MUSEUMS", "парк": "PARKS",
    }
    interests = []
    for value in raw_interests:
        if isinstance(value, dict):
            interests.append(value)
            continue
        concept = next((result for word, result in concept_map.items()
                        if word in value.casefold()), None)
        if concept:
            interests.append({"concept": concept, "priority": "HIGH",
                              "strength": "SOFT", "sourceText": value,
                              "broadeningAllowed": True})
    include_food = updates.pop("includeFood", None)
    center_only = updates.pop("centerOnly", None)
    location_hint = updates.pop("locationHint", None)
    start_hint = updates.pop("startLocationHint", None)
    ambiguous = updates.pop("startLocationAmbiguous", False)
    prefer_short = updates.pop("preferShortWalks", None)
    parsed_limit = updates.pop("maxWalkingMinutes", None)
    values = {
        "schemaVersion": "1.0", "cityText": updates.pop("cityText", None),
        "duration": {"mode": "TARGET" if duration_minutes else "DEFAULT",
                     "targetMinutes": duration_minutes, "maxMinutes": None,
                     "minMinutes": None},
        "start": {"explicitLocationText": start_hint, "isExplicit": bool(start_hint),
                  "isAmbiguous": ambiguous},
        "area": {"preference": "CENTER" if center_only else
                 ("DISTRICT" if location_hint else "ANY"),
                 "locationText": location_hint, "strength": "SOFT"},
        "directionHint": updates.pop("directionHint", None),
        "mobility": {"transportMode": "WALKING",
                     "walkingEffort": "LOW" if prefer_short else "NOT_SPECIFIED",
                     "compactness": "HIGH" if prefer_short else "NORMAL",
                     "minimizeTotalWalking": bool(prefer_short),
                     "preferredLegMinutes": parsed_limit if prefer_short else None,
                     "maxLegMinutes": None, "maxLegDistanceMeters": None,
                     "maxTotalWalkingMinutes": None,
                     "maxTotalWalkingDistanceMeters": None},
        "interests": interests, "exclusions": [],
        "food": {"mode": "REQUIRED" if include_food else "NONE", "timing": "ANY",
                 "exactTime": None, "preferences": [], "excludedPreferences": []},
        "routeStyle": {"pace": "NORMAL", "placeDensity": "NORMAL",
                       "variety": "NORMAL", "popularityPreference": "NOT_SPECIFIED",
                       "requestedPlaceCount": None},
        "withChildren": bool(updates.pop("withChildren", False)),
        "unusualPlaces": bool(updates.pop("unusualPlaces", False)),
        "clarificationFields": clarification,
    }
    assert not updates, updates
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
    body = result.json()
    assert body["cityId"] == "tula"
    assert body["durationMinutes"] == 120
    assert body["durationMode"] == "TARGET"
    assert body["interests"] == ["RELIGIOUS_PLACES"]
    assert body["foodMode"] == "REQUIRED"
    assert body["maxWalkingMinutes"] is None
    assert provider.calls == 1
    assert "placeId" not in result.text and "lat" not in result.text


def test_borovsk_city_name_is_accepted_for_borovsk_request():
    app.dependency_overrides[get_intent_provider] = lambda: FakeIntentProvider(
        parsed(cityText="Боровск", durationMinutes=120))
    result = request(cityId="borovsk", query="Погулять по Боровску два часа")
    assert result.status_code == 200
    assert result.json()["cityId"] == "borovsk"


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
    assert result.json()["preferredWalkingMinutes"] == 20
    assert result.json()["maxWalkingMinutes"] is None


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
    assert result.json()["preferredWalkingMinutes"] == 20
    assert result.json()["maxWalkingMinutes"] is None


@pytest.mark.parametrize("query,parsed_limit,expected_max,expected_preferred", [
    ("Желательно, чтобы до локаций идти было недалеко", None, None, 20),
    ("Между точками должно быть максимум 15-20 минут", None, 20, 20),
    ("Чтобы идти было не больше 12 минут между локациями", None, 12, 20),
    ("Хочу короткие переходы", 17, None, 17),
])
def test_walking_phrases_keep_soft_and_hard_limits_separate(
        query, parsed_limit, expected_max, expected_preferred):
    app.dependency_overrides[get_intent_provider] = lambda: FakeIntentProvider(parsed(
        durationMinutes=120, preferShortWalks=True, maxWalkingMinutes=parsed_limit,
        locationHint="до локаций идти недалеко",
        startLocationHint="до локаций идти недалеко",
        directionHint="короткие переходы",
    ))
    result = request(query=query)
    assert result.status_code == 200
    assert result.json()["locationHint"] is None
    assert result.json()["startLocationHint"] is None
    assert result.json()["directionHint"] is None
    assert result.json()["maxWalkingMinutes"] == expected_max
    assert result.json()["preferredWalkingMinutes"] == expected_preferred


def test_walking_instruction_is_removed_from_interests_before_2gis_search():
    app.dependency_overrides[get_intent_provider] = lambda: FakeIntentProvider(parsed(
        durationMinutes=120,
        interests=["архитектура", "чтобы недалеко ходить", "без очередей"],
        preferShortWalks=False,
    ))
    result = request(query="Хочу посмотреть архитектуру, чтобы недалеко ходить")
    assert result.status_code == 200
    assert result.json()["interests"] == ["ARCHITECTURE"]
    assert result.json()["preferShortWalks"] is True
    assert result.json()["maxWalkingMinutes"] is None
    assert result.json()["preferredWalkingMinutes"] == 20


def test_only_unknown_conditions_fall_back_without_breaking_preview():
    app.dependency_overrides[get_intent_provider] = lambda: FakeIntentProvider(parsed(
        durationMinutes=120,
        interests=["чтобы было без очередей", "по пути", "не знаю"],
    ))
    result = request(query="Погулять два часа, желательно без очередей")
    assert result.status_code == 200
    assert result.json()["interests"] == []


@pytest.mark.parametrize("query,expected", [
    ("Между точками должно быть не больше 800 метров", 800),
    ("Хочу ходить максимум 1 км между локациями", 1000),
])
def test_walking_distance_remains_an_exact_hard_distance(query, expected):
    app.dependency_overrides[get_intent_provider] = lambda: FakeIntentProvider(parsed(
        durationMinutes=120, interests=[query],
    ))
    result = request(query=query)
    assert result.status_code == 200
    assert result.json()["interests"] == []
    assert result.json()["preferShortWalks"] is True
    assert result.json()["maxWalkingMinutes"] is None
    assert result.json()["maxWalkingDistanceMeters"] == expected


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
    result = request(query="Хочу погулять по Владимиру")
    assert result.status_code == 422
    assert result.json()["error"]["code"] == "QUERY_NEEDS_CLARIFICATION"
    assert result.json()["error"]["details"]["fields"] == ["cityId"]


def test_other_supported_city_does_not_silently_route_to_selected_city():
    app.dependency_overrides[get_intent_provider] = lambda: FakeIntentProvider(parsed(cityText="Москва"))
    result = request(query="Хочу погулять по Москве")
    assert result.status_code == 422
    assert result.json()["error"]["details"]["fields"] == ["cityId"]


@pytest.mark.parametrize("query,city_text", [
    ("Хочу прогуляться по центру города 5 часов", "город"),
    ("Я хочу прогуляться", "Владимир"),
    ("Я хочу прогуляться", None),
])
def test_selected_city_is_authoritative_when_query_has_no_explicit_city(query, city_text):
    app.dependency_overrides[get_intent_provider] = lambda: FakeIntentProvider(parsed(
        cityText=city_text, clarificationFields=["cityId"],
    ))
    result = request(cityId="moscow", query=query)
    assert result.status_code == 200
    assert result.json()["cityId"] == "moscow"


def test_explicit_unsupported_city_still_requires_clarification():
    app.dependency_overrides[get_intent_provider] = lambda: FakeIntentProvider(
        parsed(cityText="Казань"))
    result = request(query="Хочу погулять по Казани")
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


def test_stronger_model_is_default_but_environment_can_override(monkeypatch):
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    assert configured_model() == "gpt-5.4-mini"
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5-mini")
    assert configured_model() == "gpt-5-mini"


@pytest.mark.parametrize("query,parsed_mode,expected", [
    ("Хочу гулять 3 часа", "TARGET", "TARGET"),
    ("У меня максимум 3 часа", "TARGET", "MAXIMUM"),
    ("Хочу погулять около трёх часов", "TARGET", "APPROXIMATE"),
])
def test_duration_semantics_are_not_collapsed_into_one_budget(query, parsed_mode, expected):
    intent = parsed(durationMinutes=180)
    intent = intent.model_copy(update={
        "duration": intent.duration.model_copy(update={"mode": parsed_mode}),
    })
    app.dependency_overrides[get_intent_provider] = lambda: FakeIntentProvider(intent)
    result = request(query=query)
    assert result.status_code == 200
    assert result.json()["durationMode"] == expected
    assert result.json()["targetDurationMinutes"] == 180


def test_optional_food_and_soft_exclusion_stay_soft():
    data = parsed(durationMinutes=180).model_dump()
    data["food"].update({"mode": "OPTIONAL", "timing": "MIDDLE",
                         "preferences": ["COFFEE"]})
    data["exclusions"] = [{"concept": "MUSEUMS", "strength": "SOFT_NEGATIVE"}]
    data["routeStyle"]["pace"] = "RELAXED"
    intent = IntentExtraction.model_validate(data)
    app.dependency_overrides[get_intent_provider] = lambda: FakeIntentProvider(intent)
    result = request(query="Не спеша погулять три часа, лучше без музеев, в середине можно кофе")
    assert result.status_code == 200
    assert result.json()["foodMode"] == "OPTIONAL"
    assert result.json()["foodTiming"] == "MIDDLE"
    assert result.json()["foodPreferences"] == ["COFFEE"]
    assert result.json()["softExclusions"] == ["MUSEUMS"]
    assert result.json()["hardExclusions"] == []
    assert result.json()["routePace"] == "RELAXED"


def test_explicit_place_count_and_specific_cuisine_are_preserved():
    data = parsed(durationMinutes=180).model_dump()
    data["routeStyle"]["requestedPlaceCount"] = 1
    data["food"].update({"mode": "REQUIRED", "timing": "END",
                         "preferences": ["ITALIAN"]})
    intent = IntentExtraction.model_validate(data)
    app.dependency_overrides[get_intent_provider] = lambda: FakeIntentProvider(intent)
    result = request(query="Хочу одно место и в конце итальянскую кухню")
    assert result.status_code == 200
    assert result.json()["requestedPlaceCount"] == 1
    assert result.json()["allowSinglePlace"] is True
    assert result.json()["foodPreferences"] == ["ITALIAN"]
    assert result.json()["foodTiming"] == "END"

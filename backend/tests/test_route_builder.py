from datetime import datetime
from zoneinfo import ZoneInfo

from gulyay.models import (CreateRoute, PlaceCandidate, QueryPreview, RouteLeg,
                           SearchArea)
from gulyay.route_builder import build_route, city_timezone, schedule_status_at


class FakeGeo:
    def __init__(self, candidates):
        self.candidates = candidates

    def ensure_configured(self): pass
    def resolve_city_center(self, city_id): return 54.193, 37.617
    def resolve_search_area(self, city_id, location_hint, center):
        return SearchArea(label="Центр города" if location_hint else "Весь город",
                          lat=center[0], lon=center[1], radiusMeters=3500 if location_hint else 12000,
                          source="city")
    def search_places(self, city_id, preview, area): return self.candidates
    def walking_leg(self, start, end, from_order, to_order):
        return RouteLeg(fromOrder=from_order, toOrder=to_order, distanceMeters=500,
                        durationSeconds=600, geometry=[[37.617, 54.193], [end[1], end[0]]])


def candidate(name, place_id, food=False, schedule=None):
    return PlaceCandidate(placeId=place_id, name=name, lat=54.195, lon=37.62,
                          rubrics=[], schedule=schedule or {}, isFood=food)


def preferences(**updates):
    data = dict(cityId="tula", durationMinutes=180, durationSource="text", interests=["история"],
                includeFood=False, withChildren=False, unusualPlaces=False, centerOnly=False, warnings=[])
    data.update(updates)
    return QueryPreview.model_validate(data)


def test_builds_route_only_from_provider_places_and_legs():
    route = build_route(CreateRoute(cityId="tula", query="История 3 часа"), preferences(),
                        FakeGeo([candidate("Кремль", "2gis-1")]),
                        datetime(2026, 9, 15, 12, tzinfo=ZoneInfo("Europe/Moscow")))
    assert route.points[0].placeId == "2gis-1"
    assert route.legs[0].durationSeconds == 600
    assert route.totalMinutes == 50
    assert route.requestedMinutes == 180
    assert route.unusedMinutes == 130
    assert route.approximateStart is True


def test_center_and_food_are_visible_in_route_warnings():
    route = build_route(CreateRoute(cityId="tula", query="Центр с едой 2 часа"),
                        preferences(durationMinutes=120, includeFood=True, centerOnly=True),
                        FakeGeo([candidate("Кремль", "2gis-1"), candidate("Кафе", "2gis-food", True)]),
                        datetime(2026, 9, 15, 12, tzinfo=ZoneInfo("Europe/Moscow")))
    assert any(point.isFood for point in route.points)
    assert "Область поиска: Центр города" in route.warnings
    assert route.searchArea.label == "Центр города"


def test_schedule_checks_whole_visit_not_only_arrival():
    schedule = {"Tue": {"working_hours": [{"from": "10:00", "to": "13:00"}]}}
    current = datetime(2026, 9, 15, 12, 30, tzinfo=ZoneInfo("Europe/Moscow"))
    assert schedule_status_at(schedule, current, 20) == "OPEN"
    assert schedule_status_at(schedule, current, 40) == "CLOSED"
    assert schedule_status_at({}, current, 40) == "UNKNOWN"


def test_pilot_timezone_is_available_on_windows_and_linux():
    assert datetime(2026, 9, 15, 12, tzinfo=city_timezone()).utcoffset().total_seconds() == 10800


def test_route_adds_another_real_place_to_fill_requested_time():
    places = [candidate(f"Место {index}", f"2gis-{index}", schedule={"is_24x7": True})
              for index in range(1, 4)]
    route = build_route(CreateRoute(cityId="tula", query="История 3 часа"), preferences(),
                        FakeGeo(places),
                        datetime(2026, 9, 15, 12, tzinfo=ZoneInfo("Europe/Moscow")))
    assert len(route.points) == 3
    assert route.totalMinutes == 150
    assert route.requestedMinutes == 180
    assert route.unusedMinutes == 30


def test_large_unused_budget_is_explained_instead_of_hidden():
    route = build_route(CreateRoute(cityId="tula", query="История 3 часа"), preferences(),
                        FakeGeo([candidate("Кремль", "2gis-1", schedule={"is_24x7": True})]),
                        datetime(2026, 9, 15, 12, tzinfo=ZoneInfo("Europe/Moscow")))
    assert any("Осталось 130 мин." in warning for warning in route.warnings)

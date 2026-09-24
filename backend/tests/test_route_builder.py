from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from gulyay.models import (CreateRoute, PlaceCandidate, QueryPreview, RouteLeg,
                           SearchArea, StartLocation)
from gulyay.route_builder import (RouteNotFound, TimeBudgetExceeded, build_route, city_timezone,
                                  rebuild_route_with_points, schedule_status_at)


class FakeGeo:
    def __init__(self, candidates):
        self.candidates = candidates
        self.walking_starts = []

    def ensure_configured(self): pass
    def resolve_city_center(self, city_id): return 54.193, 37.617
    def resolve_search_area(self, city_id, location_hint, center):
        return SearchArea(label="Центр города" if location_hint else "Весь город",
                          lat=center[0], lon=center[1], radiusMeters=3500 if location_hint else 12000,
                          source="city")
    def search_places(self, city_id, preview, area): return self.candidates
    def walking_leg(self, start, end, from_order, to_order):
        self.walking_starts.append(start)
        return RouteLeg(fromOrder=from_order, toOrder=to_order, distanceMeters=500,
                        durationSeconds=600, geometry=[[37.617, 54.193], [end[1], end[0]]])


def candidate(name, place_id, food=False, schedule=None):
    return PlaceCandidate(placeId=place_id, name=name, lat=54.195, lon=37.62,
                          rubrics=[], schedule=schedule or {}, isFood=food)


def preferences(**updates):
    data = dict(cityId="tula", durationMinutes=180, durationSource="text", interests=["история"],
                includeFood=False, withChildren=False, unusualPlaces=False, centerOnly=False,
                maxWalkingMinutes=None, allowSinglePlace=True, warnings=[])
    data.update(updates)
    if data.get("includeFood") and "foodMode" not in updates:
        data["foodMode"] = "REQUIRED"
    return QueryPreview.model_validate(data)


def test_builds_route_only_from_provider_places_and_legs():
    route = build_route(CreateRoute(cityId="tula", query="История 3 часа"), preferences(),
                        FakeGeo([candidate("Кремль", "2gis-1")]),
                        datetime(2026, 9, 15, 12, tzinfo=ZoneInfo("Europe/Moscow")))
    assert route.points[0].placeId == "2gis-1"
    assert route.legs[0].durationSeconds == 600
    assert route.totalMinutes == 60
    assert route.requestedMinutes == 180
    assert route.unusedMinutes == 120
    assert route.approximateStart is True


def test_device_location_is_used_as_real_first_leg_start():
    geo = FakeGeo([candidate("Кремль", "2gis-1")])
    payload = CreateRoute(
        cityId="tula", query="История 3 часа",
        startLocation=StartLocation(lat=54.191, lon=37.615, accuracyMeters=18),
    )
    route = build_route(payload, preferences(), geo,
                        datetime(2026, 9, 15, 12, tzinfo=ZoneInfo("Europe/Moscow")))
    assert route.approximateStart is False
    assert geo.walking_starts[0] == (54.191, 37.615)
    assert route.searchArea == SearchArea(
        label="Рядом с геопозицией", lat=54.191, lon=37.615,
        radiusMeters=6500, source="geo",
    )
    assert all("фактического местоположения" not in warning for warning in route.warnings)


@pytest.mark.parametrize("has_geo,has_text_start,expected_start,expected_source", [
    (True, False, (54.191, 37.615), "USER_GEO"),
    (False, True, (54.210, 37.640), "TEXT_ANCHOR"),
    (False, False, (54.193, 37.617), "CITY_CENTER"),
    (True, True, (54.210, 37.640), "TEXT_ANCHOR"),
])
def test_start_priority_matrix(has_geo, has_text_start, expected_start, expected_source):
    class StartGeo(FakeGeo):
        def resolve_search_area(self, city_id, location_hint, center):
            if location_hint == "вокзал":
                return SearchArea(label="Вокзал", lat=54.210, lon=37.640,
                                  radiusMeters=3000, source="2gis")
            if location_hint == "север":
                return SearchArea(label="Север города", lat=54.250, lon=37.620,
                                  radiusMeters=3500, source="2gis")
            return super().resolve_search_area(city_id, location_hint, center)

    geo = StartGeo([candidate("Кремль", "2gis-1", schedule={"is_24x7": True})])
    payload_data = {"cityId": "tula", "query": "Прогулка 2 часа"}
    if has_geo:
        payload_data["startLocation"] = StartLocation(
            lat=54.191, lon=37.615, accuracyMeters=18,
        )
    preview = preferences(
        durationMinutes=120,
        locationHint="север",
        startLocationHint="вокзал" if has_text_start else None,
    )
    route = build_route(CreateRoute(**payload_data), preview, geo,
                        datetime(2026, 9, 15, 12, tzinfo=ZoneInfo("Europe/Moscow")))
    assert geo.walking_starts[0] == expected_start
    assert (route.startLat, route.startLon) == expected_start
    assert route.startSource == expected_source
    assert route.approximateStart is (expected_source == "CITY_CENTER")


def test_named_start_is_used_before_direction_and_center_is_not_the_start():
    class MoscowGeo(FakeGeo):
        def __init__(self):
            places = [
                PlaceCandidate(placeId="away", name="Назад", lat=55.7400, lon=37.5200,
                               rubrics=[], schedule={"is_24x7": True}, isFood=False),
                PlaceCandidate(placeId="toward", name="По пути к центру", lat=55.7400, lon=37.5450,
                               rubrics=[], schedule={"is_24x7": True}, isFood=False),
            ]
            super().__init__(places)
            self.searched_area = None

        def resolve_city_center(self, city_id): return 55.7558, 37.6173
        def resolve_search_area(self, city_id, location_hint, center):
            if location_hint == "МЦК Кутузовская":
                return SearchArea(label="МЦК Кутузовская", lat=55.7400, lon=37.5340,
                                  radiusMeters=3000, source="2gis")
            if location_hint == "центр":
                return SearchArea(label="Центр города", lat=55.7558, lon=37.6173,
                                  radiusMeters=3500, source="city")
            return super().resolve_search_area(city_id, location_hint, center)
        def search_places(self, city_id, preview, area):
            self.searched_area = area
            return self.candidates

    geo = MoscowGeo()
    preview = preferences(
        cityId="moscow", durationMinutes=120, interests=[],
        startLocationHint="МЦК Кутузовская", directionHint="центр",
        preferShortWalks=True,
    )
    route = build_route(
        CreateRoute(cityId="moscow", query="От МЦК Кутузовская в сторону центра 2 часа"),
        preview, geo, datetime(2026, 9, 16, 12, tzinfo=ZoneInfo("Europe/Moscow")),
    )
    assert geo.walking_starts[0] == (55.7400, 37.5340)
    assert geo.searched_area.lon == 37.5340
    assert geo.searched_area.label == "МЦК Кутузовская → центр"
    assert route.points[0].placeId == "toward"
    assert "Старт по указанному ориентиру: МЦК Кутузовская" in route.warnings
    assert "Направление прогулки: центр" in route.warnings


def test_center_and_food_are_visible_in_route_warnings():
    route = build_route(CreateRoute(cityId="tula", query="Центр с едой 2 часа"),
                        preferences(durationMinutes=150, includeFood=True, centerOnly=True),
                        FakeGeo([candidate("Кремль", "2gis-1"), candidate("Кафе", "2gis-food", True)]),
                        datetime(2026, 9, 15, 12, tzinfo=ZoneInfo("Europe/Moscow")))
    assert any(point.isFood for point in route.points)
    assert "Область поиска: Центр города" in route.warnings
    assert route.searchArea.label == "Центр города"


def test_required_food_at_end_is_not_skipped_when_time_target_is_reached():
    sights = [candidate(f"Место {index}", f"sight-{index}", schedule={"is_24x7": True})
              for index in range(3)]
    food = candidate("Итальянский ресторан", "food", True, {"is_24x7": True}).model_copy(
        update={"matchedFoodPreferences": ["ITALIAN"]},
    )
    route = build_route(
        CreateRoute(cityId="tula", query="Четыре часа, в конце итальянская кухня"),
        preferences(durationMinutes=240, targetDurationMinutes=240,
                    maxDurationMinutes=240, includeFood=True, foodTiming="END",
                    foodPreferences=["ITALIAN"], allowSinglePlace=False),
        FakeGeo([*sights, food]),
        datetime(2026, 9, 15, 12, tzinfo=ZoneInfo("Europe/Moscow")),
    )
    assert route.points[-1].placeId == "food"


def test_density_and_pace_change_how_many_places_fit():
    places = [candidate(f"Место {index}", f"place-{index}", schedule={"is_24x7": True})
              for index in range(8)]
    payload = CreateRoute(cityId="tula", query="Прогулка четыре часа")
    slow = build_route(
        payload,
        preferences(durationMinutes=240, targetDurationMinutes=240,
                    maxDurationMinutes=240, interests=[], routePace="RELAXED",
                    placeDensity="LOW", allowSinglePlace=False),
        FakeGeo(places),
        datetime(2026, 9, 15, 12, tzinfo=ZoneInfo("Europe/Moscow")),
    )
    intensive = build_route(
        payload,
        preferences(durationMinutes=240, targetDurationMinutes=240,
                    maxDurationMinutes=240, interests=[], routePace="INTENSIVE",
                    placeDensity="HIGH", allowSinglePlace=False),
        FakeGeo(places),
        datetime(2026, 9, 15, 12, tzinfo=ZoneInfo("Europe/Moscow")),
    )
    assert len(intensive.points) > len(slow.points)


def test_ordinary_walk_never_publishes_one_point_route():
    with pytest.raises(RouteNotFound):
        build_route(
            CreateRoute(cityId="tula", query="Прогулка на три часа"),
            preferences(allowSinglePlace=False),
            FakeGeo([candidate("Кремль", "only", schedule={"is_24x7": True})]),
            datetime(2026, 9, 15, 12, tzinfo=ZoneInfo("Europe/Moscow")),
        )


def test_explicit_one_place_request_may_return_one_point():
    route = build_route(
        CreateRoute(cityId="tula", query="Хочу посетить одно место"),
        preferences(durationMinutes=120, requestedPlaceCount=1, allowSinglePlace=True),
        FakeGeo([candidate("Кремль", "only", schedule={"is_24x7": True})]),
        datetime(2026, 9, 15, 12, tzinfo=ZoneInfo("Europe/Moscow")),
    )
    assert [point.placeId for point in route.points] == ["only"]


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


def test_first_build_checks_at_most_eight_routing_candidates():
    places = [candidate(f"Место {index}", f"2gis-{index}", schedule={"is_24x7": True}).model_copy(
                  update={"lat": 54.195 + index * 0.0001},
              )
              for index in range(1, 11)]
    geo = FakeGeo(places)
    route = build_route(
        CreateRoute(cityId="tula", query="История 10 часов"),
        preferences(durationMinutes=600), geo,
        datetime(2026, 9, 15, 12, tzinfo=ZoneInfo("Europe/Moscow")),
    )
    assert len(geo.walking_starts) == 8
    assert len(route.points) == 8


def test_compares_affordable_alternative_using_shared_legs(monkeypatch):
    from gulyay import route_builder

    places = [candidate(f"Место {index}", str(index), schedule={"is_24x7": True}).model_copy(
        update={"lat": 54.195 + index * 0.0001},
    ) for index in range(13)]
    primary = places[:6]
    expensive_alternative = places[7:13]
    affordable_alternative = [*places[:5], places[6]]
    # The first route looks good before Routing but misses the real time target.
    # A disjoint six-leg alternative must not consume the remaining checks before
    # the six-leg alternative that shares five already verified transitions.
    plans = [route_builder._RoutePlan(str(index), points, 280, 0, False, 90 - index, {})
             for index, points in enumerate(
                 [primary, expensive_alternative, affordable_alternative])]
    monkeypatch.setattr(route_builder, "_make_route_plans", lambda *args: plans)
    monkeypatch.setenv("ROUTE_MAX_ROUTING_CHECKS", "7")

    class SharedLegGeo(FakeGeo):
        def __init__(self):
            super().__init__(places)
            self.calls = []

        def walking_leg(self, start, end, from_order, to_order):
            self.calls.append((start, end))
            seconds = 900 if end == (places[6].lat, places[6].lon) else 60
            return RouteLeg(fromOrder=from_order, toOrder=to_order,
                            durationSeconds=seconds, distanceMeters=100,
                            geometry=[[start[1], start[0]], [end[1], end[0]]])

    geo = SharedLegGeo()
    route = build_route(
        CreateRoute(cityId="tula", query="Хочу гулять пять часов"),
        preferences(durationMinutes=300, targetDurationMinutes=300,
                    maxDurationMinutes=300, interests=[], allowSinglePlace=False),
        geo, datetime(2026, 9, 15, 12, tzinfo=ZoneInfo("Europe/Moscow")),
    )
    assert [point.placeId for point in route.points] == [item.placeId for item in affordable_alternative]
    assert route.planningStatus == "SUCCESS"
    assert route.totalMinutes == 260
    assert len(geo.calls) == len(set(geo.calls)) == 7
    assert [(leg.fromOrder, leg.toOrder) for leg in route.legs] == [(i, i + 1) for i in range(6)]
    assert all(leg.geometry[-1] == (point.lon, point.lat)
               for leg, point in zip(route.legs, route.points))


def test_compares_successful_routes_instead_of_stopping_at_first(monkeypatch):
    from gulyay import route_builder

    places = [candidate(f"Место {index}", str(index), schedule={"is_24x7": True}).model_copy(
        update={"lat": 54.195 + index * 0.0001},
    ) for index in range(3)]
    plans = [route_builder._RoutePlan(str(i), points, 100, 0, False, 90 - i, {})
             for i, points in enumerate([places[:2], [places[0], places[2]]])]
    monkeypatch.setattr(route_builder, "_make_route_plans", lambda *args: plans)
    monkeypatch.setenv("ROUTE_MAX_ROUTING_CHECKS", "3")

    class ActualDurationGeo(FakeGeo):
        def walking_leg(self, start, end, from_order, to_order):
            self.walking_starts.append(start)
            seconds = 1200 if end == (places[2].lat, places[2].lon) else 600
            return RouteLeg(fromOrder=from_order, toOrder=to_order,
                            durationSeconds=seconds, distanceMeters=500,
                            geometry=[[start[1], start[0]], [end[1], end[0]]])

    geo = ActualDurationGeo(places)
    route = build_route(
        CreateRoute(cityId="tula", query="Прогулка на 110 минут"),
        preferences(durationMinutes=110, targetDurationMinutes=110,
                    maxDurationMinutes=110, interests=[], allowSinglePlace=False),
        geo, datetime(2026, 9, 15, 12, tzinfo=ZoneInfo("Europe/Moscow")),
    )
    assert route.points[-1].placeId == places[2].placeId
    assert route.totalMinutes == 110
    assert route.planningStatus == "SUCCESS"
    assert len(geo.walking_starts) == 3


def test_routing_cache_handles_exhaustion_unreachable_and_directed_legs():
    from gulyay.geo import GeoRouteNotFound
    from gulyay.route_builder import _RoutingChecks

    class DirectedGeo(FakeGeo):
        def walking_leg(self, start, end, from_order, to_order):
            self.walking_starts.append(start)
            if end == (54.0, 37.0):
                raise GeoRouteNotFound()
            return super().walking_leg(start, end, from_order, to_order)

    geo = DirectedGeo([])
    checks = _RoutingChecks(2)
    first, second = (54.0, 37.0), (54.1, 37.1)
    leg = checks.walking_leg(geo, first, second, 0)
    with pytest.raises(GeoRouteNotFound):
        checks.walking_leg(geo, second, first, 0)
    count = len(geo.walking_starts)
    reused = checks.walking_leg(geo, first, second, 4)
    with pytest.raises(GeoRouteNotFound):
        checks.walking_leg(geo, second, first, 4)
    assert checks.remaining == 0
    assert len(geo.walking_starts) == count
    assert (leg.fromOrder, leg.toOrder) == (0, 1)
    assert (reused.fromOrder, reused.toOrder) == (4, 5)
    assert reused.geometry == leg.geometry


@pytest.mark.parametrize("wider_is_better", [True, False])
def test_returned_area_belongs_to_selected_route(wider_is_better):
    local_places = [candidate("Место в центре", "local", schedule={"is_24x7": True})]
    wider_places = [candidate(f"Место {i}", f"wide-{i}", schedule={"is_24x7": True}).model_copy(
        update={"lat": 54.198 + i * 0.0001},
    ) for i in range(3)]

    class ExpandingGeo(FakeGeo):
        def __init__(self):
            super().__init__(local_places)
            self.areas = []

        def search_places(self, city_id, preview, area):
            self.areas.append(area)
            return wider_places if len(self.areas) > 1 and wider_is_better else local_places

    geo = ExpandingGeo()
    route = build_route(
        CreateRoute(cityId="tula", query="Прогулка в центре на 150 минут"),
        preferences(durationMinutes=150, targetDurationMinutes=150,
                    maxDurationMinutes=150, interests=[], locationHint="центр", areaStrength="SOFT"),
        geo, datetime(2026, 9, 15, 12, tzinfo=ZoneInfo("Europe/Moscow")),
    )
    assert len(geo.areas) == 2
    expected = geo.areas[1] if wider_is_better else geo.areas[0]
    assert route.searchArea == expected
    assert f"Область поиска: {expected.label}" in route.warnings
    assert any("поиск расширен на город" in warning for warning in route.warnings) == wider_is_better
    assert all("поиск был расширен" not in warning for warning in route.warnings)


def test_hard_area_never_expands():
    class HardAreaGeo(FakeGeo):
        def resolve_search_area(self, city_id, location_hint, center):
            assert location_hint == "центр"
            return super().resolve_search_area(city_id, location_hint, center)

    geo = HardAreaGeo([candidate("Одно место", "local", schedule={"is_24x7": True})])
    with pytest.raises(RouteNotFound):
        build_route(
            CreateRoute(cityId="tula", query="Только в центре, прогулка на три часа"),
            preferences(locationHint="центр", areaStrength="HARD", allowSinglePlace=False),
            geo, datetime(2026, 9, 15, 12, tzinfo=ZoneInfo("Europe/Moscow")),
        )


def test_walking_limit_skips_long_leg_without_reporting_geo_failure():
    near = PlaceCandidate(placeId="near", name="Рядом", lat=54.194, lon=37.618,
                          rubrics=[], schedule={"is_24x7": True}, isFood=False)
    far = PlaceCandidate(placeId="far", name="Далеко", lat=54.25, lon=37.70,
                         rubrics=[], schedule={"is_24x7": True}, isFood=False)

    class LimitedGeo(FakeGeo):
        def walking_leg(self, start, end, from_order, to_order):
            self.walking_starts.append(start)
            seconds = 600 if end == (near.lat, near.lon) else 1800
            return RouteLeg(fromOrder=from_order, toOrder=to_order,
                            distanceMeters=500 if seconds == 600 else 2500,
                            durationSeconds=seconds,
                            geometry=[[start[1], start[0]], [end[1], end[0]]])

    geo = LimitedGeo([far, near])
    route = build_route(
        CreateRoute(cityId="tula", query="Недалеко идти два часа"),
        preferences(durationMinutes=120, preferShortWalks=True, maxWalkingMinutes=20),
        geo, datetime(2026, 9, 15, 12, tzinfo=ZoneInfo("Europe/Moscow")),
    )
    assert [point.placeId for point in route.points] == ["near"]
    assert route.maxWalkingMinutes == 20
    assert all(leg.durationSeconds <= 1200 for leg in route.legs)
    assert "Каждый пеший переход — не более 20 мин." in route.warnings


def test_soft_short_walk_preference_does_not_destroy_five_hour_route():
    places = [candidate(f"Место {index}", f"2gis-{index}", schedule={"is_24x7": True}).model_copy(
                  update={"lat": 54.195 + index * 0.0001},
              )
              for index in range(1, 7)]

    class SoftWalkGeo(FakeGeo):
        def walking_leg(self, start, end, from_order, to_order):
            self.walking_starts.append(start)
            seconds = 1500 if end == (places[2].lat, places[2].lon) else 900
            return RouteLeg(fromOrder=from_order, toOrder=to_order,
                            distanceMeters=2000 if seconds == 1500 else 1000,
                            durationSeconds=seconds,
                            geometry=[[start[1], start[0]], [end[1], end[0]]])

    route = build_route(
        CreateRoute(cityId="tula", query="Хочу гулять 5 часов, но много ходить не хочу"),
        preferences(durationMinutes=300, targetDurationMinutes=300,
                    maxDurationMinutes=300, preferShortWalks=True,
                    compactness="HIGH", minimizeTotalWalking=True,
                    preferredWalkingMinutes=20, maxWalkingMinutes=None),
        SoftWalkGeo(places),
        datetime(2026, 9, 15, 12, tzinfo=ZoneInfo("Europe/Moscow")),
    )
    assert route.planningStatus == "SUCCESS"
    assert route.durationUtilization >= 0.85
    assert len(route.points) >= 5
    assert any(leg.durationSeconds > 20 * 60 for leg in route.legs)


def test_best_interest_cluster_wins_over_first_candidates_from_provider():
    generic = [
        PlaceCandidate(placeId=f"generic-{index}", name=f"Обычное место {index}",
                       lat=54.193 + index * 0.0001, lon=37.617 + index * 0.0001,
                       rubrics=["Достопримечательности"], schedule={"is_24x7": True},
                       isFood=False)
        for index in range(8)
    ]
    museums = [
        PlaceCandidate(placeId=f"museum-{index}", name=f"Музей {index}",
                       lat=54.205 + index * 0.0001, lon=37.630 + index * 0.0001,
                       rubrics=["Музеи"], schedule={"is_24x7": True}, isFood=False,
                       matchedConcepts=["MUSEUMS"])
        for index in range(2)
    ]
    route = build_route(
        CreateRoute(cityId="tula", query="Хочу музеи на три часа"),
        preferences(interests=["MUSEUMS"], interestPriorities={"MUSEUMS": "HIGH"},
                    targetDurationMinutes=180, maxDurationMinutes=180,
                    allowSinglePlace=False),
        FakeGeo([*generic, *museums]),
        datetime(2026, 9, 15, 12, tzinfo=ZoneInfo("Europe/Moscow")),
    )
    assert [point.placeId for point in route.points] == ["museum-0", "museum-1"]
    assert route.planningScore >= 70


def test_maximum_duration_is_a_ceiling_not_a_target_to_fill():
    places = [candidate(f"Место {index}", f"2gis-{index}", schedule={"is_24x7": True})
              for index in range(4)]
    route = build_route(
        CreateRoute(cityId="tula", query="У меня максимум пять часов"),
        preferences(durationMinutes=300, durationMode="MAXIMUM",
                    targetDurationMinutes=300, maxDurationMinutes=300,
                    interests=[], allowSinglePlace=False),
        FakeGeo(places),
        datetime(2026, 9, 15, 12, tzinfo=ZoneInfo("Europe/Moscow")),
    )
    assert route.totalMinutes < 300
    assert route.planningStatus == "SUCCESS"
    assert "DURATION_TARGET" not in route.unmetPreferences


def test_hard_exclusion_is_rechecked_even_if_provider_adapter_misses_it():
    museums = [
        PlaceCandidate(placeId=f"museum-{index}", name=f"Музей {index}",
                       lat=54.195 + index * 0.0001, lon=37.620,
                       rubrics=["Музеи"], schedule={"is_24x7": True}, isFood=False)
        for index in range(2)
    ]
    with pytest.raises(RouteNotFound):
        build_route(
            CreateRoute(cityId="tula", query="Без музеев, прогулка два часа"),
            preferences(durationMinutes=120, interests=[], hardExclusions=["MUSEUMS"],
                        allowSinglePlace=False),
            FakeGeo(museums),
            datetime(2026, 9, 15, 12, tzinfo=ZoneInfo("Europe/Moscow")),
        )


def test_large_unused_budget_is_explained_instead_of_hidden():
    route = build_route(CreateRoute(cityId="tula", query="История 3 часа"), preferences(),
                        FakeGeo([candidate("Кремль", "2gis-1", schedule={"is_24x7": True})]),
                        datetime(2026, 9, 15, 12, tzinfo=ZoneInfo("Europe/Moscow")))
    assert route.planningStatus == "DEGRADED"
    assert "DURATION_TARGET" in route.unmetPreferences
    assert any("Маршрут заполнен" in warning for warning in route.warnings)


def test_manual_point_order_is_preserved_and_all_legs_are_rebuilt():
    first = candidate("Первое", "2gis-1", schedule={"is_24x7": True})
    second = candidate("Второе", "2gis-2", schedule={"is_24x7": True})
    geo = FakeGeo([first, second])
    source_payload = CreateRoute(cityId="tula", query="История 3 часа")
    source = build_route(source_payload, preferences(), geo,
                         datetime(2026, 9, 15, 12, tzinfo=ZoneInfo("Europe/Moscow")))
    changed = rebuild_route_with_points(
        source, source_payload, [second, first], geo,
        datetime(2026, 9, 15, 12, tzinfo=ZoneInfo("Europe/Moscow")),
    )
    assert [point.placeId for point in changed.points] == ["2gis-2", "2gis-1"]
    assert [(leg.fromOrder, leg.toOrder) for leg in changed.legs] == [(0, 1), (1, 2)]
    assert changed.totalMinutes == 100


def test_reordering_points_rebuilds_legs_and_changes_total_time():
    first = PlaceCandidate(placeId="near", name="Ближняя", lat=0.0, lon=0.001,
                           rubrics=[], schedule={"is_24x7": True}, isFood=False)
    second = PlaceCandidate(placeId="far", name="Дальняя", lat=0.0, lon=0.010,
                            rubrics=[], schedule={"is_24x7": True}, isFood=False)

    class VariableLegGeo(FakeGeo):
        def resolve_city_center(self, city_id): return 0.0, 0.0
        def walking_leg(self, start, end, from_order, to_order):
            self.walking_starts.append(start)
            units = abs(end[0] - start[0]) + abs(end[1] - start[1])
            return RouteLeg(fromOrder=from_order, toOrder=to_order,
                            distanceMeters=round(units * 1_000_000),
                            durationSeconds=round(units * 60_000),
                            geometry=[[start[1], start[0]], [end[1], end[0]]])

    geo = VariableLegGeo([first, second])
    payload = CreateRoute(cityId="tula", query="Прогулка 3 часа")
    source = build_route(
        payload, preferences(durationMinutes=180), geo,
        datetime(2026, 9, 15, 12, tzinfo=ZoneInfo("Europe/Moscow")),
    )
    by_id = {item.placeId: item for item in (first, second)}
    reversed_candidates = [by_id[point.placeId] for point in reversed(source.points)]
    geo.walking_starts.clear()
    changed = rebuild_route_with_points(
        source, payload, reversed_candidates, geo,
        datetime(2026, 9, 15, 12, tzinfo=ZoneInfo("Europe/Moscow")),
    )
    assert [point.placeId for point in changed.points] == [
        point.placeId for point in reversed(source.points)
    ]
    assert geo.walking_starts[0] == (0.0, 0.0)
    assert source.totalMinutes != changed.totalMinutes


def test_point_edit_keeps_text_start_and_direction_explanation():
    place = candidate("Кремль", "2gis-1", schedule={"is_24x7": True})
    geo = FakeGeo([place])
    source = build_route(
        CreateRoute(cityId="tula", query="От вокзала в сторону центра 2 часа"),
        preferences(durationMinutes=120, startLocationHint="вокзал",
                    directionHint="центр", preferShortWalks=True),
        geo, datetime(2026, 9, 15, 12, tzinfo=ZoneInfo("Europe/Moscow")),
    )
    changed = rebuild_route_with_points(
        source, CreateRoute(cityId="tula", query=source.query), [place], geo,
        datetime(2026, 9, 15, 12, tzinfo=ZoneInfo("Europe/Moscow")),
    )
    assert any(warning.startswith("Старт по указанному ориентиру:")
               for warning in changed.warnings)
    assert "Направление прогулки: центр" in changed.warnings
    assert "Из полноценных вариантов выбран наиболее компактный маршрут" in changed.warnings


def test_point_edit_recovers_exact_start_from_route_created_before_0_5_4():
    place = candidate("Кремль", "2gis-1", schedule={"is_24x7": True})
    geo = FakeGeo([place])
    source = build_route(
        CreateRoute(cityId="tula", query="От вокзала 2 часа"),
        preferences(durationMinutes=120, startLocationHint="вокзал"), geo,
        datetime(2026, 9, 15, 12, tzinfo=ZoneInfo("Europe/Moscow")),
    ).model_copy(update={"startLat": None, "startLon": None, "startSource": "LEGACY"})
    source.legs[0].geometry[0] = (37.700, 54.250)
    geo.walking_starts.clear()
    rebuild_route_with_points(
        source, CreateRoute(cityId="tula", query=source.query), [place], geo,
        datetime(2026, 9, 15, 12, tzinfo=ZoneInfo("Europe/Moscow")),
    )
    assert geo.walking_starts[0] == (54.250, 37.700)


def test_manual_edit_over_budget_does_not_publish_partial_route():
    places = [candidate(f"Место {index}", f"2gis-{index}", schedule={"is_24x7": True})
              for index in range(1, 5)]
    geo = FakeGeo(places)
    payload = CreateRoute(cityId="tula", query="История 3 часа")
    source = build_route(payload, preferences(), geo,
                         datetime(2026, 9, 15, 12, tzinfo=ZoneInfo("Europe/Moscow")))
    with pytest.raises(TimeBudgetExceeded) as error:
        rebuild_route_with_points(
            source, payload, places, geo,
            datetime(2026, 9, 15, 12, tzinfo=ZoneInfo("Europe/Moscow")),
        )
    assert error.value.minimum_minutes == 200

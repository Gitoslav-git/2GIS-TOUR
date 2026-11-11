import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from gulyay.models import (Filters, Route, RouteGroup, RouteLeg, RoutePoint,
                           RouteWaypoint, RouteWaypointLeg, RouteZoneGeometry,
                           SearchArea, StartWalk, WalkAction, WalkPosition, WalkState)
from gulyay.walk import (WalkInvalidPosition, WalkInvalidState, apply_action,
                         register_position, session_at, start_walk)
from gulyay.visit_zones import VisitZone, VisitZones, bundled_visit_zones_path


def route(points=2, total_minutes=120):
    route_points = [
        RoutePoint(order=index, placeId=f"place-{index}", name=f"Точка {index}",
                   lat=54.19 + index * 0.001, lon=37.61 + index * 0.001,
                   visitMinutes=40, scheduleStatus="OPEN", isFood=False)
        for index in range(1, points + 1)
    ]
    return Route(
        routeId=uuid4(), routeVersion=1, status="READY", cityId="tula",
        query="Прогулка два часа", filters=Filters(),
        searchArea=SearchArea(label="Весь город", lat=54.193, lon=37.617,
                              radiusMeters=12000, source="city"),
        approximateStart=True, requestedMinutes=120, totalMinutes=total_minutes,
        unusedMinutes=max(0, 120 - total_minutes), points=route_points,
        legs=[RouteLeg(fromOrder=index - 1, toOrder=index, distanceMeters=300,
                       durationSeconds=240, geometry=[[37.61, 54.19], [37.62, 54.20]])
              for index in range(1, points + 1)], warnings=[],
    )


def position(point, measured_at, accuracy=10):
    return WalkPosition(lat=point.lat, lon=point.lon, accuracyMeters=accuracy,
                        measuredAt=measured_at)


def grouped_route():
    itinerary = route(points=1, total_minutes=45)
    point = itinerary.points[0]
    first_lon = point.lon - 0.001
    second_lon = point.lon + 0.001
    square = lambda lon: [[
        [lon - 0.0002, point.lat - 0.0002], [lon + 0.0002, point.lat - 0.0002],
        [lon + 0.0002, point.lat + 0.0002], [lon - 0.0002, point.lat + 0.0002],
        [lon - 0.0002, point.lat - 0.0002],
    ]]
    group = RouteGroup(
        pointOrder=1, catalogId="msk-parent",
        waypoints=[RouteWaypoint(
            order=1, catalogId="msk-child", placeId="catalog:msk-child",
            name="Child", lat=point.lat, lon=second_lon, relation="CLUSTER_MEMBER",
        )],
        waypointLegs=[RouteWaypointLeg(
            fromWaypointOrder=0, toWaypointOrder=1,
            distanceMeters=130, durationSeconds=100,
            geometry=[(first_lon, point.lat), (second_lon, point.lat)],
        )],
        visitZone=RouteZoneGeometry(
            type="MultiPolygon", coordinates=[square(first_lon), square(second_lon)],
        ),
    )
    point = point.model_copy(update={
        "lon": first_lon, "catalogId": "msk-parent",
    })
    return itinerary.model_copy(update={
        "points": [point], "routeGroupsEnabled": True, "routeGroups": [group],
    })


def adjacent_grouped_route():
    """Two nearby zones whose boundary gap is well below the normal exit radius."""
    itinerary = route(points=2, total_minutes=60)
    first = itinerary.points[0]
    second = itinerary.points[1].model_copy(update={
        "lat": first.lat, "lon": first.lon + 0.0006,
    })

    def group(point_order, point, catalog_id):
        ring = [[
            [point.lon - 0.00015, point.lat - 0.00015],
            [point.lon + 0.00015, point.lat - 0.00015],
            [point.lon + 0.00015, point.lat + 0.00015],
            [point.lon - 0.00015, point.lat + 0.00015],
            [point.lon - 0.00015, point.lat - 0.00015],
        ]]
        return RouteGroup(
            pointOrder=point_order, catalogId=catalog_id,
            waypoints=[RouteWaypoint(
                order=1, catalogId=f"{catalog_id}-child",
                placeId=f"catalog:{catalog_id}-child", name="Child",
                lat=point.lat, lon=point.lon, relation="CLUSTER_MEMBER",
            )],
            waypointLegs=[RouteWaypointLeg(
                fromWaypointOrder=0, toWaypointOrder=1,
                distanceMeters=20, durationSeconds=20,
                geometry=[(point.lon, point.lat), (point.lon, point.lat)],
            )],
            visitZone=RouteZoneGeometry(type="Polygon", coordinates=ring),
        )

    return itinerary.model_copy(update={
        "points": [first, second], "routeGroupsEnabled": True,
        "routeGroups": [
            group(1, first, "msk-first"), group(2, second, "msk-second"),
        ],
    })


def bundled_zones(*catalog_ids):
    payload = json.loads(bundled_visit_zones_path().read_text(encoding="utf-8"))
    wanted = set(catalog_ids)
    return VisitZones({
        feature["properties"]["catalog_id"]: VisitZone(
            catalog_id=feature["properties"]["catalog_id"],
            geometry=feature["geometry"],
        )
        for feature in payload["features"]
        if feature["properties"]["catalog_id"] in wanted
    })


def test_group_zone_creates_one_parent_visit_and_boundary_buffer_prevents_gap_exit():
    start = datetime(2026, 9, 16, 12, tzinfo=timezone.utc)
    itinerary = grouped_route()
    point = itinerary.points[0]
    state = start_walk(itinerary, StartWalk(routeVersion=1), start)
    state, _ = register_position(state, itinerary, position(point, start), start)
    state, reached = register_position(
        state, itinerary, position(point, start + timedelta(seconds=10)),
        start + timedelta(seconds=10),
    )
    assert reached.pointReached is True
    assert len(state.session.visits) == 1
    assert state.session.visits[0].catalogId == "msk-parent"

    gap = WalkPosition(
        lat=point.lat, lon=point.lon + 0.001, accuracyMeters=10,
        measuredAt=start + timedelta(seconds=10),
    )
    state, _ = register_position(state, itinerary, gap, gap.measuredAt)
    state, gap_result = register_position(
        state, itinerary,
        gap.model_copy(update={"measuredAt": start + timedelta(seconds=30)}),
        start + timedelta(seconds=30),
    )
    assert gap_result.pointExited is False
    assert state.session.phase == "VISITING"
    assert len(state.session.visits) == 1


def test_group_requires_actual_zone_entry_and_completes_after_confirmed_exit():
    start = datetime(2026, 9, 16, 12, tzinfo=timezone.utc)
    itinerary = grouped_route()
    point = itinerary.points[0]
    near_but_outside = WalkPosition(
        lat=point.lat + 0.0005, lon=point.lon, accuracyMeters=10, measuredAt=start,
    )
    state = start_walk(itinerary, StartWalk(routeVersion=1), start)
    state, _ = register_position(state, itinerary, near_but_outside, start)
    state, result = register_position(
        state, itinerary,
        near_but_outside.model_copy(update={"measuredAt": start + timedelta(seconds=10)}),
        start + timedelta(seconds=10),
    )
    assert result.pointReached is False

    state, _ = register_position(
        state, itinerary, position(point, start + timedelta(seconds=15)),
        start + timedelta(seconds=15),
    )
    state, _ = register_position(
        state, itinerary, position(point, start + timedelta(seconds=25)),
        start + timedelta(seconds=25),
    )
    far = WalkPosition(
        lat=point.lat + 0.003, lon=point.lon, accuracyMeters=10,
        measuredAt=start + timedelta(seconds=30),
    )
    state, _ = register_position(state, itinerary, far, far.measuredAt)
    for offset in (40, 50):
        state, pending = register_position(
            state, itinerary,
            far.model_copy(update={"measuredAt": start + timedelta(seconds=offset)}),
            start + timedelta(seconds=offset),
        )
        assert pending.pointExited is False
    state, exited = register_position(
        state, itinerary,
        far.model_copy(update={"measuredAt": start + timedelta(seconds=60)}),
        start + timedelta(seconds=60),
    )
    assert exited.pointExited is True
    assert state.session.status == "COMPLETED"
    assert state.session.currentPointOrder is None
    assert len(state.session.visits) == 1


def test_direct_next_zone_transition_skips_distance_threshold_but_keeps_confirmation():
    start = datetime(2026, 9, 16, 12, tzinfo=timezone.utc)
    itinerary = adjacent_grouped_route()
    first, second = itinerary.points
    state = start_walk(itinerary, StartWalk(routeVersion=1), start)
    state, _ = register_position(state, itinerary, position(first, start), start)
    state, reached = register_position(
        state, itinerary, position(first, start + timedelta(seconds=10)),
        start + timedelta(seconds=10),
    )
    assert reached.pointReached is True

    for offset in (20, 30, 40):
        state, pending = register_position(
            state, itinerary, position(second, start + timedelta(seconds=offset)),
            start + timedelta(seconds=offset),
        )
        assert pending.distanceMeters < 70
        assert pending.pointExited is False
        assert pending.pointReached is False
        assert pending.exitConfirmationPending is True

    state, transitioned = register_position(
        state, itinerary, position(second, start + timedelta(seconds=50)),
        start + timedelta(seconds=50),
    )
    assert transitioned.distanceMeters < 70
    assert transitioned.pointExited is True
    assert transitioned.pointReached is True
    assert transitioned.exitConfirmationPending is False
    assert state.session.phase == "VISITING"
    assert state.session.currentPointOrder == 2
    assert [visit.catalogId for visit in state.session.visits] == [
        "msk-first", "msk-second",
    ]
    assert state.session.visits[0].durationSeconds == 40


def test_alexander_garden_to_kremlin_uses_confirmed_direct_zone_transition():
    start = datetime(2026, 9, 16, 12, tzinfo=timezone.utc)
    itinerary = route(points=2, total_minutes=60)
    first = itinerary.points[0].model_copy(update={"catalogId": "msk013"})
    second = itinerary.points[1].model_copy(update={"catalogId": "msk005"})
    itinerary = itinerary.model_copy(update={"points": [first, second]})
    zones = bundled_zones("msk013", "msk005")
    garden = WalkPosition(
        lat=55.7485198, lon=37.612056, accuracyMeters=10, measuredAt=start,
    )
    kremlin = WalkPosition(
        lat=55.74908751071428, lon=37.61266647857143,
        accuracyMeters=10, measuredAt=start + timedelta(seconds=20),
    )
    state = start_walk(itinerary, StartWalk(routeVersion=1), start)
    state, _ = register_position(state, itinerary, garden, start, zones)
    state, reached = register_position(
        state, itinerary,
        garden.model_copy(update={"measuredAt": start + timedelta(seconds=10)}),
        start + timedelta(seconds=10), zones,
    )
    assert reached.pointReached is True
    for offset in (20, 30, 40):
        measured = start + timedelta(seconds=offset)
        state, pending = register_position(
            state, itinerary, kremlin.model_copy(update={"measuredAt": measured}),
            measured, zones,
        )
        assert pending.distanceMeters < 70
        assert pending.exitConfirmationPending is True
        assert pending.pointExited is False
    state, transitioned = register_position(
        state, itinerary,
        kremlin.model_copy(update={"measuredAt": start + timedelta(seconds=50)}),
        start + timedelta(seconds=50), zones,
    )
    assert transitioned.pointExited is True
    assert transitioned.pointReached is True
    assert state.session.phase == "VISITING"
    assert state.session.currentPointOrder == 2
    assert [visit.catalogId for visit in state.session.visits] == ["msk013", "msk005"]


def test_red_square_exit_via_unrelated_alexander_garden_uses_ordinary_confirmation():
    start = datetime(2026, 9, 16, 12, tzinfo=timezone.utc)
    itinerary = route(points=2, total_minutes=60)
    red_square = itinerary.points[0].model_copy(update={
        "catalogId": "msk001", "lat": 55.754549, "lon": 37.618666,
    })
    unrelated_next = itinerary.points[1].model_copy(update={
        "catalogId": "msk036", "lat": 55.82981, "lon": 37.63201,
    })
    itinerary = itinerary.model_copy(update={"points": [red_square, unrelated_next]})
    zones = bundled_zones("msk001", "msk013", "msk036")
    state = start_walk(itinerary, StartWalk(routeVersion=1), start)
    state, _ = register_position(
        state, itinerary, position(red_square, start), start, zones,
    )
    state, reached = register_position(
        state, itinerary,
        position(red_square, start + timedelta(seconds=10)),
        start + timedelta(seconds=10), zones,
    )
    assert reached.pointReached is True

    garden = WalkPosition(
        lat=55.750651, lon=37.612822, accuracyMeters=10,
        measuredAt=start + timedelta(seconds=20),
    )
    for expected_count, offset in enumerate((20, 30, 40), start=1):
        measured = start + timedelta(seconds=offset)
        state, pending = register_position(
            state, itinerary, garden.model_copy(update={"measuredAt": measured}),
            measured, zones,
        )
        assert pending.distanceMeters > 70
        assert pending.pointExited is False
        assert pending.exitConfirmationPending is True
        assert state.exitConfirmationCount == expected_count
        assert state.exitDirectNextPointOrder is None

    measured = start + timedelta(seconds=50)
    state, exited = register_position(
        state, itinerary, garden.model_copy(update={"measuredAt": measured}),
        measured, zones,
    )
    assert exited.pointExited is True
    assert exited.pointReached is False
    assert state.session.phase == "MOVING"
    assert state.session.currentPointOrder == 2


def test_overlapping_zones_keep_current_visit_until_user_is_outside_it():
    start = datetime(2026, 9, 16, 12, tzinfo=timezone.utc)
    itinerary = route(points=2)
    first = itinerary.points[0].model_copy(update={"catalogId": "first"})
    second = itinerary.points[1].model_copy(update={"catalogId": "second"})
    itinerary = itinerary.model_copy(update={"points": [first, second]})

    def square(center_lon):
        return {"type": "Polygon", "coordinates": [[
            [center_lon - 0.0002, first.lat - 0.0002],
            [center_lon + 0.0002, first.lat - 0.0002],
            [center_lon + 0.0002, first.lat + 0.0002],
            [center_lon - 0.0002, first.lat + 0.0002],
            [center_lon - 0.0002, first.lat - 0.0002],
        ]]}

    first_polygon = square(first.lon)
    far_polygon = square(first.lon - 0.01)
    zones = VisitZones({
        "first": VisitZone("first", {
            "type": "MultiPolygon",
            "coordinates": [first_polygon["coordinates"], far_polygon["coordinates"]],
        }),
        "second": VisitZone("second", square(first.lon + 0.0003)),
    })
    inside_first = position(first, start)
    state = start_walk(itinerary, StartWalk(routeVersion=1), start)
    state, _ = register_position(state, itinerary, inside_first, start, zones)
    state, _ = register_position(
        state, itinerary,
        inside_first.model_copy(update={"measuredAt": start + timedelta(seconds=10)}),
        start + timedelta(seconds=10), zones,
    )
    overlap = WalkPosition(
        lat=first.lat, lon=first.lon + 0.00015, accuracyMeters=10,
        measuredAt=start + timedelta(seconds=20),
    )
    state, result = register_position(state, itinerary, overlap, overlap.measuredAt, zones)
    assert result.exitConfirmationPending is False
    assert state.session.currentPointOrder == 1

    next_only = overlap.model_copy(update={"lon": first.lon + 0.00035})
    for offset in (30, 40, 50, 60):
        measured = start + timedelta(seconds=offset)
        state, result = register_position(
            state, itinerary, next_only.model_copy(update={"measuredAt": measured}),
            measured, zones,
        )
    assert result.pointExited is True
    assert result.pointReached is True
    assert state.session.currentPointOrder == 2


def test_point_fallback_exit_starts_only_beyond_ninety_five_meters():
    start = datetime(2026, 9, 16, 12, tzinfo=timezone.utc)
    itinerary = route()
    point = itinerary.points[0]
    state = start_walk(itinerary, StartWalk(routeVersion=1), start)
    state, _ = register_position(state, itinerary, position(point, start), start)
    state, _ = register_position(
        state, itinerary, position(point, start + timedelta(seconds=10)),
        start + timedelta(seconds=10),
    )
    at_threshold = WalkPosition(
        lat=point.lat + 95 / 111_195, lon=point.lon, accuracyMeters=10,
        measuredAt=start + timedelta(seconds=20),
    )
    state, at_threshold_result = register_position(
        state, itinerary, at_threshold, at_threshold.measuredAt,
    )
    assert at_threshold_result.distanceMeters == 95
    assert at_threshold_result.exitThresholdMeters == 95
    assert state.exitStartedAt is None

    beyond = at_threshold.model_copy(update={
        "lat": point.lat + 96 / 111_195,
        "measuredAt": start + timedelta(seconds=30),
    })
    state, beyond_result = register_position(state, itinerary, beyond, beyond.measuredAt)
    assert beyond_result.distanceMeters == 96
    assert state.exitStartedAt == beyond.measuredAt
    assert state.exitConfirmationCount == 1

    returned = beyond.model_copy(update={
        "lat": point.lat + 95 / 111_195,
        "measuredAt": start + timedelta(seconds=40),
    })
    state, returned_result = register_position(
        state, itinerary, returned, returned.measuredAt,
    )
    assert returned_result.pointExited is False
    assert state.exitStartedAt is None
    assert state.exitConfirmationCount == 0


def test_point_fallback_arrival_includes_seventy_five_meter_boundary():
    start = datetime(2026, 9, 16, 12, tzinfo=timezone.utc)
    itinerary = route()
    point = itinerary.points[0]
    boundary = WalkPosition(
        lat=point.lat + 75 / 111_195, lon=point.lon, accuracyMeters=10,
        measuredAt=start,
    )
    state = start_walk(itinerary, StartWalk(routeVersion=1), start)
    state, first = register_position(state, itinerary, boundary, start)
    state, second = register_position(
        state, itinerary,
        boundary.model_copy(update={"measuredAt": start + timedelta(seconds=10)}),
        start + timedelta(seconds=10),
    )
    assert first.distanceMeters == second.distanceMeters == 75
    assert second.pointReached is True


def test_poor_accuracy_cannot_advance_exit_confirmation():
    start = datetime(2026, 9, 16, 12, tzinfo=timezone.utc)
    itinerary = route()
    point = itinerary.points[0]
    state = start_walk(itinerary, StartWalk(routeVersion=1), start)
    state, _ = register_position(state, itinerary, position(point, start), start)
    state, _ = register_position(
        state, itinerary, position(point, start + timedelta(seconds=10)),
        start + timedelta(seconds=10),
    )
    outside = WalkPosition(
        lat=point.lat + 96 / 111_195, lon=point.lon, accuracyMeters=10,
        measuredAt=start + timedelta(seconds=20),
    )
    state, _ = register_position(state, itinerary, outside, outside.measuredAt)
    inaccurate = outside.model_copy(update={
        "accuracyMeters": 60,
        "measuredAt": start + timedelta(seconds=30),
    })
    state, result = register_position(
        state, itinerary, inaccurate, inaccurate.measuredAt,
    )
    assert result.pointExited is False
    assert result.exitConfirmationPending is False
    assert state.exitConfirmationCount == 0


def test_standalone_geojson_exit_distance_is_measured_from_nearest_boundary():
    start = datetime(2026, 9, 16, 12, tzinfo=timezone.utc)
    itinerary = route()
    point = itinerary.points[0].model_copy(update={"catalogId": "msk-root"})
    itinerary = itinerary.model_copy(update={
        "points": [point, itinerary.points[1]],
    })
    ring = [[
        [point.lon - 0.0002, point.lat - 0.0002],
        [point.lon + 0.0002, point.lat - 0.0002],
        [point.lon + 0.0002, point.lat + 0.0002],
        [point.lon - 0.0002, point.lat + 0.0002],
        [point.lon - 0.0002, point.lat - 0.0002],
    ]]
    zones = VisitZones({
        "msk-root": VisitZone(
            catalog_id="msk-root",
            geometry={"type": "Polygon", "coordinates": ring},
        ),
    })
    state = start_walk(itinerary, StartWalk(routeVersion=1), start)
    state, _ = register_position(
        state, itinerary, position(point, start), start, zones,
    )
    state, reached = register_position(
        state, itinerary, position(point, start + timedelta(seconds=10)),
        start + timedelta(seconds=10), zones,
    )
    assert reached.pointReached is True

    outside = WalkPosition(
        lat=point.lat + 0.0002 + 71 / 111_195,
        lon=point.lon, accuracyMeters=10,
        measuredAt=start + timedelta(seconds=20),
    )
    state, result = register_position(
        state, itinerary, outside, outside.measuredAt, zones,
    )
    assert result.distanceMeters == 71
    assert result.exitThresholdMeters == 70
    assert state.exitConfirmationCount == 1


def test_group_visit_pause_resume_and_stop_keep_single_parent_timer():
    start = datetime(2026, 9, 16, 12, tzinfo=timezone.utc)
    itinerary = grouped_route()
    point = itinerary.points[0]
    state = start_walk(itinerary, StartWalk(routeVersion=1), start)
    state, _ = register_position(state, itinerary, position(point, start), start)
    state, _ = register_position(
        state, itinerary, position(point, start + timedelta(seconds=10)),
        start + timedelta(seconds=10),
    )
    state = apply_action(
        state, itinerary, WalkAction(action="PAUSE"), start + timedelta(seconds=20),
    )
    state = apply_action(
        state, itinerary, WalkAction(action="RESUME"), start + timedelta(seconds=50),
    )
    stopped = apply_action(
        state, itinerary, WalkAction(action="STOP"), start + timedelta(seconds=60),
    )
    assert stopped.session.status == "STOPPED"
    assert len(stopped.session.visits) == 1
    assert stopped.session.visits[0].catalogId == "msk-parent"
    assert stopped.session.visits[0].durationSeconds == 20


def test_two_accurate_measurements_ten_seconds_apart_reach_point():
    start = datetime(2026, 9, 16, 12, tzinfo=timezone.utc)
    itinerary = route()
    state = start_walk(itinerary, StartWalk(routeVersion=1), start)
    state, first = register_position(
        state, itinerary, position(itinerary.points[0], start + timedelta(minutes=10)),
        start + timedelta(minutes=10),
    )
    assert first.pointReached is False
    state, early = register_position(
        state, itinerary,
        position(itinerary.points[0], start + timedelta(minutes=10, seconds=9)),
        start + timedelta(minutes=10, seconds=9),
    )
    assert early.pointReached is False
    state, second = register_position(
        state, itinerary,
        position(itinerary.points[0], start + timedelta(minutes=10, seconds=10)),
        start + timedelta(minutes=10, seconds=10),
    )
    assert second.pointReached is True
    assert state.session.currentPointOrder == 1
    assert state.session.phase == "VISITING"
    assert state.session.visitStartedAt == start + timedelta(minutes=10, seconds=10)
    assert state.lastPosition is not None
    assert state.lastPosition.lat == itinerary.points[0].lat
    assert state.lastPosition.accuracyMeters == 10
    assert state.session.visitElapsedSeconds == 0
    assert state.session.visits[0].pointOrder == 1
    assert state.session.estimatedRemainingMinutes == 110


def test_visit_stays_until_initial_exit_and_three_ten_second_confirmations():
    start = datetime(2026, 9, 16, 12, tzinfo=timezone.utc)
    itinerary = route()
    point = itinerary.points[0]
    state = start_walk(itinerary, StartWalk(routeVersion=1), start)
    state, _ = register_position(state, itinerary, position(point, start), start)
    state, _ = register_position(
        state, itinerary, position(point, start + timedelta(seconds=10)),
        start + timedelta(seconds=10),
    )
    outside = WalkPosition(
        lat=point.lat + 0.002, lon=point.lon, accuracyMeters=10,
        measuredAt=start + timedelta(minutes=3),
    )
    state, first_exit = register_position(state, itinerary, outside, outside.measuredAt)
    assert first_exit.pointExited is False
    assert state.session.phase == "VISITING"
    assert state.session.currentPointOrder == 1
    for seconds in (10, 20):
        state, pending = register_position(
            state, itinerary,
            outside.model_copy(update={
                "measuredAt": outside.measuredAt + timedelta(seconds=seconds),
            }),
            outside.measuredAt + timedelta(seconds=seconds),
        )
        assert pending.pointExited is False
    state, confirmed_exit = register_position(
        state, itinerary,
        outside.model_copy(update={
            "measuredAt": outside.measuredAt + timedelta(seconds=30),
        }),
        outside.measuredAt + timedelta(seconds=30),
    )
    assert confirmed_exit.pointExited is True
    assert state.session.phase == "MOVING"
    assert state.session.currentPointOrder == 2
    assert state.session.visits[0].durationSeconds == 200
    assert state.session.visits[0].leftAt == outside.measuredAt + timedelta(seconds=30)


def test_one_outside_jump_is_cancelled_by_next_inside_measurement():
    start = datetime(2026, 9, 16, 12, tzinfo=timezone.utc)
    itinerary = route()
    point = itinerary.points[0]
    state = start_walk(itinerary, StartWalk(routeVersion=1), start)
    state, _ = register_position(state, itinerary, position(point, start), start)
    state, _ = register_position(
        state, itinerary, position(point, start + timedelta(seconds=10)),
        start + timedelta(seconds=10),
    )
    jump = WalkPosition(lat=point.lat + 0.002, lon=point.lon, accuracyMeters=10,
                        measuredAt=start + timedelta(seconds=20))
    state, _ = register_position(state, itinerary, jump, jump.measuredAt)
    state, result = register_position(
        state, itinerary, position(point, start + timedelta(seconds=30)),
        start + timedelta(seconds=30),
    )
    assert result.pointExited is False
    assert state.exitStartedAt is None
    assert state.exitConfirmationCount == 0
    assert state.session.phase == "VISITING"


def test_one_measurement_at_exact_point_does_not_confirm_arrival():
    start = datetime(2026, 9, 16, 12, tzinfo=timezone.utc)
    itinerary = route()
    state = start_walk(itinerary, StartWalk(routeVersion=1), start)
    state, progress = register_position(
        state, itinerary, position(itinerary.points[0], start + timedelta(seconds=10)),
        start + timedelta(seconds=10),
    )
    assert progress.distanceMeters == 0
    assert progress.pointReached is False
    assert state.session.currentPointOrder == 1


def test_duplicate_measurement_timestamp_is_not_a_second_confirmation():
    start = datetime(2026, 9, 16, 12, tzinfo=timezone.utc)
    itinerary = route()
    measured = start + timedelta(seconds=5)
    state = start_walk(itinerary, StartWalk(routeVersion=1), start)
    state, _ = register_position(state, itinerary, position(itinerary.points[0], measured), measured)
    state, duplicate = register_position(
        state, itinerary, position(itinerary.points[0], measured), measured + timedelta(seconds=5),
    )
    assert duplicate.pointReached is False
    assert state.session.currentPointOrder == 1


def test_position_outside_arrival_radius_does_not_confirm():
    start = datetime(2026, 9, 16, 12, tzinfo=timezone.utc)
    itinerary = route()
    point = itinerary.points[0]
    far = WalkPosition(lat=point.lat + 0.001, lon=point.lon, accuracyMeters=10,
                       measuredAt=start + timedelta(seconds=5))
    state = start_walk(itinerary, StartWalk(routeVersion=1), start)
    state, first = register_position(state, itinerary, far, far.measuredAt)
    far_second = far.model_copy(update={"measuredAt": start + timedelta(seconds=10)})
    state, second = register_position(state, itinerary, far_second, far_second.measuredAt)
    assert first.distanceMeters > 75
    assert second.pointReached is False
    assert state.session.currentPointOrder == 1


def test_position_measured_before_walk_is_rejected_as_stale():
    start = datetime(2026, 9, 16, 12, tzinfo=timezone.utc)
    itinerary = route()
    state = start_walk(itinerary, StartWalk(routeVersion=1), start)
    stale = position(itinerary.points[0], start - timedelta(minutes=1))
    with pytest.raises(WalkInvalidPosition):
        register_position(state, itinerary, stale, start)


def test_paused_walk_does_not_accept_arrival_measurements():
    start = datetime(2026, 9, 16, 12, tzinfo=timezone.utc)
    itinerary = route()
    state = start_walk(itinerary, StartWalk(routeVersion=1), start)
    state = apply_action(state, itinerary, WalkAction(action="PAUSE"),
                         start + timedelta(seconds=1))
    with pytest.raises(WalkInvalidState):
        register_position(
            state, itinerary, position(itinerary.points[0], start + timedelta(seconds=5)),
            start + timedelta(seconds=5),
        )


def test_poor_accuracy_breaks_arrival_confirmation_sequence():
    start = datetime(2026, 9, 16, 12, tzinfo=timezone.utc)
    itinerary = route()
    state = start_walk(itinerary, StartWalk(routeVersion=1), start)
    state, _ = register_position(
        state, itinerary, position(itinerary.points[0], start + timedelta(seconds=10)),
        start + timedelta(seconds=10),
    )
    state, _ = register_position(
        state, itinerary,
        position(itinerary.points[0], start + timedelta(seconds=11), accuracy=70),
        start + timedelta(seconds=11),
    )
    state, result = register_position(
        state, itinerary, position(itinerary.points[0], start + timedelta(seconds=17)),
        start + timedelta(seconds=17),
    )
    assert result.pointReached is False
    assert state.session.currentPointOrder == 1


def test_last_point_completes_only_after_confirmed_exit_without_time_limit():
    start = datetime(2026, 9, 16, 12, tzinfo=timezone.utc)
    itinerary = route(points=1, total_minutes=50)
    state = start_walk(itinerary, StartWalk(routeVersion=1), start)
    state, _ = register_position(state, itinerary, position(itinerary.points[0], start), start)
    state, reached = register_position(
        state, itinerary, position(itinerary.points[0], start + timedelta(seconds=10)),
        start + timedelta(seconds=10),
    )
    assert reached.pointReached is True
    assert state.session.status == "ACTIVE"
    assert state.session.currentPointOrder == 1
    assert state.session.phase == "VISITING"
    inside_state, inside = register_position(
        state, itinerary, position(itinerary.points[0], start + timedelta(hours=3)),
        start + timedelta(hours=3),
    )
    assert inside.pointExited is False
    assert inside_state.session.status == "ACTIVE"
    assert inside_state.session.visitElapsedSeconds == 3 * 60 * 60 - 10
    point = itinerary.points[0]
    outside = WalkPosition(lat=point.lat + 0.002, lon=point.lon, accuracyMeters=10,
                           measuredAt=start + timedelta(hours=3, seconds=5))
    outside_state, first_exit = register_position(
        inside_state, itinerary, outside, outside.measuredAt,
    )
    assert first_exit.pointExited is False
    for seconds in (10, 20):
        outside_state, pending = register_position(
            outside_state, itinerary,
            outside.model_copy(update={
                "measuredAt": outside.measuredAt + timedelta(seconds=seconds),
            }),
            outside.measuredAt + timedelta(seconds=seconds),
        )
        assert pending.pointExited is False
    completed_state, completed = register_position(
        outside_state, itinerary,
        outside.model_copy(update={
            "measuredAt": outside.measuredAt + timedelta(seconds=30),
        }),
        outside.measuredAt + timedelta(seconds=30),
    )
    assert completed.pointExited is True
    assert completed_state.session.status == "COMPLETED"
    assert completed_state.session.currentPointOrder is None
    assert len(completed_state.session.visits) == 1
    assert completed_state.session.visits[0].durationSeconds == 3 * 60 * 60 + 25


def test_pause_stops_visit_stopwatch_and_resume_continues_it():
    start = datetime(2026, 9, 16, 12, tzinfo=timezone.utc)
    itinerary = route(points=1, total_minutes=50)
    state = start_walk(itinerary, StartWalk(routeVersion=1), start)
    state, _ = register_position(state, itinerary, position(itinerary.points[0], start), start)
    state, _ = register_position(
        state, itinerary, position(itinerary.points[0], start + timedelta(seconds=10)),
        start + timedelta(seconds=10),
    )
    state = apply_action(state, itinerary, WalkAction(action="PAUSE"),
                         start + timedelta(minutes=20))
    state = apply_action(state, itinerary, WalkAction(action="RESUME"),
                         start + timedelta(minutes=50))
    assert state.session.visitElapsedSeconds == 20 * 60 - 10
    current = session_at(state, start + timedelta(hours=1, seconds=5))
    assert current.status == "ACTIVE"
    assert current.visitElapsedSeconds == 30 * 60 - 5


def test_legacy_final_visit_json_restores_as_unlimited_visiting_stopwatch():
    start = datetime(2026, 9, 16, 12, tzinfo=timezone.utc)
    itinerary = route(points=1)
    original = start_walk(itinerary, StartWalk(routeVersion=1), start)
    legacy_payload = original.model_copy(update={
        "session": original.session.model_copy(update={
            "finalPointVisitStartedAt": start + timedelta(minutes=1),
        }),
        "finalPointPausedSeconds": 10,
    }).model_dump(mode="json")
    for field in ("phase", "visitStartedAt", "visitElapsedSeconds"):
        legacy_payload["session"].pop(field)
    for field in (
        "visitPausedSeconds", "exitStartedAt", "exitPointOrder",
        "exitLastConfirmedAt", "exitConfirmationCount", "exitDirectNextPointOrder",
    ):
        legacy_payload.pop(field)
    restored = WalkState.model_validate_json(json.dumps(legacy_payload))
    current = session_at(restored, start + timedelta(minutes=3))
    assert current.phase == "VISITING"
    assert current.currentPointOrder == 1
    assert current.visitElapsedSeconds == 110


def test_pause_time_is_excluded_from_remaining_time():
    start = datetime(2026, 9, 16, 12, tzinfo=timezone.utc)
    itinerary = route()
    state = start_walk(itinerary, StartWalk(routeVersion=1), start)
    state = apply_action(state, itinerary, WalkAction(action="PAUSE"),
                         start + timedelta(minutes=10))
    state = apply_action(state, itinerary, WalkAction(action="RESUME"),
                         start + timedelta(minutes=30))
    state, progress = register_position(
        state, itinerary,
        WalkPosition(lat=54.0, lon=37.0, accuracyMeters=10,
                     measuredAt=start + timedelta(minutes=40)),
        start + timedelta(minutes=40),
    )
    assert progress.walk.estimatedRemainingMinutes == 100
    stopped = apply_action(state, itinerary, WalkAction(action="STOP"),
                           start + timedelta(minutes=45))
    assert stopped.session.status == "STOPPED"

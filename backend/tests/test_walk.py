import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from gulyay.models import (Filters, Route, RouteLeg, RoutePoint, SearchArea,
                           StartWalk, WalkAction, WalkPosition, WalkState)
from gulyay.walk import (WalkInvalidPosition, WalkInvalidState, apply_action,
                         register_position, session_at, start_walk)


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


def test_two_accurate_measurements_five_seconds_apart_reach_point():
    start = datetime(2026, 9, 16, 12, tzinfo=timezone.utc)
    itinerary = route()
    state = start_walk(itinerary, StartWalk(routeVersion=1), start)
    state, first = register_position(
        state, itinerary, position(itinerary.points[0], start + timedelta(minutes=10)),
        start + timedelta(minutes=10),
    )
    assert first.pointReached is False
    state, second = register_position(
        state, itinerary,
        position(itinerary.points[0], start + timedelta(minutes=10, seconds=5)),
        start + timedelta(minutes=10, seconds=5),
    )
    assert second.pointReached is True
    assert state.session.currentPointOrder == 1
    assert state.session.phase == "VISITING"
    assert state.session.visitStartedAt == start + timedelta(minutes=10, seconds=5)
    assert state.session.visitElapsedSeconds == 0
    assert state.session.visits[0].pointOrder == 1
    assert state.session.estimatedRemainingMinutes == 110


def test_visit_stays_on_current_point_until_two_confirmed_exit_measurements():
    start = datetime(2026, 9, 16, 12, tzinfo=timezone.utc)
    itinerary = route()
    point = itinerary.points[0]
    state = start_walk(itinerary, StartWalk(routeVersion=1), start)
    state, _ = register_position(state, itinerary, position(point, start), start)
    state, _ = register_position(
        state, itinerary, position(point, start + timedelta(seconds=5)),
        start + timedelta(seconds=5),
    )
    outside = WalkPosition(
        lat=point.lat + 0.002, lon=point.lon, accuracyMeters=10,
        measuredAt=start + timedelta(minutes=3),
    )
    state, first_exit = register_position(state, itinerary, outside, outside.measuredAt)
    assert first_exit.pointExited is False
    assert state.session.phase == "VISITING"
    assert state.session.currentPointOrder == 1
    state, second_exit = register_position(
        state, itinerary,
        outside.model_copy(update={"measuredAt": outside.measuredAt + timedelta(seconds=5)}),
        outside.measuredAt + timedelta(seconds=5),
    )
    assert second_exit.pointExited is True
    assert state.session.phase == "MOVING"
    assert state.session.currentPointOrder == 2
    assert state.session.visits[0].durationSeconds == 180
    assert state.session.visits[0].leftAt == outside.measuredAt + timedelta(seconds=5)


def test_one_outside_jump_is_cancelled_by_next_inside_measurement():
    start = datetime(2026, 9, 16, 12, tzinfo=timezone.utc)
    itinerary = route()
    point = itinerary.points[0]
    state = start_walk(itinerary, StartWalk(routeVersion=1), start)
    state, _ = register_position(state, itinerary, position(point, start), start)
    state, _ = register_position(
        state, itinerary, position(point, start + timedelta(seconds=5)),
        start + timedelta(seconds=5),
    )
    jump = WalkPosition(lat=point.lat + 0.002, lon=point.lon, accuracyMeters=10,
                        measuredAt=start + timedelta(seconds=10))
    state, _ = register_position(state, itinerary, jump, jump.measuredAt)
    state, result = register_position(
        state, itinerary, position(point, start + timedelta(seconds=15)),
        start + timedelta(seconds=15),
    )
    assert result.pointExited is False
    assert state.exitStartedAt is None
    assert state.session.phase == "VISITING"


def test_one_measurement_at_exact_point_does_not_confirm_arrival():
    start = datetime(2026, 9, 16, 12, tzinfo=timezone.utc)
    itinerary = route()
    state = start_walk(itinerary, StartWalk(routeVersion=1), start)
    state, progress = register_position(
        state, itinerary, position(itinerary.points[0], start + timedelta(seconds=5)),
        start + timedelta(seconds=5),
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
        state, itinerary, position(itinerary.points[0], start + timedelta(seconds=5)),
        start + timedelta(seconds=5),
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
        state, itinerary, position(itinerary.points[0], start + timedelta(seconds=5)),
        start + timedelta(seconds=5),
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
    assert inside_state.session.visitElapsedSeconds == 3 * 60 * 60 - 5
    point = itinerary.points[0]
    outside = WalkPosition(lat=point.lat + 0.002, lon=point.lon, accuracyMeters=10,
                           measuredAt=start + timedelta(hours=3, seconds=5))
    outside_state, first_exit = register_position(
        inside_state, itinerary, outside, outside.measuredAt,
    )
    assert first_exit.pointExited is False
    completed_state, completed = register_position(
        outside_state, itinerary,
        outside.model_copy(update={"measuredAt": outside.measuredAt + timedelta(seconds=5)}),
        outside.measuredAt + timedelta(seconds=5),
    )
    assert completed.pointExited is True
    assert completed_state.session.status == "COMPLETED"
    assert completed_state.session.currentPointOrder is None
    assert len(completed_state.session.visits) == 1
    assert completed_state.session.visits[0].durationSeconds == 3 * 60 * 60 + 5


def test_pause_stops_visit_stopwatch_and_resume_continues_it():
    start = datetime(2026, 9, 16, 12, tzinfo=timezone.utc)
    itinerary = route(points=1, total_minutes=50)
    state = start_walk(itinerary, StartWalk(routeVersion=1), start)
    state, _ = register_position(state, itinerary, position(itinerary.points[0], start), start)
    state, _ = register_position(
        state, itinerary, position(itinerary.points[0], start + timedelta(seconds=5)),
        start + timedelta(seconds=5),
    )
    state = apply_action(state, itinerary, WalkAction(action="PAUSE"),
                         start + timedelta(minutes=20))
    state = apply_action(state, itinerary, WalkAction(action="RESUME"),
                         start + timedelta(minutes=50))
    assert state.session.visitElapsedSeconds == 20 * 60 - 5
    current = session_at(state, start + timedelta(hours=1, seconds=5))
    assert current.status == "ACTIVE"
    assert current.visitElapsedSeconds == 30 * 60


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
    for field in ("visitPausedSeconds", "exitStartedAt", "exitPointOrder"):
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

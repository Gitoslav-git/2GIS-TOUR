from datetime import datetime, timedelta, timezone
from uuid import uuid4

from gulyay.models import (Filters, Route, RouteLeg, RoutePoint, SearchArea,
                           StartWalk, WalkAction, WalkPosition)
from gulyay.walk import (WalkInvalidState, apply_action, register_position,
                         start_walk)


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
    assert state.session.currentPointOrder == 2
    assert state.session.visits[0].pointOrder == 1
    assert state.session.estimatedRemainingMinutes == 110


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


def test_last_point_starts_one_hour_visit_before_completion():
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
    assert state.session.finalPointVisitStartedAt == start + timedelta(seconds=5)
    assert state.session.estimatedRemainingMinutes == 60
    waiting_state, waiting = register_position(
        state, itinerary, position(itinerary.points[0], start + timedelta(minutes=30)),
        start + timedelta(minutes=30),
    )
    assert waiting.pointReached is False
    assert waiting_state.session.status == "ACTIVE"
    assert waiting_state.session.estimatedRemainingMinutes == 31
    completed_state, completed = register_position(
        waiting_state, itinerary, position(itinerary.points[0], start + timedelta(hours=1, seconds=5)),
        start + timedelta(hours=1, seconds=5),
    )
    assert completed.pointReached is False
    assert completed_state.session.status == "COMPLETED"
    assert completed_state.session.currentPointOrder is None
    assert len(completed_state.session.visits) == 1


def test_pause_does_not_consume_final_point_visit_time():
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
    state, progress = register_position(
        state, itinerary, position(itinerary.points[0], start + timedelta(hours=1, seconds=5)),
        start + timedelta(hours=1, seconds=5),
    )
    assert progress.walk.status == "ACTIVE"
    assert progress.walk.estimatedRemainingMinutes == 30


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

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from .models import (Route, StartWalk, Visit, WalkAction, WalkPosition,
                     WalkProgress, WalkSession, WalkState)

ARRIVAL_RADIUS_METERS = 75
EXIT_RADIUS_METERS = 115
MAX_ACCURACY_METERS = 50
CONFIRMATION_INTERVAL_SECONDS = 5


class WalkInvalidState(Exception):
    pass


class WalkInvalidPosition(Exception):
    pass


def start_walk(route: Route, payload: StartWalk,
               now: datetime | None = None) -> WalkState:
    if payload.routeVersion != route.routeVersion or not route.points:
        raise WalkInvalidState()
    started = _utc(now)
    session = WalkSession(
        walkId=uuid4(), routeId=route.routeId, routeVersion=route.routeVersion,
        status="ACTIVE", currentPointOrder=1, startedAt=started,
        estimatedRemainingMinutes=route.totalMinutes, visits=[],
    )
    return WalkState(session=session)


def register_position(state: WalkState, route: Route, position: WalkPosition,
                      now: datetime | None = None) -> tuple[WalkState, WalkProgress]:
    state = _normalize_legacy_visit(state)
    session = state.session
    measured = position.measuredAt.astimezone(timezone.utc)
    if state.lastMeasuredAt is not None and measured <= state.lastMeasuredAt:
        return state, WalkProgress(walk=session, pointReached=False)
    if session.status != "ACTIVE" or session.currentPointOrder is None:
        raise WalkInvalidState()
    current_time = _utc(now)
    if measured < session.startedAt.astimezone(timezone.utc) - timedelta(seconds=5):
        raise WalkInvalidPosition()
    if measured > current_time + timedelta(minutes=5):
        raise WalkInvalidPosition()
    point = route.points[session.currentPointOrder - 1]
    distance = round(_distance_meters(position.lat, position.lon, point.lat, point.lon))
    if session.phase == "VISITING":
        return _register_visit_position(state, route, measured, position, distance)
    reached = False
    session = session.model_copy(update={
        "estimatedRemainingMinutes": _remaining_minutes(
            route, session.startedAt, measured, state.pausedSeconds,
        ),
    })
    update: dict = {
        "lastMeasuredAt": measured,
        "lastPosition": position.model_copy(update={"measuredAt": measured}),
        "session": session,
    }
    accurate_and_near = (
        position.accuracyMeters <= MAX_ACCURACY_METERS
        and distance <= ARRIVAL_RADIUS_METERS
    )
    if not accurate_and_near:
        update.update({"proximityStartedAt": None, "proximityPointOrder": None})
    elif (state.proximityPointOrder != session.currentPointOrder
          or state.proximityStartedAt is None):
        update.update({
            "proximityStartedAt": measured,
            "proximityPointOrder": session.currentPointOrder,
        })
    elif (measured - state.proximityStartedAt).total_seconds() >= CONFIRMATION_INTERVAL_SECONDS:
        reached = True
        visits = [*session.visits, Visit(
            pointOrder=session.currentPointOrder, reachedAt=measured,
        )]
        session = session.model_copy(update={
            "phase": "VISITING", "visits": visits,
            "visitStartedAt": measured, "visitElapsedSeconds": 0,
            "finalPointVisitStartedAt": None,
        })
        update.update({
            "session": session, "proximityStartedAt": None,
            "proximityPointOrder": None, "exitStartedAt": None,
            "exitPointOrder": None, "visitPausedSeconds": 0,
            "finalPointPausedSeconds": 0,
        })
    updated = state.model_copy(update=update)
    return updated, WalkProgress(
        walk=updated.session, pointReached=reached, distanceMeters=distance,
    )


def apply_action(state: WalkState, route: Route, payload: WalkAction,
                 now: datetime | None = None) -> WalkState:
    state = _normalize_legacy_visit(state)
    moment = _utc(now)
    session = state.session
    if payload.action == "PAUSE":
        if session.status != "ACTIVE":
            raise WalkInvalidState()
        session = _session_with_visit_elapsed(state, moment)
        return state.model_copy(update={
            "session": session.model_copy(update={"status": "PAUSED"}),
            "pausedAt": moment, "proximityStartedAt": None,
            "proximityPointOrder": None,
        })
    if payload.action == "RESUME":
        if session.status != "PAUSED" or state.pausedAt is None:
            raise WalkInvalidState()
        paused_seconds = state.pausedSeconds + max(
            0, round((moment - state.pausedAt).total_seconds()),
        )
        visit_paused_seconds = state.visitPausedSeconds
        if session.phase == "VISITING":
            visit_paused_seconds += max(
                0, round((moment - state.pausedAt).total_seconds()),
            )
        session = _session_with_visit_elapsed(state, moment)
        return state.model_copy(update={
            "session": session.model_copy(update={
                "status": "ACTIVE",
                "estimatedRemainingMinutes": _remaining_minutes(
                    route, session.startedAt, moment, paused_seconds,
                ),
            }),
            "pausedAt": None, "pausedSeconds": paused_seconds,
            "visitPausedSeconds": visit_paused_seconds,
            "finalPointPausedSeconds": 0,
            "proximityStartedAt": None, "proximityPointOrder": None,
            "exitStartedAt": None, "exitPointOrder": None,
        })
    if payload.action == "STOP":
        if session.status not in {"ACTIVE", "PAUSED"}:
            raise WalkInvalidState()
        session = _session_with_visit_elapsed(state, moment)
        paused_seconds = state.pausedSeconds
        if session.status == "PAUSED" and state.pausedAt is not None:
            paused_seconds += max(0, round((moment - state.pausedAt).total_seconds()))
        visits = list(session.visits)
        if session.phase == "VISITING" and visits:
            visits[-1] = visits[-1].model_copy(update={
                "leftAt": moment,
                "durationSeconds": session.visitElapsedSeconds,
            })
        return state.model_copy(update={
            "session": session.model_copy(update={
                "status": "STOPPED", "endedAt": moment,
                "phase": "MOVING", "visits": visits,
                "visitStartedAt": None, "visitElapsedSeconds": 0,
                "finalPointVisitStartedAt": None,
                "estimatedRemainingMinutes": _remaining_minutes(
                    route, session.startedAt, moment, paused_seconds,
                ),
            }),
            "pausedAt": None, "pausedSeconds": paused_seconds,
            "proximityStartedAt": None, "proximityPointOrder": None,
            "exitStartedAt": None, "exitPointOrder": None,
            "visitPausedSeconds": 0, "finalPointPausedSeconds": 0,
        })
    raise WalkInvalidState()


def session_at(state: WalkState, now: datetime | None = None) -> WalkSession:
    """Return a response snapshot with an authoritative live visit stopwatch."""
    normalized = _normalize_legacy_visit(state)
    return _session_with_visit_elapsed(normalized, _utc(now))


def _register_visit_position(state: WalkState, route: Route, measured: datetime,
                             position: WalkPosition,
                             distance: int) -> tuple[WalkState, WalkProgress]:
    session = _session_with_visit_elapsed(state, measured)
    update: dict = {
        "lastMeasuredAt": measured,
        "lastPosition": position.model_copy(update={"measuredAt": measured}),
        "session": session,
    }
    accurate_and_outside = (
        position.accuracyMeters <= MAX_ACCURACY_METERS
        and distance > EXIT_RADIUS_METERS
    )
    exited = False
    if not accurate_and_outside:
        update.update({"exitStartedAt": None, "exitPointOrder": None})
    elif (state.exitPointOrder != session.currentPointOrder
          or state.exitStartedAt is None):
        update.update({
            "exitStartedAt": measured,
            "exitPointOrder": session.currentPointOrder,
        })
    elif (measured - state.exitStartedAt).total_seconds() >= CONFIRMATION_INTERVAL_SECONDS:
        exited = True
        visits = list(session.visits)
        duration = session.visitElapsedSeconds
        if visits and visits[-1].pointOrder == session.currentPointOrder:
            visits[-1] = visits[-1].model_copy(update={
                "leftAt": measured, "durationSeconds": duration,
            })
        common = {
            "phase": "MOVING", "visits": visits, "visitStartedAt": None,
            "visitElapsedSeconds": 0, "finalPointVisitStartedAt": None,
        }
        if session.currentPointOrder >= len(route.points):
            session = session.model_copy(update={
                **common, "status": "COMPLETED", "currentPointOrder": None,
                "endedAt": measured, "estimatedRemainingMinutes": 0,
            })
        else:
            session = session.model_copy(update={
                **common, "currentPointOrder": session.currentPointOrder + 1,
                "estimatedRemainingMinutes": _remaining_minutes(
                    route, session.startedAt, measured, state.pausedSeconds,
                ),
            })
        update.update({
            "session": session, "exitStartedAt": None, "exitPointOrder": None,
            "proximityStartedAt": None, "proximityPointOrder": None,
            "visitPausedSeconds": 0, "finalPointPausedSeconds": 0,
        })
    updated = state.model_copy(update=update)
    return updated, WalkProgress(
        walk=updated.session, pointReached=False, pointExited=exited,
        distanceMeters=distance,
    )


def _remaining_minutes(route: Route, started_at: datetime, current: datetime,
                       paused_seconds: int) -> int:
    elapsed = max(0, (current - started_at.astimezone(timezone.utc)).total_seconds()
                  - paused_seconds)
    return max(0, math.ceil(route.totalMinutes - elapsed / 60))


def _session_with_visit_elapsed(state: WalkState, current: datetime) -> WalkSession:
    session = state.session
    if session.phase != "VISITING" or session.visitStartedAt is None:
        return session
    paused = state.visitPausedSeconds
    if session.status == "PAUSED" and state.pausedAt is not None:
        paused += max(0, round((current - state.pausedAt).total_seconds()))
    elapsed = max(0, round(
        (current - session.visitStartedAt.astimezone(timezone.utc)).total_seconds() - paused,
    ))
    return session.model_copy(update={"visitElapsedSeconds": elapsed})


def _normalize_legacy_visit(state: WalkState) -> WalkState:
    session = state.session
    if (session.phase == "MOVING" and session.currentPointOrder is not None
            and session.finalPointVisitStartedAt is not None):
        session = session.model_copy(update={
            "phase": "VISITING",
            "visitStartedAt": session.finalPointVisitStartedAt,
            "visitElapsedSeconds": 0,
            "finalPointVisitStartedAt": None,
        })
        return state.model_copy(update={
            "session": session,
            "visitPausedSeconds": max(
                state.visitPausedSeconds, state.finalPointPausedSeconds,
            ),
            "finalPointPausedSeconds": 0,
        })
    return state


def _distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_000.0
    first, second = math.radians(lat1), math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    haversine = (math.sin(delta_lat / 2) ** 2
                 + math.cos(first) * math.cos(second) * math.sin(delta_lon / 2) ** 2)
    return radius * 2 * math.atan2(math.sqrt(haversine), math.sqrt(1 - haversine))


def _utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

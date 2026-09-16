from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from .models import (Route, StartWalk, Visit, WalkAction, WalkPosition,
                     WalkProgress, WalkSession, WalkState)

ARRIVAL_RADIUS_METERS = 75
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
    reached = False
    session = session.model_copy(update={
        "estimatedRemainingMinutes": _remaining_minutes(
            route, session.startedAt, measured, state.pausedSeconds,
        ),
    })
    update: dict = {"lastMeasuredAt": measured, "session": session}
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
        if session.currentPointOrder >= len(route.points):
            session = session.model_copy(update={
                "status": "COMPLETED", "currentPointOrder": None,
                "endedAt": measured, "visits": visits,
                "estimatedRemainingMinutes": 0,
            })
        else:
            session = session.model_copy(update={
                "currentPointOrder": session.currentPointOrder + 1,
                "visits": visits,
                "estimatedRemainingMinutes": _remaining_minutes(
                    route, session.startedAt, measured, state.pausedSeconds,
                ),
            })
        update.update({
            "session": session, "proximityStartedAt": None,
            "proximityPointOrder": None,
        })
    updated = state.model_copy(update=update)
    return updated, WalkProgress(
        walk=updated.session, pointReached=reached, distanceMeters=distance,
    )


def apply_action(state: WalkState, route: Route, payload: WalkAction,
                 now: datetime | None = None) -> WalkState:
    moment = _utc(now)
    session = state.session
    if payload.action == "PAUSE":
        if session.status != "ACTIVE":
            raise WalkInvalidState()
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
        return state.model_copy(update={
            "session": session.model_copy(update={
                "status": "ACTIVE",
                "estimatedRemainingMinutes": _remaining_minutes(
                    route, session.startedAt, moment, paused_seconds,
                ),
            }),
            "pausedAt": None, "pausedSeconds": paused_seconds,
            "proximityStartedAt": None, "proximityPointOrder": None,
        })
    if payload.action == "STOP":
        if session.status not in {"ACTIVE", "PAUSED"}:
            raise WalkInvalidState()
        paused_seconds = state.pausedSeconds
        if session.status == "PAUSED" and state.pausedAt is not None:
            paused_seconds += max(0, round((moment - state.pausedAt).total_seconds()))
        return state.model_copy(update={
            "session": session.model_copy(update={
                "status": "STOPPED", "endedAt": moment,
                "estimatedRemainingMinutes": _remaining_minutes(
                    route, session.startedAt, moment, paused_seconds,
                ),
            }),
            "pausedAt": None, "pausedSeconds": paused_seconds,
            "proximityStartedAt": None, "proximityPointOrder": None,
        })
    raise WalkInvalidState()


def _remaining_minutes(route: Route, started_at: datetime, current: datetime,
                       paused_seconds: int) -> int:
    elapsed = max(0, (current - started_at.astimezone(timezone.utc)).total_seconds()
                  - paused_seconds)
    return max(0, math.ceil(route.totalMinutes - elapsed / 60))


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

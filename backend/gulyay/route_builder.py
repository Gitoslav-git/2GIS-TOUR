from __future__ import annotations

import math
from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from .geo import GeoProvider, GeoRouteNotFound
from .models import CreateRoute, PlaceCandidate, QueryPreview, Route, RoutePoint


class RouteNotFound(Exception):
    pass


class TimeBudgetExceeded(Exception):
    def __init__(self, minimum_minutes: int | None = None):
        self.minimum_minutes = minimum_minutes


def build_route(payload: CreateRoute, preview: QueryPreview, geo: GeoProvider,
                now: datetime | None = None) -> Route:
    city_center = geo.resolve_city_center(payload.cityId)
    if payload.startLocation:
        start = (payload.startLocation.lat, payload.startLocation.lon)
        approximate_start = False
    else:
        start = city_center
        approximate_start = True

    candidates = geo.search_places(payload.cityId, preview, city_center)
    if not candidates:
        raise RouteNotFound()
    candidates = _candidate_order(candidates, preview.includeFood)
    current, elapsed_seconds = start, 0
    route_points, legs = [], []
    skipped_for_budget = False
    local_now = now or datetime.now(ZoneInfo("Europe/Moscow"))

    for candidate in candidates[:12]:
        if len(route_points) >= 8:
            break
        visit_minutes = 60 if candidate.isFood else 40
        try:
            leg = geo.walking_leg(current, (candidate.lat, candidate.lon),
                                  len(route_points), len(route_points) + 1)
        except GeoRouteNotFound:
            continue
        projected_seconds = elapsed_seconds + leg.durationSeconds + visit_minutes * 60
        if math.ceil(projected_seconds / 60) > preview.durationMinutes:
            skipped_for_budget = True
            continue
        arrival = local_now + timedelta(seconds=elapsed_seconds + leg.durationSeconds)
        schedule_status = schedule_status_at(candidate.schedule, arrival, visit_minutes)
        if schedule_status == "CLOSED":
            continue
        route_points.append(RoutePoint(
            order=len(route_points) + 1, placeId=candidate.placeId, name=candidate.name,
            lat=candidate.lat, lon=candidate.lon, visitMinutes=visit_minutes,
            scheduleStatus=schedule_status, isFood=candidate.isFood,
        ))
        legs.append(leg)
        current = candidate.lat, candidate.lon
        elapsed_seconds = projected_seconds

    if not route_points:
        if skipped_for_budget:
            raise TimeBudgetExceeded()
        raise RouteNotFound()

    warnings = ["Время посещения пока оценочное: 40 минут, для еды — 60 минут"]
    if approximate_start:
        warnings.append("Время от вашего фактического местоположения не учтено")
    if preview.centerOnly:
        warnings.append("Поиск мест ограничен центром города")
    if preview.includeFood and not any(point.isFood for point in route_points):
        warnings.append("Подходящее место для еды не поместилось в маршрут")
    if any(point.scheduleStatus == "UNKNOWN" for point in route_points):
        warnings.append("Для части мест 2ГИС не вернул расписание")
    return Route(
        routeId=uuid4(), routeVersion=1, status="READY", cityId=payload.cityId,
        approximateStart=approximate_start, totalMinutes=math.ceil(elapsed_seconds / 60),
        points=route_points, legs=legs, warnings=warnings,
    )


def _candidate_order(candidates: list[PlaceCandidate], include_food: bool) -> list[PlaceCandidate]:
    if not include_food:
        return [candidate for candidate in candidates if not candidate.isFood]
    sights = [candidate for candidate in candidates if not candidate.isFood]
    food = [candidate for candidate in candidates if candidate.isFood]
    if not food:
        return sights
    # Stage 0.3 uses relevance order; full sequence optimization is the boundary of 0.4.
    insertion = min(2, len(sights))
    return sights[:insertion] + food[:1] + sights[insertion:] + food[1:]


def schedule_status_at(schedule: dict, arrival: datetime, visit_minutes: int) -> str:
    if not schedule:
        return "UNKNOWN"
    if schedule.get("is_24x7") is True:
        return "OPEN"
    finish = arrival + timedelta(minutes=visit_minutes)
    saw_hours = False
    # The previous day is needed for intervals such as 20:00–02:00.
    for offset in (0, -1):
        anchor = arrival + timedelta(days=offset)
        day = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")[anchor.weekday()]
        day_data = schedule.get(day)
        if not isinstance(day_data, dict):
            continue
        hours = day_data.get("working_hours")
        if not isinstance(hours, list):
            continue
        saw_hours = True
        for period in hours:
            if not isinstance(period, dict):
                continue
            start_time, end_time = _clock(period.get("from")), _clock(period.get("to"))
            if start_time is None or end_time is None:
                continue
            opened = anchor.replace(hour=start_time[0], minute=start_time[1], second=0, microsecond=0)
            closed = anchor.replace(hour=end_time[0], minute=end_time[1], second=0, microsecond=0)
            if closed <= opened:
                closed += timedelta(days=1)
            if opened <= arrival and finish <= closed:
                return "OPEN"
    has_weekday_data = any(isinstance(schedule.get(day), dict)
                           for day in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"))
    return "CLOSED" if saw_hours or has_weekday_data else "UNKNOWN"


def _clock(value: object) -> tuple[int, int] | None:
    if not isinstance(value, str):
        return None
    try:
        hour, minute = (int(part) for part in value.split(":", 1))
    except (ValueError, TypeError):
        return None
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        return None
    return hour, minute

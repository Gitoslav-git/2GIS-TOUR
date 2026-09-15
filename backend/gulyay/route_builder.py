from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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
    location_hint = preview.locationHint or ("центр" if preview.centerOnly else None)
    search_area = geo.resolve_search_area(payload.cityId, location_hint, city_center)
    if payload.startLocation:
        start = (payload.startLocation.lat, payload.startLocation.lon)
        approximate_start = False
    else:
        start = (search_area.lat, search_area.lon)
        approximate_start = True

    candidates = geo.search_places(payload.cityId, preview, search_area)
    if not candidates:
        raise RouteNotFound()
    candidates = _candidate_order(candidates, preview.includeFood, start)
    current, elapsed_seconds = start, 0
    route_points, legs = [], []
    skipped_for_budget = False
    local_now = now or datetime.now(city_timezone())

    # Stop near the requested budget and cap first-build traffic to 10 real Routing checks.
    target_seconds = preview.durationMinutes * 60
    satisfactory_seconds = math.floor(target_seconds * 0.9)
    for candidate in candidates[:10]:
        if len(route_points) >= 8 or elapsed_seconds >= satisfactory_seconds:
            break
        visit_minutes = 60 if candidate.isFood else 40
        if target_seconds - elapsed_seconds < 40 * 60:
            break
        if elapsed_seconds + visit_minutes * 60 > target_seconds:
            skipped_for_budget = True
            continue
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

    total_minutes = math.ceil(elapsed_seconds / 60)
    unused_minutes = max(0, preview.durationMinutes - total_minutes)
    warnings = ["Время посещения пока оценочное: 40 минут, для еды — 60 минут"]
    if approximate_start:
        warnings.append("Время от вашего фактического местоположения не учтено")
    if location_hint:
        warnings.append(f"Область поиска: {search_area.label}")
    if preview.includeFood and not any(point.isFood for point in route_points):
        warnings.append("Подходящее место для еды не поместилось в маршрут")
    if any(point.scheduleStatus == "UNKNOWN" for point in route_points):
        warnings.append("Для части мест 2ГИС не вернул расписание")
    if unused_minutes > max(20, math.ceil(preview.durationMinutes * 0.15)):
        warnings.append(
            f"Осталось {unused_minutes} мин.: больше подходящих открытых мест в бюджет не найдено"
        )
    return Route(
        routeId=uuid4(), routeVersion=1, status="READY", cityId=payload.cityId,
        query=payload.query, filters=payload.filters, searchArea=search_area,
        approximateStart=approximate_start, requestedMinutes=preview.durationMinutes,
        totalMinutes=total_minutes, unusedMinutes=unused_minutes,
        points=route_points, legs=legs, warnings=warnings,
    )


def rebuild_route_with_points(source: Route, payload: CreateRoute,
                              candidates: list[PlaceCandidate], geo: GeoProvider,
                              now: datetime | None = None) -> Route:
    """Recalculate an explicitly ordered point list without silently optimizing it."""
    if not 1 <= len(candidates) <= 8:
        raise RouteNotFound()
    if len({candidate.placeId for candidate in candidates}) != len(candidates):
        raise RouteNotFound()

    if payload.startLocation:
        current = payload.startLocation.lat, payload.startLocation.lon
    else:
        current = source.searchArea.lat, source.searchArea.lon
    local_now = now or datetime.now(city_timezone())
    elapsed_seconds = 0
    route_points, legs = [], []
    previous = {point.placeId: point for point in source.points}

    for candidate in candidates:
        old = previous.get(candidate.placeId)
        visit_minutes = old.visitMinutes if old else (60 if candidate.isFood else 40)
        try:
            leg = geo.walking_leg(current, (candidate.lat, candidate.lon),
                                  len(route_points), len(route_points) + 1)
        except GeoRouteNotFound as exc:
            raise RouteNotFound() from exc
        projected_seconds = elapsed_seconds + leg.durationSeconds + visit_minutes * 60
        arrival = local_now + timedelta(seconds=elapsed_seconds + leg.durationSeconds)
        schedule_status = schedule_status_at(candidate.schedule, arrival, visit_minutes)
        if schedule_status == "CLOSED":
            raise RouteNotFound()
        route_points.append(RoutePoint(
            order=len(route_points) + 1, placeId=candidate.placeId, name=candidate.name,
            lat=candidate.lat, lon=candidate.lon, visitMinutes=visit_minutes,
            scheduleStatus=schedule_status, isFood=candidate.isFood,
        ))
        legs.append(leg)
        current = candidate.lat, candidate.lon
        elapsed_seconds = projected_seconds

    total_minutes = math.ceil(elapsed_seconds / 60)
    if total_minutes > source.requestedMinutes:
        raise TimeBudgetExceeded(total_minutes)
    unused_minutes = source.requestedMinutes - total_minutes
    food_required = (any(point.isFood for point in source.points)
                     or any("место для еды" in warning for warning in source.warnings))
    warnings = _route_warnings(
        source.requestedMinutes, unused_minutes, source.approximateStart,
        source.searchArea.label, source.searchArea.label != "Весь город",
        food_required, any(point.isFood for point in route_points),
        any(point.scheduleStatus == "UNKNOWN" for point in route_points),
    )
    return source.model_copy(update={
        "points": route_points, "legs": legs, "totalMinutes": total_minutes,
        "unusedMinutes": unused_minutes, "warnings": warnings,
    })


def _route_warnings(requested_minutes: int, unused_minutes: int,
                    approximate_start: bool, area_label: str,
                    area_is_explicit: bool, food_required: bool, has_food: bool,
                    has_unknown_schedule: bool) -> list[str]:
    warnings = ["Время посещения пока оценочное: 40 минут, для еды — 60 минут"]
    if approximate_start:
        warnings.append("Время от вашего фактического местоположения не учтено")
    if area_is_explicit:
        warnings.append(f"Область поиска: {area_label}")
    if food_required and not has_food:
        warnings.append("После ручного редактирования в маршруте нет места для еды")
    if has_unknown_schedule:
        warnings.append("Для части мест 2ГИС не вернул расписание")
    if unused_minutes > max(20, math.ceil(requested_minutes * 0.15)):
        warnings.append(f"После ручного редактирования осталось {unused_minutes} мин. свободного времени")
    return warnings


def _candidate_order(candidates: list[PlaceCandidate], include_food: bool,
                     start: tuple[float, float]) -> list[PlaceCandidate]:
    """Use a nearest-neighbour shortlist; published legs are still verified by 2GIS Routing."""
    sights = _nearest_order([candidate for candidate in candidates if not candidate.isFood], start)
    if not include_food:
        return sights
    food = _nearest_order([candidate for candidate in candidates if candidate.isFood], start)
    if not food:
        return sights
    insertion = min(2, len(sights))
    return sights[:insertion] + food[:1] + sights[insertion:] + food[1:]


def _nearest_order(candidates: list[PlaceCandidate], start: tuple[float, float]) -> list[PlaceCandidate]:
    remaining, ordered, current = list(candidates), [], start
    while remaining:
        candidate = min(remaining, key=lambda item: _distance_squared(current, (item.lat, item.lon)))
        remaining.remove(candidate)
        ordered.append(candidate)
        current = candidate.lat, candidate.lon
    return ordered


def _distance_squared(start: tuple[float, float], end: tuple[float, float]) -> float:
    # Used only to prioritize which real Routing calls to make, never as published route data.
    lon_scale = math.cos(math.radians((start[0] + end[0]) / 2))
    return (start[0] - end[0]) ** 2 + ((start[1] - end[1]) * lon_scale) ** 2


def city_timezone():
    """Use bundled IANA data; retain a safe pilot-city fallback on minimal Windows installs."""
    try:
        return ZoneInfo("Europe/Moscow")
    except ZoneInfoNotFoundError:
        return timezone(timedelta(hours=3), name="MSK")


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

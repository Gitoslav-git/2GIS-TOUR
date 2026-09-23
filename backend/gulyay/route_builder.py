from __future__ import annotations

import math
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .geo import (GeoConstraintNotFound, GeoProvider, GeoRouteNotFound,
                  candidate_matches_concept)
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
    try:
        search_area = geo.resolve_search_area(payload.cityId, location_hint, city_center)
    except GeoConstraintNotFound:
        if preview.areaStrength == "HARD":
            raise
        search_area = geo.resolve_search_area(payload.cityId, None, city_center)
        location_hint = None
        preview.warnings.append(
            "Предпочтительный район не найден — поиск расширен на город"
        )
    explicit_start_area = None
    if preview.startLocationHint:
        explicit_start_area = geo.resolve_search_area(
            payload.cityId, preview.startLocationHint, city_center,
        )
        start = (explicit_start_area.lat, explicit_start_area.lon)
        approximate_start = False
        start_source = "TEXT_ANCHOR"
        if not location_hint:
            # Compactness is a ranking preference, not a destructive radius filter.
            radius = 6500
            label = explicit_start_area.label
            if preview.directionHint:
                label += f" → {preview.directionHint}"
            search_area = explicit_start_area.model_copy(update={
                "label": label, "radiusMeters": radius,
            })
    elif payload.startLocation:
        start = (payload.startLocation.lat, payload.startLocation.lon)
        approximate_start = False
        start_source = "USER_GEO"
    else:
        start = city_center
        approximate_start = True
        start_source = "CITY_CENTER"

    direction_target = None
    if preview.directionHint:
        direction_area = geo.resolve_search_area(
            payload.cityId, preview.directionHint, city_center,
        )
        direction_target = (direction_area.lat, direction_area.lon)

    candidates = geo.search_places(payload.cityId, preview, search_area)
    if not candidates:
        raise RouteNotFound()
    candidates = _candidate_order(candidates, preview, start, direction_target)
    current, elapsed_seconds = start, 0
    route_points, legs = [], []
    skipped_for_budget = False
    local_now = now or datetime.now(city_timezone())
    walking_seconds = 0
    walking_distance = 0
    routing_checks = 0

    target_minutes = preview.targetDurationMinutes or preview.durationMinutes
    budget_minutes = preview.maxDurationMinutes or preview.durationMinutes
    target_seconds = target_minutes * 60
    budget_seconds = budget_minutes * 60
    satisfactory_seconds = math.floor(target_seconds * _good_duration_utilization())
    max_routing_checks = _max_routing_checks()
    for candidate in candidates:
        if (len(route_points) >= 8 or elapsed_seconds >= satisfactory_seconds
                or routing_checks >= max_routing_checks):
            break
        visit_minutes = _visit_minutes(candidate, preview.routePace)
        if budget_seconds - elapsed_seconds < min(20, visit_minutes) * 60:
            break
        if elapsed_seconds + visit_minutes * 60 > budget_seconds:
            skipped_for_budget = True
            continue
        direct_distance = _approx_distance_meters(current, (candidate.lat, candidate.lon))
        if (preview.maxWalkingMinutes is not None
                and direct_distance > preview.maxWalkingMinutes * 130):
            continue
        if (preview.maxWalkingDistanceMeters is not None
                and direct_distance > preview.maxWalkingDistanceMeters):
            continue
        try:
            routing_checks += 1
            leg = geo.walking_leg(current, (candidate.lat, candidate.lon),
                                  len(route_points), len(route_points) + 1)
        except GeoRouteNotFound:
            continue
        if (preview.maxWalkingMinutes is not None
                and math.ceil(leg.durationSeconds / 60) > preview.maxWalkingMinutes):
            continue
        if (preview.maxWalkingDistanceMeters is not None
                and leg.distanceMeters > preview.maxWalkingDistanceMeters):
            continue
        if (preview.maxTotalWalkingMinutes is not None
                and math.ceil((walking_seconds + leg.durationSeconds) / 60)
                > preview.maxTotalWalkingMinutes):
            continue
        if (preview.maxTotalWalkingDistanceMeters is not None
                and walking_distance + leg.distanceMeters
                > preview.maxTotalWalkingDistanceMeters):
            continue
        projected_seconds = elapsed_seconds + leg.durationSeconds + visit_minutes * 60
        if projected_seconds > budget_seconds:
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
        walking_seconds += leg.durationSeconds
        walking_distance += leg.distanceMeters

    if not route_points:
        if skipped_for_budget:
            raise TimeBudgetExceeded()
        raise RouteNotFound()

    if preview.foodMode == "REQUIRED" and not any(point.isFood for point in route_points):
        raise RouteNotFound()

    total_minutes = math.ceil(elapsed_seconds / 60)
    unused_minutes = max(0, target_minutes - total_minutes)
    utilization = total_minutes / target_minutes
    unmet: list[str] = []
    if utilization < _good_duration_utilization():
        unmet.append("DURATION_TARGET")
    if preview.minDurationMinutes is not None and total_minutes < preview.minDurationMinutes:
        unmet.append("MINIMUM_DURATION")
    if len(route_points) == 1 and target_minutes >= 120:
        unmet.append("ROUTE_VARIETY")
    planning_status = "DEGRADED" if unmet else "SUCCESS"

    warnings = [*preview.warnings,
                "Время посещения оценено по типу места и темпу прогулки"]
    if explicit_start_area:
        warnings.append(f"Старт по указанному ориентиру: {explicit_start_area.label}")
    if preview.directionHint:
        warnings.append(f"Направление прогулки: {preview.directionHint}")
    if preview.preferShortWalks:
        warnings.append("Из полноценных вариантов выбран наиболее компактный маршрут")
    if preview.preferredWalkingMinutes is not None and preview.maxWalkingMinutes is None:
        warnings.append(
            f"Желаемая длина перехода — около {preview.preferredWalkingMinutes} мин.; "
            "это мягкое предпочтение"
        )
    if preview.maxWalkingMinutes is not None:
        warnings.append(
            f"Каждый пеший переход — не более {preview.maxWalkingMinutes} мин."
        )
    if approximate_start:
        warnings.append("Геопозиция и старт в тексте не указаны — маршрут начат от центра города")
    if location_hint:
        warnings.append(f"Область поиска: {search_area.label}")
    if preview.foodMode == "OPTIONAL" and not any(point.isFood for point in route_points):
        warnings.append("Подходящее место для еды не поместилось в маршрут")
    if any(point.scheduleStatus == "UNKNOWN" for point in route_points):
        warnings.append("Для части мест 2ГИС не вернул расписание")
    if planning_status == "DEGRADED":
        warnings.append(
            f"Маршрут заполнен на {round(utilization * 100)}%: поиск был расширен, "
            "но подходящих открытых мест недостаточно"
        )
    return Route(
        routeId=uuid4(), routeVersion=1, status="READY", cityId=payload.cityId,
        query=payload.query, filters=payload.filters, searchArea=search_area,
        approximateStart=approximate_start, startLat=start[0], startLon=start[1],
        startSource=start_source, maxWalkingMinutes=preview.maxWalkingMinutes,
        planningStatus=planning_status, durationUtilization=round(utilization, 3),
        unmetPreferences=unmet, requestedMinutes=target_minutes,
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

    if source.startLat is not None and source.startLon is not None:
        current = source.startLat, source.startLon
    elif source.legs and source.legs[0].geometry:
        # Routes persisted before 0.5.4 do not have explicit start fields, but
        # the first Routing geometry still contains the exact original start.
        first_lon, first_lat = source.legs[0].geometry[0]
        current = first_lat, first_lon
    elif payload.startLocation:
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
        if (source.maxWalkingMinutes is not None
                and math.ceil(leg.durationSeconds / 60) > source.maxWalkingMinutes):
            raise RouteNotFound()
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
    retained_prefixes = (
        "Старт по указанному ориентиру:",
        "Направление прогулки:",
        "Из полноценных вариантов выбран наиболее компактный маршрут",
        "Желаемая длина перехода",
        "Каждый пеший переход — не более",
    )
    utilization = total_minutes / source.requestedMinutes
    unmet = [item for item in source.unmetPreferences if item != "DURATION_TARGET"]
    if utilization < _good_duration_utilization():
        unmet.append("DURATION_TARGET")
    retained = [warning for warning in source.warnings
                if warning.startswith(retained_prefixes)]
    warnings = retained + [warning for warning in warnings if warning not in retained]
    return source.model_copy(update={
        "points": route_points, "legs": legs, "totalMinutes": total_minutes,
        "unusedMinutes": unused_minutes, "warnings": warnings,
        "durationUtilization": round(utilization, 3),
        "planningStatus": "DEGRADED" if unmet else "SUCCESS",
        "unmetPreferences": list(dict.fromkeys(unmet)),
    })


def _route_warnings(requested_minutes: int, unused_minutes: int,
                    approximate_start: bool, area_label: str,
                    area_is_explicit: bool, food_required: bool, has_food: bool,
                    has_unknown_schedule: bool) -> list[str]:
    warnings = ["Время посещения пока оценочное: 40 минут, для еды — 60 минут"]
    if approximate_start:
        warnings.append("Геопозиция и старт в тексте не указаны — маршрут начат от центра города")
    if area_is_explicit:
        warnings.append(f"Область поиска: {area_label}")
    if food_required and not has_food:
        warnings.append("После ручного редактирования в маршруте нет места для еды")
    if has_unknown_schedule:
        warnings.append("Для части мест 2ГИС не вернул расписание")
    if unused_minutes > max(20, math.ceil(requested_minutes * 0.15)):
        warnings.append(f"После ручного редактирования осталось {unused_minutes} мин. свободного времени")
    return warnings


def _candidate_order(candidates: list[PlaceCandidate], preview: QueryPreview,
                     start: tuple[float, float],
                     direction_target: tuple[float, float] | None) -> list[PlaceCandidate]:
    """Use a nearest-neighbour shortlist; published legs are still verified by 2GIS Routing."""
    sights = _preference_order(
        [candidate for candidate in candidates if not candidate.isFood], start,
        direction_target, preview,
    )
    if not preview.includeFood:
        return sights
    food = _preference_order(
        [candidate for candidate in candidates if candidate.isFood], start,
        direction_target, preview,
    )
    if not food:
        return sights
    if preview.foodTiming == "START" or (
            preview.foodMode == "REQUIRED" and preview.foodTiming == "ANY"):
        insertion = 0
    elif preview.foodMode == "REQUIRED" and preview.foodTiming == "MIDDLE":
        insertion = min(1, len(sights))
    elif preview.foodTiming == "END":
        insertion = len(sights)
    else:
        insertion = min(max(1, len(sights) // 2), len(sights))
    return sights[:insertion] + food[:1] + sights[insertion:] + food[1:]


def _preference_order(candidates: list[PlaceCandidate], start: tuple[float, float],
                      direction_target: tuple[float, float] | None,
                      preview: QueryPreview) -> list[PlaceCandidate]:
    remaining, ordered, current = list(candidates), [], start
    while remaining:
        candidate = min(remaining, key=lambda item: _candidate_score(
            current, item, direction_target, preview,
        ))
        remaining.remove(candidate)
        ordered.append(candidate)
        current = candidate.lat, candidate.lon
    return ordered


def _candidate_score(current: tuple[float, float], candidate: PlaceCandidate,
                     direction_target: tuple[float, float] | None,
                     preview: QueryPreview) -> float:
    coordinates = candidate.lat, candidate.lon
    leg = _approx_distance_meters(current, coordinates)
    compactness_weight = {"LOW": 0.7, "NORMAL": 1.0, "HIGH": 1.8}[preview.compactness]
    score = leg * compactness_weight
    if preview.preferredWalkingMinutes is not None:
        preferred_distance = preview.preferredWalkingMinutes * 80
        score += max(0.0, leg - preferred_distance) * 1.5
    for excluded in preview.softExclusions:
        if candidate_matches_concept(candidate, excluded):
            score += 10_000
    if direction_target is None:
        return score
    current_to_target = _approx_distance_meters(current, direction_target)
    candidate_to_target = _approx_distance_meters(coordinates, direction_target)
    # Moving away from the requested direction is expensive; moving toward it is rewarded
    # modestly so «short transitions» still wins over a single long jump to the target.
    regression = max(0.0, candidate_to_target - current_to_target)
    progress = max(0.0, current_to_target - candidate_to_target)
    return score + regression * 2.5 - progress * 0.25


def _visit_minutes(candidate: PlaceCandidate, pace: str) -> int:
    searchable = " ".join([candidate.name, *candidate.rubrics]).casefold().replace("ё", "е")
    if candidate.isFood:
        baseline = 60
    elif any(word in searchable for word in ("музей", "галере", "выстав", "зоопарк")):
        baseline = 75
    elif any(word in searchable for word in ("парк", "сад", "набереж", "кремль")):
        baseline = 50
    elif any(word in searchable for word in ("памятник", "скульптур", "арт-объект")):
        baseline = 25
    else:
        baseline = 40
    multiplier = {"RELAXED": 1.25, "NORMAL": 1.0, "INTENSIVE": 0.75}[pace]
    return max(15, min(120, round(baseline * multiplier / 5) * 5))


def _good_duration_utilization() -> float:
    try:
        value = float(os.getenv("ROUTE_GOOD_DURATION_UTILIZATION", "0.85"))
    except ValueError:
        return 0.85
    return max(0.65, min(1.0, value))


def _max_routing_checks() -> int:
    try:
        value = int(os.getenv("ROUTE_MAX_ROUTING_CHECKS", "6"))
    except ValueError:
        return 6
    return max(3, min(8, value))


def _approx_distance_meters(start: tuple[float, float], end: tuple[float, float]) -> float:
    return math.sqrt(_distance_squared(start, end)) * 111_320


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

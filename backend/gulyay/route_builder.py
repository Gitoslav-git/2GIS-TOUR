from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .geo import (GeoConstraintNotFound, GeoProvider, GeoRouteNotFound,
                  candidate_matches_concept, candidate_matches_food)
from .models import (CreateRoute, PlaceCandidate, QueryPreview, Route, RouteLeg,
                     RoutePoint)
from .planning_debug import planning_log


class RouteNotFound(Exception):
    pass


class TimeBudgetExceeded(Exception):
    def __init__(self, minimum_minutes: int | None = None):
        self.minimum_minutes = minimum_minutes


class _RoutingBudgetExhausted(Exception):
    pass


_LegKey = tuple[tuple[float, float], tuple[float, float]]


@dataclass
class _RoutingChecks:
    """Share directed legs, including no-route results, within one build."""
    remaining: int
    legs: dict[_LegKey, RouteLeg | None] = field(default_factory=dict)

    def walking_leg(self, geo: GeoProvider, start: tuple[float, float],
                    end: tuple[float, float], from_order: int,
                    reserve: int = 0) -> RouteLeg:
        key = (start, end)
        if key not in self.legs:
            if self.remaining <= reserve:
                raise _RoutingBudgetExhausted()
            self.remaining -= 1
            try:
                self.legs[key] = geo.walking_leg(start, end, from_order, from_order + 1)
            except GeoRouteNotFound:
                self.legs[key] = None
        leg = self.legs[key]
        if leg is None:
            raise GeoRouteNotFound()
        return leg.model_copy(update={"fromOrder": from_order, "toOrder": from_order + 1})


@dataclass
class _RoutePlan:
    plan_id: str
    candidates: list[PlaceCandidate]
    estimated_minutes: int
    relaxation: int
    area_relaxed: bool
    score: float
    score_breakdown: dict[str, float]


@dataclass
class _BuiltPlan:
    plan: _RoutePlan
    points: list[RoutePoint] = field(default_factory=list)
    legs: list[RouteLeg] = field(default_factory=list)
    candidates: list[PlaceCandidate] = field(default_factory=list)
    arrivals: list[datetime] = field(default_factory=list)
    elapsed_seconds: int = 0
    walking_seconds: int = 0
    walking_distance: int = 0
    score: float = 0.0
    score_breakdown: dict[str, float] = field(default_factory=dict)
    unmet: list[str] = field(default_factory=list)
    hard_violations: list[str] = field(default_factory=list)
    budget_limited: bool = False


def build_route(payload: CreateRoute, preview: QueryPreview, geo: GeoProvider,
                now: datetime | None = None, trace_id: str | None = None) -> Route:
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

    local_now = now or datetime.now(city_timezone())
    target_minutes = preview.targetDurationMinutes or preview.durationMinutes
    routing_budget = _RoutingChecks(_max_routing_checks())
    attempts = 0
    best: _BuiltPlan | None = None
    best_area = search_area
    candidates = geo.search_places(payload.cityId, preview, search_area)
    planning_log(trace_id, "dgis_candidates", attempt=1, area=search_area.label,
                 count=len(candidates), candidates=_candidate_debug(candidates))
    search_rounds = [(search_area, candidates, 0)]
    expanded = False

    while search_rounds:
        active_area, active_candidates, search_relaxation = search_rounds.pop(0)
        if not active_candidates:
            plans: list[_RoutePlan] = []
        else:
            plans = _make_route_plans(
                active_candidates, preview, start, direction_target, search_relaxation,
            )
        planning_log(trace_id, "route_variants", area=active_area.label,
                     variants=[_plan_debug(plan) for plan in plans])
        plans, reserve = _comparison_order(plans, start, routing_budget)
        if reserve:
            planning_log(trace_id, "routing_budget_reserved",
                         planId=plans[1].plan_id, checks=reserve)
        scheduled = [(plan, reserve if index == 0 else 0)
                     for index, plan in enumerate(plans)]
        while scheduled:
            plan, protected_checks = scheduled.pop(0)
            attempts += 1
            built = _materialize_plan(
                plan, preview, geo, start, local_now, routing_budget, protected_checks,
            )
            if built.budget_limited and protected_checks:
                # Revisit after the reserved challenger; cached legs cost nothing.
                scheduled.insert(1, (plan, 0))
            if not built.points:
                planning_log(trace_id, "route_variant_rejected", planId=plan.plan_id,
                             reason=("ROUTING_BUDGET_EXHAUSTED" if built.budget_limited
                                     else "NO_REACHABLE_OPEN_POINTS"))
                continue
            built.hard_violations = _hard_violations(built, preview)
            if built.hard_violations:
                planning_log(trace_id, "route_variant_rejected", planId=plan.plan_id,
                             hardViolations=built.hard_violations,
                             points=[point.name for point in built.points])
                continue
            built.score, built.score_breakdown = _route_quality(built, preview)
            built.unmet = _unmet_preferences(built, preview)
            planning_log(
                trace_id, "route_variant_evaluated", planId=plan.plan_id,
                relaxation=plan.relaxation, score=round(built.score, 2),
                scoreBreakdown=built.score_breakdown,
                totalMinutes=math.ceil(built.elapsed_seconds / 60),
                walkingMinutes=math.ceil(built.walking_seconds / 60),
                pointIds=[point.placeId for point in built.points],
                unmet=built.unmet, routingChecksLeft=routing_budget.remaining,
                budgetLimited=built.budget_limited,
            )
            if best is None or (not built.unmet, built.score) > (not best.unmet, best.score):
                best = built
                best_area = active_area
        if best is not None and not best.unmet and best.score >= _good_quality_score():
            break
        # A named SOFT area may be widened only after its best route is poor.
        if (not expanded and location_hint and preview.areaStrength == "SOFT"
                and routing_budget.remaining > 0):
            expanded = True
            city_area = geo.resolve_search_area(payload.cityId, None, city_center)
            wider = geo.search_places(payload.cityId, preview, city_area)
            merged = _merge_candidates(active_candidates, wider)
            planning_log(trace_id, "dgis_candidates", attempt=2, area=city_area.label,
                         reason="SOFT_AREA_RELAXED", count=len(merged),
                         candidates=_candidate_debug(merged))
            search_rounds.append((city_area, merged, 1))

    if best is None:
        planning_log(trace_id, "planning_failed", reason="NO_HARD_VALID_ROUTE",
                     routingChecksUsed=_max_routing_checks() - routing_budget.remaining)
        raise RouteNotFound()

    route_points, legs = best.points, best.legs
    total_minutes = math.ceil(best.elapsed_seconds / 60)
    unused_minutes = max(0, target_minutes - total_minutes)
    utilization = total_minutes / target_minutes
    unmet = best.unmet
    planning_status = "DEGRADED" if unmet else "SUCCESS"

    warnings = [*preview.warnings,
                "Время посещения оценено по типу места и темпу прогулки"]
    if best.plan.area_relaxed:
        warnings.append("Предпочтительный район дал слабый маршрут — поиск расширен на город")
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
        warnings.append(f"Область поиска: {best_area.label}")
    if preview.foodMode == "OPTIONAL" and not any(point.isFood for point in route_points):
        warnings.append("Подходящее место для еды не поместилось в маршрут")
    if any(point.scheduleStatus == "UNKNOWN" for point in route_points):
        warnings.append("Для части мест 2ГИС не вернул расписание")
    if planning_status == "DEGRADED":
        warnings.append(
            f"Маршрут заполнен на {round(utilization * 100)}%: "
            "в пределах доступных проверок не удалось выполнить все пожелания"
        )
    planning_log(
        trace_id, "route_selected", planId=best.plan.plan_id,
        reason="highest_quality_hard_valid_variant", score=round(best.score, 2),
        scoreBreakdown=best.score_breakdown, attempts=attempts,
        area=best_area.label,
        routingChecksUsed=_max_routing_checks() - routing_budget.remaining,
        totalMinutes=total_minutes, targetMinutes=target_minutes,
        points=[{"placeId": point.placeId, "name": point.name}
                for point in route_points], unmet=unmet,
    )
    return Route(
        routeId=uuid4(), routeVersion=1, status="READY", cityId=payload.cityId,
        query=payload.query, filters=payload.filters, searchArea=best_area,
        approximateStart=approximate_start, startLat=start[0], startLon=start[1],
        startSource=start_source, maxWalkingMinutes=preview.maxWalkingMinutes,
        planningStatus=planning_status, durationUtilization=round(utilization, 3),
        planningScore=round(best.score, 2), planningAttempts=max(1, attempts),
        unmetPreferences=unmet, requestedMinutes=target_minutes,
        totalMinutes=total_minutes, unusedMinutes=unused_minutes,
        points=route_points, legs=legs, warnings=warnings,
    )


def _comparison_order(plans: list[_RoutePlan], start: tuple[float, float],
                      checks: _RoutingChecks) -> tuple[list[_RoutePlan], int]:
    """Reserve unique legs for the best challenger affordable beside the leader.

    If two complete sequences cannot fit, keep the highest-ranked sequence intact.
    This matters for explicit eight-place requests with an eight-check budget.
    """
    def missing_legs(plan: _RoutePlan) -> set[_LegKey]:
        coordinates = [start, *((item.lat, item.lon) for item in plan.candidates)]
        return set(zip(coordinates, coordinates[1:])) - checks.legs.keys()

    if len(plans) < 2:
        return plans, 0
    primary = missing_legs(plans[0])
    for index, challenger in enumerate(plans[1:], 1):
        alternative = missing_legs(challenger)
        if len(primary | alternative) <= checks.remaining:
            ordered = [plans[0], challenger, *plans[1:index], *plans[index + 1:]]
            return ordered, len(alternative - primary)
    return plans, 0


def _make_route_plans(candidates: list[PlaceCandidate], preview: QueryPreview,
                      start: tuple[float, float],
                      direction_target: tuple[float, float] | None,
                      search_relaxation: int = 0) -> list[_RoutePlan]:
    sights = [candidate for candidate in candidates if not candidate.isFood]
    foods = [candidate for candidate in candidates if candidate.isFood]
    if not sights and not (preview.allowSinglePlace and foods):
        return []
    ordered_seeds = _preference_order(sights, start, direction_target, preview)
    seeds = ordered_seeds[:min(3, len(ordered_seeds))]
    interest_seeds = sorted(
        sights,
        key=lambda item: (
            -_candidate_interest_value(item, preview),
            _approx_distance_meters(start, (item.lat, item.lon)),
        ),
    )
    for item in interest_seeds:
        if item not in seeds:
            seeds.append(item)
        if len(seeds) >= min(6, len(sights)):
            break
    cluster_size = min(14, max(8, _desired_point_count(preview) + 4))
    clusters: list[tuple[list[PlaceCandidate], PlaceCandidate | None]] = []
    if sights:
        clusters.append((sights, None))
    for seed in seeds:
        neighborhood = sorted(
            sights,
            key=lambda item: (
                _approx_distance_meters((seed.lat, seed.lon), (item.lat, item.lon)),
                _candidate_score(start, item, direction_target, preview),
            ),
        )[:cluster_size]
        clusters.append((neighborhood, seed))

    plans: list[_RoutePlan] = []
    seen: set[tuple[str, ...]] = set()
    for local_relaxation in (0, 1):
        relaxation = max(search_relaxation, local_relaxation)
        soft_scale = 1.0 if relaxation == 0 else 0.45
        for cluster_index, (cluster, seed) in enumerate(clusters or [([], None)]):
            if seed is None:
                ordered_sights = _preference_order(
                    cluster, start, direction_target, preview, soft_scale,
                )
            else:
                ordered_sights = [seed, *_preference_order(
                    [item for item in cluster if item.placeId != seed.placeId],
                    (seed.lat, seed.lon), direction_target, preview, soft_scale,
                )]
            ordered_food = _preference_order(
                foods, start, direction_target, preview, soft_scale,
            )
            ordered = _insert_food(ordered_sights, ordered_food, preview)
            selected, estimated_minutes = _approximate_route(
                ordered, preview, start,
            )
            signature = tuple(item.placeId for item in selected)
            if not signature or signature in seen:
                continue
            seen.add(signature)
            score, breakdown = _candidate_sequence_quality(
                selected, estimated_minutes, preview, start,
            )
            plans.append(_RoutePlan(
                plan_id=f"r{relaxation}-c{cluster_index}", candidates=selected,
                estimated_minutes=estimated_minutes, relaxation=relaxation,
                area_relaxed=search_relaxation > 0,
                score=score, score_breakdown=breakdown,
            ))
    return sorted(plans, key=lambda item: item.score, reverse=True)[:12]


def _approximate_route(candidates: list[PlaceCandidate], preview: QueryPreview,
                       start: tuple[float, float]) -> tuple[list[PlaceCandidate], int]:
    current = start
    selected: list[PlaceCandidate] = []
    elapsed = walking = walking_distance = 0
    budget_seconds = (preview.maxDurationMinutes or preview.durationMinutes) * 60
    max_points = preview.requestedPlaceCount or 8
    for candidate in candidates:
        if len(selected) >= max_points:
            break
        distance = _approx_distance_meters(current, (candidate.lat, candidate.lon))
        leg_seconds = max(60, round(distance / 80 * 60))
        if preview.maxWalkingMinutes is not None and leg_seconds > preview.maxWalkingMinutes * 60:
            continue
        if preview.maxWalkingDistanceMeters is not None and distance > preview.maxWalkingDistanceMeters:
            continue
        if (preview.maxTotalWalkingMinutes is not None
                and walking + leg_seconds > preview.maxTotalWalkingMinutes * 60):
            continue
        if (preview.maxTotalWalkingDistanceMeters is not None
                and walking_distance + distance > preview.maxTotalWalkingDistanceMeters):
            continue
        visit_seconds = _visit_minutes(candidate, preview.routePace) * 60
        if elapsed + leg_seconds + visit_seconds > budget_seconds:
            continue
        selected.append(candidate)
        current = candidate.lat, candidate.lon
        elapsed += leg_seconds + visit_seconds
        walking += leg_seconds
        walking_distance += round(distance)
        if _enough_points_and_time(selected, elapsed, preview):
            break
    return selected, math.ceil(elapsed / 60)


def _materialize_plan(plan: _RoutePlan, preview: QueryPreview, geo: GeoProvider,
                      start: tuple[float, float], local_now: datetime,
                      routing_budget: _RoutingChecks, reserve: int = 0) -> _BuiltPlan:
    built = _BuiltPlan(plan=plan)
    current = start
    budget_seconds = (preview.maxDurationMinutes or preview.durationMinutes) * 60
    for candidate in plan.candidates:
        if len(built.points) >= (preview.requestedPlaceCount or 8):
            break
        distance = _approx_distance_meters(current, (candidate.lat, candidate.lon))
        if (preview.maxWalkingMinutes is not None
                and distance > preview.maxWalkingMinutes * 130):
            continue
        if (preview.maxWalkingDistanceMeters is not None
                and distance > preview.maxWalkingDistanceMeters):
            continue
        visit_minutes = _visit_minutes(candidate, preview.routePace)
        if built.elapsed_seconds + visit_minutes * 60 > budget_seconds:
            continue
        try:
            leg = routing_budget.walking_leg(
                geo, current, (candidate.lat, candidate.lon), len(built.points), reserve,
            )
        except _RoutingBudgetExhausted:
            built.budget_limited = True
            break
        except GeoRouteNotFound:
            continue
        if (preview.maxWalkingMinutes is not None
                and math.ceil(leg.durationSeconds / 60) > preview.maxWalkingMinutes):
            continue
        if (preview.maxWalkingDistanceMeters is not None
                and leg.distanceMeters > preview.maxWalkingDistanceMeters):
            continue
        if (preview.maxTotalWalkingMinutes is not None
                and math.ceil((built.walking_seconds + leg.durationSeconds) / 60)
                > preview.maxTotalWalkingMinutes):
            continue
        if (preview.maxTotalWalkingDistanceMeters is not None
                and built.walking_distance + leg.distanceMeters
                > preview.maxTotalWalkingDistanceMeters):
            continue
        projected = built.elapsed_seconds + leg.durationSeconds + visit_minutes * 60
        if projected > budget_seconds:
            continue
        arrival = local_now + timedelta(seconds=built.elapsed_seconds + leg.durationSeconds)
        schedule_status = schedule_status_at(candidate.schedule, arrival, visit_minutes)
        if schedule_status == "CLOSED":
            continue
        built.points.append(RoutePoint(
            order=len(built.points) + 1, placeId=candidate.placeId, name=candidate.name,
            lat=candidate.lat, lon=candidate.lon, visitMinutes=visit_minutes,
            scheduleStatus=schedule_status, isFood=candidate.isFood,
        ))
        built.legs.append(leg)
        built.candidates.append(candidate)
        built.arrivals.append(arrival)
        built.elapsed_seconds = projected
        built.walking_seconds += leg.durationSeconds
        built.walking_distance += leg.distanceMeters
        current = candidate.lat, candidate.lon
        if _enough_points_and_time(built.candidates, built.elapsed_seconds, preview):
            break
    return built


def _hard_violations(route: _BuiltPlan, preview: QueryPreview) -> list[str]:
    violations: list[str] = []
    total_minutes = math.ceil(route.elapsed_seconds / 60)
    if len(route.points) == 1 and not preview.allowSinglePlace:
        violations.append("MINIMUM_TWO_POINTS")
    if preview.requestedPlaceCount is not None and len(route.points) != preview.requestedPlaceCount:
        violations.append("REQUESTED_PLACE_COUNT")
    if preview.minDurationMinutes is not None and total_minutes < preview.minDurationMinutes:
        violations.append("MINIMUM_DURATION")
    for concept in preview.hardInterests:
        if not any(candidate_matches_concept(item, concept) for item in route.candidates):
            violations.append(f"INTEREST:{concept}")
    for concept in preview.hardExclusions:
        if any(candidate_matches_concept(item, concept) for item in route.candidates):
            violations.append(f"EXCLUSION:{concept}")
    food_items = [item for item in route.candidates if item.isFood]
    if preview.foodMode == "REQUIRED" and not food_items:
        violations.append("FOOD_REQUIRED")
    if preview.foodPreferences and food_items and not any(
            candidate_matches_food(item, preference)
            for item in food_items for preference in preview.foodPreferences):
        violations.append("FOOD_PREFERENCE")
    if preview.foodMode == "REQUIRED" and not _food_timing_satisfied(route, preview):
        violations.append("FOOD_TIMING")
    return list(dict.fromkeys(violations))


def _unmet_preferences(route: _BuiltPlan, preview: QueryPreview) -> list[str]:
    total_minutes = math.ceil(route.elapsed_seconds / 60)
    target = preview.targetDurationMinutes or preview.durationMinutes
    unmet: list[str] = []
    if (preview.durationMode != "MAXIMUM"
            and total_minutes / target < _good_duration_utilization()):
        unmet.append("DURATION_TARGET")
    if len(route.points) < 2 and not preview.allowSinglePlace:
        unmet.append("ROUTE_VARIETY")
    if route.score < _good_quality_score():
        unmet.append("ROUTE_QUALITY")
    return unmet


def _route_quality(route: _BuiltPlan, preview: QueryPreview) -> tuple[float, dict[str, float]]:
    total_minutes = math.ceil(route.elapsed_seconds / 60)
    score, components = _quality_components(
        route.candidates, total_minutes, route.walking_seconds,
        route.walking_distance, preview,
        area_score=65.0 if route.plan.area_relaxed else 100.0,
    )
    if preview.foodMode != "NONE" and not _food_timing_satisfied(route, preview):
        score += (0.0 - components["food"]) * 0.08
        components["food"] = 0.0
    return max(0.0, score), components


def _candidate_sequence_quality(candidates: list[PlaceCandidate], total_minutes: int,
                                preview: QueryPreview,
                                start: tuple[float, float]) -> tuple[float, dict[str, float]]:
    current = start
    distance = 0
    for candidate in candidates:
        next_point = candidate.lat, candidate.lon
        distance += round(_approx_distance_meters(current, next_point))
        current = next_point
    walking_seconds = round(distance / 80 * 60)
    return _quality_components(candidates, total_minutes, walking_seconds, distance, preview)


def _quality_components(candidates: list[PlaceCandidate], total_minutes: int,
                        walking_seconds: int, walking_distance: int,
                        preview: QueryPreview,
                        area_score: float = 100.0) -> tuple[float, dict[str, float]]:
    target = preview.targetDurationMinutes or preview.durationMinutes
    if preview.durationMode == "MAXIMUM":
        duration_score = 100.0
    else:
        duration_score = max(0.0, 100 - abs(total_minutes - target) / target * 140)
    priority_weight = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
    possible = sum(priority_weight[preview.interestPriorities.get(item, "MEDIUM")]
                   for item in preview.interests)
    covered = sum(
        priority_weight[preview.interestPriorities.get(concept, "MEDIUM")]
        for concept in preview.interests
        if any(candidate_matches_concept(item, concept) for item in candidates)
    )
    interest_score = 100.0 if possible == 0 else covered / possible * 100
    desired = preview.requestedPlaceCount or _desired_point_count(preview)
    count_score = min(len(candidates), desired) / max(1, desired) * 100
    average_leg_minutes = walking_seconds / 60 / max(1, len(candidates))
    preferred = preview.preferredWalkingMinutes
    if preferred is None:
        walking_score = max(35.0, 100 - average_leg_minutes * 2)
    else:
        walking_score = max(0.0, 100 - max(0.0, average_leg_minutes - preferred) * 6)
    average_distance = walking_distance / max(1, len(candidates))
    compactness_score = max(0.0, 100 - max(0.0, average_distance - 500) / 20)
    food_items = [item for item in candidates if item.isFood]
    if preview.foodMode == "NONE":
        food_score = 100.0
    elif not food_items:
        food_score = 0.0 if preview.foodMode == "REQUIRED" else 55.0
    elif not preview.foodPreferences:
        food_score = 100.0
    else:
        food_score = 100.0 if any(
            candidate_matches_food(item, preference)
            for item in food_items for preference in preview.foodPreferences
        ) else 0.0
    variety_keys = set()
    for candidate in candidates:
        matches = tuple(concept for concept in preview.interests
                        if candidate_matches_concept(candidate, concept))
        variety_keys.add(matches or tuple(candidate.rubrics[:1]) or (candidate.name,))
    variety_score = min(100.0, len(variety_keys) / max(1, min(len(candidates), 4)) * 100)
    components = {
        "duration": round(duration_score, 1),
        "interests": round(interest_score, 1),
        "pointCount": round(count_score, 1),
        "walking": round(walking_score, 1),
        "compactness": round(compactness_score, 1),
        "area": round(area_score, 1),
        "food": round(food_score, 1),
        "variety": round(variety_score, 1),
    }
    weights = {"duration": 0.30, "interests": 0.20, "pointCount": 0.12,
               "walking": 0.10, "compactness": 0.10, "area": 0.05,
               "food": 0.08, "variety": 0.05}
    return sum(components[key] * weights[key] for key in weights), components


def _food_timing_satisfied(route: _BuiltPlan, preview: QueryPreview) -> bool:
    food_indices = [index for index, point in enumerate(route.points) if point.isFood]
    if preview.foodMode != "REQUIRED" and not food_indices:
        return True
    if not food_indices:
        return False
    timing = preview.foodTiming
    if timing == "ANY":
        return True
    if timing == "START":
        return 0 in food_indices
    if timing == "END":
        return len(route.points) - 1 in food_indices
    if timing == "MIDDLE":
        return any(0 < index < len(route.points) - 1 for index in food_indices)
    if timing == "EXACT_TIME" and preview.foodExactTime:
        hour, minute = (int(part) for part in preview.foodExactTime.split(":"))
        return any(abs((route.arrivals[index] - route.arrivals[index].replace(
            hour=hour, minute=minute, second=0, microsecond=0,
        )).total_seconds()) <= 30 * 60 for index in food_indices)
    return timing != "EXACT_TIME"


def _enough_points_and_time(candidates: list[PlaceCandidate], elapsed_seconds: int,
                            preview: QueryPreview) -> bool:
    if preview.foodMode == "REQUIRED" and not any(item.isFood for item in candidates):
        return False
    if any(not any(candidate_matches_concept(item, concept) for item in candidates)
           for concept in preview.hardInterests):
        return False
    if preview.requestedPlaceCount is not None:
        return len(candidates) >= preview.requestedPlaceCount
    minimum_points = 1 if preview.allowSinglePlace else 2
    if len(candidates) < minimum_points:
        return False
    if preview.durationMode == "MAXIMUM":
        return len(candidates) >= _desired_point_count(preview)
    target = preview.targetDurationMinutes or preview.durationMinutes
    return elapsed_seconds >= math.floor(target * 60 * _good_duration_utilization())


def _desired_point_count(preview: QueryPreview) -> int:
    if preview.requestedPlaceCount is not None:
        return preview.requestedPlaceCount
    target = preview.targetDurationMinutes or preview.durationMinutes
    divisor = {"LOW": 75, "NORMAL": 55, "HIGH": 40}[preview.placeDensity]
    return max(2, min(8, math.ceil(target / divisor)))


def _merge_candidates(first: list[PlaceCandidate], second: list[PlaceCandidate]) -> list[PlaceCandidate]:
    result = list(first)
    positions = {item.placeId: index for index, item in enumerate(result)}
    for item in second:
        if item.placeId not in positions:
            positions[item.placeId] = len(result)
            result.append(item)
            continue
        index = positions[item.placeId]
        current = result[index]
        result[index] = current.model_copy(update={
            "matchedConcepts": list(dict.fromkeys(
                [*current.matchedConcepts, *item.matchedConcepts]
            )),
            "matchedFoodPreferences": list(dict.fromkeys(
                [*current.matchedFoodPreferences, *item.matchedFoodPreferences]
            )),
        })
    return result


def _candidate_debug(candidates: list[PlaceCandidate]) -> list[dict[str, object]]:
    return [{"placeId": item.placeId, "name": item.name, "isFood": item.isFood,
             "matchedConcepts": item.matchedConcepts,
             "matchedFoodPreferences": item.matchedFoodPreferences}
            for item in candidates[:40]]


def _plan_debug(plan: _RoutePlan) -> dict[str, object]:
    return {"planId": plan.plan_id, "relaxation": plan.relaxation,
            "areaRelaxed": plan.area_relaxed,
            "estimatedMinutes": plan.estimated_minutes,
            "score": round(plan.score, 2), "scoreBreakdown": plan.score_breakdown,
            "pointIds": [item.placeId for item in plan.candidates]}


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
                     direction_target: tuple[float, float] | None,
                     soft_scale: float = 1.0) -> list[PlaceCandidate]:
    """Use a nearest-neighbour shortlist; published legs are still verified by 2GIS Routing."""
    sights = _preference_order(
        [candidate for candidate in candidates if not candidate.isFood], start,
        direction_target, preview, soft_scale,
    )
    food = _preference_order(
        [candidate for candidate in candidates if candidate.isFood], start,
        direction_target, preview, soft_scale,
    )
    return _insert_food(sights, food, preview)


def _insert_food(sights: list[PlaceCandidate], food: list[PlaceCandidate],
                 preview: QueryPreview) -> list[PlaceCandidate]:
    if not preview.includeFood or not food:
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
                      preview: QueryPreview,
                      soft_scale: float = 1.0) -> list[PlaceCandidate]:
    remaining, ordered, current = list(candidates), [], start
    while remaining:
        candidate = min(remaining, key=lambda item: _candidate_score(
            current, item, direction_target, preview, soft_scale,
        ))
        remaining.remove(candidate)
        ordered.append(candidate)
        current = candidate.lat, candidate.lon
    return ordered


def _candidate_score(current: tuple[float, float], candidate: PlaceCandidate,
                     direction_target: tuple[float, float] | None,
                     preview: QueryPreview, soft_scale: float = 1.0) -> float:
    coordinates = candidate.lat, candidate.lon
    leg = _approx_distance_meters(current, coordinates)
    compactness_weight = {"LOW": 0.7, "NORMAL": 1.0, "HIGH": 1.8}[preview.compactness]
    score = leg * (1 + (compactness_weight - 1) * soft_scale)
    hard_interest_value = sum(
        {"LOW": 1, "MEDIUM": 2, "HIGH": 3}[
            preview.interestPriorities.get(concept, "MEDIUM")
        ]
        for concept in preview.hardInterests
        if candidate_matches_concept(candidate, concept)
    )
    soft_interest_value = max(0, _candidate_interest_value(candidate, preview)
                              - hard_interest_value)
    score -= hard_interest_value * 900 + soft_interest_value * 650 * soft_scale
    if preview.preferredWalkingMinutes is not None:
        preferred_distance = preview.preferredWalkingMinutes * 80
        score += max(0.0, leg - preferred_distance) * 1.5 * soft_scale
    for excluded in preview.softExclusions:
        if candidate_matches_concept(candidate, excluded):
            score += 10_000 * soft_scale
    if direction_target is None:
        return score
    current_to_target = _approx_distance_meters(current, direction_target)
    candidate_to_target = _approx_distance_meters(coordinates, direction_target)
    # Moving away from the requested direction is expensive; moving toward it is rewarded
    # modestly so «short transitions» still wins over a single long jump to the target.
    regression = max(0.0, candidate_to_target - current_to_target)
    progress = max(0.0, current_to_target - candidate_to_target)
    return score + regression * 2.5 - progress * 0.25


def _candidate_interest_value(candidate: PlaceCandidate, preview: QueryPreview) -> int:
    weights = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
    return sum(
        weights[preview.interestPriorities.get(concept, "MEDIUM")]
        for concept in preview.interests
        if candidate_matches_concept(candidate, concept)
    )


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


def _good_quality_score() -> float:
    try:
        value = float(os.getenv("ROUTE_GOOD_QUALITY_SCORE", "70"))
    except ValueError:
        return 70.0
    return max(50.0, min(95.0, value))


def _max_routing_checks() -> int:
    try:
        value = int(os.getenv("ROUTE_MAX_ROUTING_CHECKS", "8"))
    except ValueError:
        return 8
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

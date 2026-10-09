from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .catalog import CatalogPlaceProvider
from .geo import (GeoConstraintNotFound, GeoProvider, GeoRouteNotFound, GeoUnavailable,
                  candidate_matches_concept, candidate_matches_food)
from .models import (CreateRoute, PlaceCandidate, QueryPreview, Route, RouteLeg,
                     RoutePoint, SearchArea)
from .planning_debug import catalog_debug_log, planning_log
from .route_config import CITY_NO_GEO_START_OVERRIDES
from .visit_categories import (minimum_visit_minutes,
                               visit_minutes as visit_duration_minutes)


class RouteNotFound(Exception):
    pass


class TimeBudgetExceeded(Exception):
    def __init__(self, minimum_minutes: int | None = None):
        self.minimum_minutes = minimum_minutes


class DurationConfirmationRequired(Exception):
    """An explicitly requested duration needs a user decision after an edit."""

    def __init__(self, requested_minutes: int, projected_minutes: int,
                 duration_mode: str):
        self.requested_minutes = requested_minutes
        self.projected_minutes = projected_minutes
        self.overrun_minutes = projected_minutes - requested_minutes
        self.duration_mode = duration_mode


class _RoutingBudgetExhausted(Exception):
    pass


class _TransientRouteUnavailable(Exception):
    """One upstream routing leg failed, while other legs may still work."""
    pass


_LegKey = tuple[tuple[float, float], tuple[float, float]]


@dataclass
class _RoutingChecks:
    """Share directed legs, including no-route results, within one build."""
    remaining: int
    legs: dict[_LegKey, RouteLeg | None] = field(default_factory=dict)
    transient_legs: set[_LegKey] = field(default_factory=set)
    transient_failures: int = 0

    def walking_leg(self, geo: GeoProvider, start: tuple[float, float],
                    end: tuple[float, float], from_order: int,
                    reserve: int = 0) -> RouteLeg:
        key = (start, end)
        if key in self.transient_legs:
            raise _TransientRouteUnavailable()
        if key not in self.legs:
            if self.remaining <= reserve:
                raise _RoutingBudgetExhausted()
            self.remaining -= 1
            try:
                self.legs[key] = geo.walking_leg(start, end, from_order, from_order + 1)
            except GeoRouteNotFound:
                self.legs[key] = None
            except GeoUnavailable:
                # Do not fabricate a straight-line leg. Skip just this transition and
                # allow the planner to try another catalog point/route variant.
                self.transient_legs.add(key)
                self.transient_failures += 1
                raise _TransientRouteUnavailable()
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
                now: datetime | None = None, trace_id: str | None = None,
                catalog: CatalogPlaceProvider | None = None) -> Route:
    location_hint = preview.locationHint or ("центр" if preview.centerOnly else None)
    catalog_first = bool(catalog and catalog.has_sufficient_resolved(payload.cityId))
    catalog_available = bool(catalog and catalog.has_city(payload.cityId))
    local_start = (payload.startLocation.lat, payload.startLocation.lon) if payload.startLocation else \
        CITY_NO_GEO_START_OVERRIDES.get(payload.cityId)
    can_skip_places = bool(
        catalog_first and local_start and not location_hint and not preview.startLocationHint
        and not preview.directionHint and preview.foodMode == "NONE"
    )
    if can_skip_places:
        city_center = local_start
        search_area = SearchArea(label="Рядом с геопозицией" if payload.startLocation else "Старт маршрута",
                                 lat=local_start[0], lon=local_start[1], radiusMeters=6500,
                                 source="geo")
    else:
        city_center = geo.resolve_city_center(payload.cityId)
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
        if not location_hint:
            # A device position is both the route start and the discovery anchor.
            # Keeping the city centre here makes nearby places lose to popular
            # downtown results even though the first walking leg starts at GPS.
            search_area = search_area.model_copy(update={
                "label": "Рядом с геопозицией",
                "lat": start[0],
                "lon": start[1],
                "radiusMeters": 6500,
                "source": "geo",
            })
    else:
        start = CITY_NO_GEO_START_OVERRIDES.get(payload.cityId, city_center)
        approximate_start = True
        start_source = ("CITY_NO_GEO_OVERRIDE" if payload.cityId in CITY_NO_GEO_START_OVERRIDES
                        else "CITY_CENTER")

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
    terminal_best: _BuiltPlan | None = None
    terminal_area = search_area
    # A city record alone is not enough to lock planning into an almost-empty
    # local catalogue. Ready cities stay catalogue-first; incomplete catalogues
    # retain their resolved local points and are augmented by the provider.
    if catalog_available and catalog is not None:
        ranked_rows, ranking = catalog.rank_candidates(payload.cityId, preview, search_area)
        catalog_debug_log(
            trace_id, "intent", city=payload.cityId,
            requested_tags={concept: preview.interestPriorities.get(concept, "MEDIUM")
                            for concept in preview.interests},
            # Interests are preferences. Only exclusions and technical filters are hard.
            required_tags=[],
            exclusions={"concepts": preview.hardExclusions,
                        "types": preview.excludedPlaceTypes},
            duration=target_minutes, pace=preview.routePace,
            start_source=start_source,
        )
        catalog_debug_log(trace_id, "after_hard_filters", candidates=len(ranked_rows))
        catalog_debug_log(trace_id, "ranking", candidates=ranking)
        catalog_debug_log(trace_id, "shortlist",
                          candidates=[{"id": row.id, "name": row.name}
                                      for row in ranked_rows[:40]])
    candidates = _retrieve_candidates(
        payload.cityId, preview, search_area, geo, catalog, catalog_first,
    )
    planning_log(trace_id, "catalog_candidates" if catalog_first else "dgis_candidates",
                 attempt=1, area=search_area.label,
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
            # Verify only the provider-backed points that actually appear in a
            # small tentative shortlist. This is metadata enrichment, never a
            # second Places discovery/ranking pass.
            active_candidates = _verify_tentative_schedules(active_candidates, plans, geo)
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
            planner_only = {"MINIMUM_TWO_POINTS", "REQUESTED_PLACE_COUNT"}
            blocking_violations = [item for item in built.hard_violations
                                   if item not in planner_only]
            if blocking_violations:
                planning_log(trace_id, "route_variant_rejected", planId=plan.plan_id,
                             hardViolations=blocking_violations,
                             points=[point.name for point in built.points])
                continue
            built.score, built.score_breakdown = _route_quality(built, preview)
            built.unmet = _unmet_preferences(built, preview)
            if built.hard_violations:
                # Keep a real, hard-valid route as the last resort, but do not
                # let it compete with ordinary multi-point variants.
                if terminal_best is None or built.score > terminal_best.score:
                    terminal_best = built
                    terminal_area = active_area
                planning_log(trace_id, "route_variant_deferred", planId=plan.plan_id,
                             reason="TERMINAL_DEGRADED_FALLBACK",
                             points=[point.name for point in built.points])
                continue
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
            wider = _retrieve_candidates(
                payload.cityId, preview, city_area, geo, catalog, catalog_first,
            )
            merged = _merge_candidates(active_candidates, wider)
            planning_log(trace_id, "catalog_candidates" if catalog_first else "dgis_candidates",
                         attempt=2, area=city_area.label,
                         reason="SOFT_AREA_RELAXED", count=len(merged),
                         candidates=_candidate_debug(merged))
            search_rounds.append((city_area, merged, 1))

    terminal_fallback = False
    if best is None and terminal_best is not None:
        best = terminal_best
        best_area = terminal_area
        terminal_fallback = True

    if best is None:
        if routing_budget.transient_failures:
            planning_log(trace_id, "planner_result", planner_status="PROVIDER_UNAVAILABLE",
                         relaxation_level=3, candidate_count=len(candidates))
            raise GeoUnavailable("2GIS routing temporarily unavailable for all route variants")
        planning_log(trace_id, "planner_result", planner_status="NO_CANDIDATES",
                     relaxation_level=3, candidate_count=len(candidates))
        planning_log(trace_id, "planning_failed", reason="NO_HARD_VALID_ROUTE",
                     routingChecksUsed=_max_routing_checks() - routing_budget.remaining)
        raise RouteNotFound()

    route_points, legs = best.points, best.legs
    total_minutes = math.ceil(best.elapsed_seconds / 60)
    unused_minutes = max(0, target_minutes - total_minutes)
    utilization = total_minutes / target_minutes
    unmet = best.unmet
    planning_status = "DEGRADED" if unmet else "SUCCESS"
    relaxation_level = max(
        best.plan.relaxation,
        max((item.catalogRelaxationLevel or 0) for item in best.candidates),
    )
    planner_result = "RELAXED_SUCCESS" if relaxation_level or unmet else "SUCCESS"

    warnings = [*preview.warnings,
                "Время посещения оценено по типу места и темпу прогулки"]
    if terminal_fallback:
        warnings.append("Only one reachable place matched the hard constraints")
    if catalog_first:
        warnings.append("Достопримечательности подобраны из локального каталога")
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
        fallback_label = ("заданной точки города" if start_source == "CITY_NO_GEO_OVERRIDE"
                          else "центра города")
        warnings.append(f"Геопозиция и старт в тексте не указаны — маршрут начат от {fallback_label}")
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
        planner_status=planner_result, relaxation_level=relaxation_level,
        candidate_count=len(candidates),
    )
    if catalog_first:
        covered_concepts = _covered_concepts(best.candidates, preview)
        catalog_debug_log(
            trace_id, "planner",
            selected=[point.name for point in route_points],
            rejected=best.hard_violations,
            relaxation_level=max((item.catalogRelaxationLevel or 0)
                                 for item in best.candidates),
            requested_concepts=list(preview.interests),
            covered_concepts=covered_concepts,
            uncovered_concepts=[concept for concept in preview.interests
                                if concept not in covered_concepts],
            duration_target=target_minutes,
            duration_actual=total_minutes,
            hard_constraints={
                "excluded_concepts": list(preview.hardExclusions),
                "excluded_types": list(preview.excludedPlaceTypes),
                "food_required": preview.foodMode == "REQUIRED",
                "max_duration": preview.maxDurationMinutes,
            },
        )
        catalog_debug_log(
            trace_id, "routing",
            legs=[{
                "from": route_points[index - 1].name if index else "start",
                "to": point.name,
                "walking_minutes": math.ceil(legs[index].durationSeconds / 60),
            } for index, point in enumerate(route_points)],
        )
        catalog_debug_log(
            trace_id, "final", visit_minutes=sum(point.visitMinutes for point in route_points),
            walking_minutes=math.ceil(best.walking_seconds / 60), total_minutes=total_minutes,
        )
    return Route(
        routeId=uuid4(), routeVersion=1, status="READY", cityId=payload.cityId,
        query=payload.query, filters=payload.filters, searchArea=best_area,
        approximateStart=approximate_start, startLat=start[0], startLon=start[1],
        startSource=start_source, maxWalkingMinutes=preview.maxWalkingMinutes,
        planningStatus=planning_status, durationUtilization=round(utilization, 3),
        planningScore=round(best.score, 2), planningAttempts=max(1, attempts),
        unmetPreferences=unmet, requestedMinutes=target_minutes,
        durationSource=preview.durationSource, durationMode=preview.durationMode,
        maxDurationMinutes=preview.maxDurationMinutes, routePace=preview.routePace,
        totalMinutes=total_minutes, unusedMinutes=unused_minutes,
        points=route_points, legs=legs, warnings=warnings,
    )


def _retrieve_candidates(city_id: str, preview: QueryPreview, area: SearchArea,
                         geo: GeoProvider, catalog: CatalogPlaceProvider | None,
                         catalog_first: bool) -> list[PlaceCandidate]:
    if catalog is None or not catalog.has_city(city_id):
        return geo.search_places(city_id, preview, area)
    sights = catalog.list_candidates(city_id, preview, area)
    if not catalog_first:
        # Do not discard the local data merely because the catalogue is too
        # small to be trusted as the sole source.
        return _merge_candidates(sights, geo.search_places(city_id, preview, area))
    food_search = getattr(geo, "search_food_places", None)
    food = food_search(city_id, preview, area) if callable(food_search) else []
    return [*sights, *food]


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
    budget_seconds = _duration_budget_minutes(preview) * 60
    max_points = preview.requestedPlaceCount or 8
    for candidate in candidates:
        if len(selected) >= max_points:
            break
        if _catalog_parent_conflict(selected, candidate):
            continue
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
        visit_seconds = visit_duration_minutes(candidate, preview.routePace) * 60
        if elapsed + leg_seconds + visit_seconds > budget_seconds:
            visit_seconds = minimum_visit_minutes(candidate) * 60
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
    budget_seconds = _duration_budget_minutes(preview) * 60
    for candidate in plan.candidates:
        if len(built.points) >= (preview.requestedPlaceCount or 8):
            break
        if _catalog_parent_conflict(built.candidates, candidate):
            continue
        distance = _approx_distance_meters(current, (candidate.lat, candidate.lon))
        if (preview.maxWalkingMinutes is not None
                and distance > preview.maxWalkingMinutes * 130):
            continue
        if (preview.maxWalkingDistanceMeters is not None
                and distance > preview.maxWalkingDistanceMeters):
            continue
        dwell_minutes = visit_duration_minutes(candidate, preview.routePace)
        if built.elapsed_seconds + dwell_minutes * 60 > budget_seconds:
            dwell_minutes = minimum_visit_minutes(candidate)
            if built.elapsed_seconds + dwell_minutes * 60 > budget_seconds:
                continue
        try:
            leg = routing_budget.walking_leg(
                geo, current, (candidate.lat, candidate.lon), len(built.points), reserve,
            )
        except _RoutingBudgetExhausted:
            built.budget_limited = True
            break
        except _TransientRouteUnavailable:
            continue
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
        projected = built.elapsed_seconds + leg.durationSeconds + dwell_minutes * 60
        if projected > budget_seconds:
            continue
        arrival = local_now + timedelta(seconds=built.elapsed_seconds + leg.durationSeconds)
        schedule_status = schedule_status_at(candidate.schedule, arrival, dwell_minutes)
        if schedule_status == "CLOSED":
            continue
        built.points.append(RoutePoint(
            order=len(built.points) + 1, placeId=candidate.placeId, name=candidate.name,
            lat=candidate.lat, lon=candidate.lon, visitMinutes=dwell_minutes,
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
    if (preview.requestedPlaceCount is not None
            and len(route.points) != preview.requestedPlaceCount):
        unmet.append("POINT_COUNT")
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
        # Duration is deliberately soft: a good 65–80% route is preferable to NO_ROUTE.
        ratio = total_minutes / max(1, target)
        if 0.80 <= ratio <= 1.0:
            # Preferred range, with a gentle preference for using more of the time.
            duration_score = 90.0 + (ratio - 0.80) / 0.20 * 10.0
        elif 1.0 < ratio <= 1.15:
            duration_score = 100.0 - (ratio - 1.0) / 0.15 * 5.0
        elif 0.65 <= ratio < 0.80:
            duration_score = 70.0 + (ratio - 0.65) / 0.15 * 30.0
        elif ratio < 0.65:
            duration_score = max(0.0, ratio / 0.65 * 70.0)
        else:
            duration_score = max(0.0, 100.0 - (ratio - 1.15) / 0.25 * 100.0)
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
        updates = {
            "matchedConcepts": list(dict.fromkeys(
                [*current.matchedConcepts, *item.matchedConcepts]
            )),
            "matchedFoodPreferences": list(dict.fromkeys(
                [*current.matchedFoodPreferences, *item.matchedFoodPreferences]
            )),
        }
        # Preserve local catalog relevance when the same provider object also
        # arrives from a fallback Places search.
        for field_name in ("catalogId", "catalogLevel", "catalogParentId", "catalogRelation",
                           "catalogType", "catalogAccessCost", "catalogPriceFromRub",
                           "catalogPriceToRub", "catalogVisitMin", "catalogVisitMax",
                           "catalogRelaxationLevel", "catalogSemanticScore",
                           "catalogFinalScore", "catalogLexicalScore"):
            if getattr(current, field_name) is None and getattr(item, field_name) is not None:
                updates[field_name] = getattr(item, field_name)
        if not current.schedule and item.schedule:
            updates["schedule"] = item.schedule
        result[index] = current.model_copy(update=updates)
    return result


def _verify_tentative_schedules(candidates: list[PlaceCandidate], plans: list[_RoutePlan],
                                geo: GeoProvider) -> list[PlaceCandidate]:
    lookup = getattr(geo, "lookup_schedules", None)
    if not callable(lookup) or not plans:
        return candidates
    ids: list[str] = []
    for plan in plans[:2]:
        for candidate in plan.candidates:
            if (candidate.catalogId is not None and not candidate.placeId.startswith("catalog:")
                    and candidate.placeId not in ids):
                ids.append(candidate.placeId)
            if len(ids) >= 10:
                break
        if len(ids) >= 10:
            break
    if not ids:
        return candidates
    try:
        schedules = lookup(ids)
    except Exception:
        # Schedule metadata is optional. Routing remains sufficient for a
        # viable catalog route and UNKNOWN is an intentional state.
        return candidates
    if not isinstance(schedules, dict):
        return candidates
    return [candidate.model_copy(update={"schedule": schedules[candidate.placeId]})
            if candidate.placeId in schedules and isinstance(schedules[candidate.placeId], dict)
            else candidate for candidate in candidates]


def _catalog_parent_conflict(selected: list[PlaceCandidate],
                             candidate: PlaceCandidate) -> bool:
    """Prevent a COMPLEX and its CONTAINS child from becoming two visits."""
    if candidate.catalogId is None:
        return False
    if candidate.catalogLevel == "COMPLEX":
        return any(
            item.catalogParentId == candidate.catalogId
            and item.catalogRelation == "CONTAINS"
            for item in selected
        )
    if candidate.catalogRelation == "CONTAINS" and candidate.catalogParentId:
        return any(
            item.catalogId == candidate.catalogParentId
            and item.catalogLevel == "COMPLEX"
            for item in selected
        )
    return False


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
                              now: datetime | None = None,
                              allow_duration_overrun: bool = False) -> Route:
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
        visit_minutes = old.visitMinutes if old else visit_duration_minutes(candidate, source.routePace)
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
    explicitly_requested_duration = source.durationSource != "default"
    # A duration override belongs to this route revision chain.  Once the
    # user explicitly accepted an overrun, later point edits must not ask the
    # same question again.  Fresh routes start with the model default (False),
    # so an override can never leak into a newly planned route.
    duration_overrun_accepted = (
        source.durationOverrunAccepted or allow_duration_overrun
    )
    if (explicitly_requested_duration and total_minutes > source.requestedMinutes
            and not duration_overrun_accepted):
        raise DurationConfirmationRequired(source.requestedMinutes, total_minutes,
                                           source.durationMode)
    unused_minutes = max(0, source.requestedMinutes - total_minutes)
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
    overrun_accepted = (explicitly_requested_duration
                         and total_minutes > source.requestedMinutes)
    unmet = [item for item in source.unmetPreferences if item != "DURATION_TARGET"]
    if utilization < _good_duration_utilization():
        unmet.append("DURATION_TARGET")
    if overrun_accepted:
        unmet.append("DURATION_TARGET")
        warnings.append(
            f"Длительность после ручного редактирования превышает исходную на "
            f"{total_minutes - source.requestedMinutes} мин.; пользователь подтвердил изменение"
        )
    retained = [warning for warning in source.warnings
                if warning.startswith(retained_prefixes)]
    warnings = retained + [warning for warning in warnings if warning not in retained]
    return source.model_copy(update={
        "points": route_points, "legs": legs, "totalMinutes": total_minutes,
        "unusedMinutes": unused_minutes, "warnings": warnings,
        "durationUtilization": round(utilization, 3),
        "planningStatus": "DEGRADED" if unmet else "SUCCESS",
        "unmetPreferences": list(dict.fromkeys(unmet)),
        "durationOverrunAccepted": duration_overrun_accepted,
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
    concept_counts: dict[str, int] = {}
    while remaining:
        candidate = min(remaining, key=lambda item: _candidate_score(
            current, item, direction_target, preview, soft_scale, concept_counts,
        ))
        remaining.remove(candidate)
        ordered.append(candidate)
        for concept in preview.interests:
            if candidate_matches_concept(candidate, concept):
                concept_counts[concept] = concept_counts.get(concept, 0) + 1
        current = candidate.lat, candidate.lon
    return ordered


def _candidate_score(current: tuple[float, float], candidate: PlaceCandidate,
                     direction_target: tuple[float, float] | None,
                     preview: QueryPreview, soft_scale: float = 1.0,
                     concept_counts: dict[str, int] | None = None) -> float:
    coordinates = candidate.lat, candidate.lon
    leg = _approx_distance_meters(current, coordinates)
    compactness_weight = {"LOW": 0.7, "NORMAL": 1.0, "HIGH": 1.8}[preview.compactness]
    score = leg * (1 + (compactness_weight - 1) * soft_scale)
    # First coverage of a requested theme is far more valuable than repetition.
    counts = concept_counts or {}
    weights = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
    coverage_bonus = 0.0
    for concept in preview.interests:
        if not candidate_matches_concept(candidate, concept):
            continue
        weight = weights[preview.interestPriorities.get(concept, "MEDIUM")]
        occurrences = counts.get(concept, 0)
        coverage_bonus += weight * (1_400 if occurrences == 0 else 260 / occurrences)
    score -= coverage_bonus * soft_scale
    if candidate.catalogRelaxationLevel is not None:
        score += candidate.catalogRelaxationLevel * 225 * soft_scale
    # Catalog score is already the authoritative semantic/geo/variety ranking.
    # Use it as a stable bias, while route cost and theme-coverage still decide
    # the actual walking sequence.
    if candidate.catalogFinalScore is not None:
        score -= candidate.catalogFinalScore * 850 * soft_scale
    if candidate.catalogLexicalScore:
        score -= candidate.catalogLexicalScore * 500 * soft_scale
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


def _covered_concepts(candidates: list[PlaceCandidate], preview: QueryPreview) -> list[str]:
    return [concept for concept in preview.interests
            if any(candidate_matches_concept(candidate, concept) for candidate in candidates)]




def _good_duration_utilization() -> float:
    try:
        value = float(os.getenv("ROUTE_GOOD_DURATION_UTILIZATION", "0.80"))
    except ValueError:
        return 0.80
    return max(0.65, min(1.0, value))


def _duration_budget_minutes(preview: QueryPreview) -> int:
    """Keep an explicit maximum hard, otherwise allow a small useful overrun."""
    if preview.maxDurationMinutes is not None:
        return preview.maxDurationMinutes
    target = preview.targetDurationMinutes or preview.durationMinutes
    return math.ceil(target * 1.15)


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

"""Opt-in construction of one logical stop with catalog child waypoints."""
from __future__ import annotations

import math

from .catalog import CatalogPlaceProvider
from .geo import GeoProvider, GeoRouteNotFound
from .models import (PlaceCandidate, QueryPreview, Route, RouteGroup, RouteLeg,
                     RouteWaypoint, RouteWaypointLeg, RouteZoneGeometry)
from .visit_zones import VisitZone, VisitZones


def logical_group_candidates(candidates: list[PlaceCandidate], preview: QueryPreview,
                             catalog: CatalogPlaceProvider,
                             zones: VisitZones) -> list[PlaceCandidate]:
    """Collapse selectable children under their eligible logical parent."""
    eligible_parents = {
        item.catalogId for item in candidates
        if item.catalogId and zones.get(item.catalogId) is not None
        and catalog.group_waypoint_candidates(item.catalogId, preview)
    }
    return [
        item for item in candidates
        if not (item.catalogParentId in eligible_parents
                and item.catalogRelation in {"CONTAINS", "CLUSTER_MEMBER"})
    ]


def attach_route_groups(route: Route, candidates: list[PlaceCandidate],
                        preview: QueryPreview, geo: GeoProvider,
                        catalog: CatalogPlaceProvider,
                        zones: VisitZones) -> Route:
    """Add verified child navigation while retaining logical Route.points."""
    logical_catalog_ids = {item.catalogId for item in candidates if item.catalogId}
    children_by_order: dict[int, list[PlaceCandidate]] = {}
    zone_by_order: dict[int, VisitZone] = {}
    for point, candidate in zip(route.points, candidates):
        if not candidate.catalogId:
            continue
        zone = zones.get(candidate.catalogId)
        if zone is None:
            continue
        children = [
            item for item in catalog.group_waypoint_candidates(candidate.catalogId, preview)
            if item.catalogId not in logical_catalog_ids
        ]
        if children:
            children_by_order[point.order] = children
            zone_by_order[point.order] = zone
    if not children_by_order:
        return route.model_copy(update={"routeGroupsEnabled": True, "routeGroups": []})

    external_legs: list[RouteLeg] = []
    groups: list[RouteGroup] = []
    internal_seconds = 0
    internal_distance = 0
    path_modified = False
    current = _route_start(route)
    for index, point in enumerate(route.points):
        if path_modified:
            try:
                external = geo.walking_leg(current, (point.lat, point.lon), index, index + 1)
            except GeoRouteNotFound:
                return route.model_copy(update={
                    "routeGroupsEnabled": True, "routeGroups": [],
                })
        else:
            external = route.legs[index]
        external_legs.append(external.model_copy(update={
            "fromOrder": index, "toOrder": index + 1,
        }))
        current = point.lat, point.lon

        waypoints: list[RouteWaypoint] = []
        waypoint_legs: list[RouteWaypointLeg] = []
        for child in children_by_order.get(point.order, []):
            if child.catalogId is None or child.catalogRelation is None:
                continue
            try:
                leg = geo.walking_leg(
                    current, (child.lat, child.lon),
                    len(waypoints), len(waypoints) + 1,
                )
            except GeoRouteNotFound:
                continue
            if (preview.maxWalkingMinutes is not None
                    and math.ceil(leg.durationSeconds / 60) > preview.maxWalkingMinutes):
                continue
            if (preview.maxWalkingDistanceMeters is not None
                    and leg.distanceMeters > preview.maxWalkingDistanceMeters):
                continue
            waypoint_order = len(waypoints) + 1
            waypoints.append(RouteWaypoint(
                order=waypoint_order, catalogId=child.catalogId,
                placeId=child.placeId, name=child.name,
                lat=child.lat, lon=child.lon, relation=child.catalogRelation,
            ))
            waypoint_legs.append(RouteWaypointLeg(
                fromWaypointOrder=waypoint_order - 1,
                toWaypointOrder=waypoint_order,
                distanceMeters=leg.distanceMeters,
                durationSeconds=leg.durationSeconds,
                geometry=leg.geometry,
            ))
            internal_seconds += leg.durationSeconds
            internal_distance += leg.distanceMeters
            current = child.lat, child.lon
        if waypoints:
            path_modified = True
            groups.append(RouteGroup(
                pointOrder=point.order, catalogId=point.catalogId or "",
                waypoints=waypoints, waypointLegs=waypoint_legs,
                visitZone=RouteZoneGeometry.model_validate(
                    zone_by_order[point.order].geometry,
                ),
            ))

    if not groups:
        return route.model_copy(update={"routeGroupsEnabled": True, "routeGroups": []})
    walking_seconds = sum(item.durationSeconds for item in external_legs) + internal_seconds
    walking_distance = sum(item.distanceMeters for item in external_legs) + internal_distance
    if (preview.maxTotalWalkingMinutes is not None
            and math.ceil(walking_seconds / 60) > preview.maxTotalWalkingMinutes):
        return route.model_copy(update={"routeGroupsEnabled": True, "routeGroups": []})
    if (preview.maxTotalWalkingDistanceMeters is not None
            and walking_distance > preview.maxTotalWalkingDistanceMeters):
        return route.model_copy(update={"routeGroupsEnabled": True, "routeGroups": []})
    total_minutes = math.ceil((
        walking_seconds + sum(point.visitMinutes * 60 for point in route.points)
    ) / 60)
    budget = (preview.maxDurationMinutes or preview.targetDurationMinutes
              or preview.durationMinutes)
    if total_minutes > budget:
        return route.model_copy(update={"routeGroupsEnabled": True, "routeGroups": []})
    warnings = [*route.warnings, "Маршрутные группы включены в тестовом backend-режиме"]
    return route.model_copy(update={
        "routeGroupsEnabled": True,
        "routeGroups": groups,
        "legs": external_legs,
        "totalMinutes": total_minutes,
        "unusedMinutes": max(0, route.requestedMinutes - total_minutes),
        "durationUtilization": round(total_minutes / route.requestedMinutes, 3),
        "warnings": warnings,
    })


def _route_start(route: Route) -> tuple[float, float]:
    if route.startLat is not None and route.startLon is not None:
        return route.startLat, route.startLon
    if route.legs and route.legs[0].geometry:
        lon, lat = route.legs[0].geometry[0]
        return lat, lon
    return route.searchArea.lat, route.searchArea.lon

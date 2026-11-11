"""Opt-in free-roam groups for one logical catalog stop."""
from __future__ import annotations

from .catalog import CatalogPlaceProvider
from .geo import GeoProvider
from .models import (PlaceCandidate, QueryPreview, Route, RouteChild, RouteGroup,
                     RouteZoneGeometry)
from .visit_zones import VisitZones


def logical_group_candidates(candidates: list[PlaceCandidate], preview: QueryPreview,
                             catalog: CatalogPlaceProvider,
                             zones: VisitZones) -> list[PlaceCandidate]:
    """Collapse selected children whenever their logical parent is available."""
    del preview, zones
    eligible_parents = {
        item.catalogId for item in candidates
        if item.catalogId and catalog.group_children(item.catalogId)
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
    """Attach complete child catalogs without changing route geometry or budget."""
    del preview, geo
    groups: list[RouteGroup] = []
    for point, candidate in zip(route.points, candidates):
        if not candidate.catalogId:
            continue
        rows = catalog.group_children(candidate.catalogId)
        if not rows:
            continue
        children = [RouteChild(
            catalogId=row.id,
            placeId=row.dgis_place_id,
            name=row.name,
            lat=row.lat,
            lon=row.lon,
            relation=row.relation,
        ) for row in rows]
        zone = zones.get(candidate.catalogId)
        groups.append(RouteGroup(
            pointOrder=point.order,
            catalogId=candidate.catalogId,
            children=children,
            visitZone=(RouteZoneGeometry.model_validate(zone.geometry)
                       if zone is not None else None),
        ))
    return route.model_copy(update={
        "routeGroupsEnabled": True,
        "routeGroups": groups,
    })

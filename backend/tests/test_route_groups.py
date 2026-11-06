from uuid import uuid4

from gulyay.geo import GeoRouteNotFound
from gulyay.models import (Filters, PlaceCandidate, QueryPreview, Route, RouteLeg,
                           RoutePoint, SearchArea)
from gulyay.route_groups import attach_route_groups, logical_group_candidates
from gulyay.visit_zones import VisitZone, VisitZones


class GroupCatalog:
    def __init__(self, children):
        self.children = children

    def group_waypoint_candidates(self, parent_id, preview):
        return self.children


class GroupGeo:
    def __init__(self, duration=60):
        self.calls = []
        self.duration = duration

    def walking_leg(self, start, end, from_order, to_order):
        self.calls.append((start, end))
        return RouteLeg(
            fromOrder=from_order, toOrder=to_order,
            distanceMeters=100, durationSeconds=self.duration,
            geometry=[[start[1], start[0]], [end[1], end[0]]],
        )


def preview(**updates):
    values = dict(
        cityId="moscow", durationMinutes=180, durationSource="text",
        interests=[], includeFood=False, withChildren=False,
        unusualPlaces=False, centerOnly=False, allowSinglePlace=True, warnings=[],
    )
    values.update(updates)
    return QueryPreview.model_validate(values)


def parent_route():
    return Route(
        routeId=uuid4(), routeVersion=1, status="READY", cityId="moscow",
        query="walk", filters=Filters(),
        searchArea=SearchArea(label="center", lat=55.75, lon=37.61,
                              radiusMeters=3500, source="city"),
        approximateStart=False, startLat=55.749, startLon=37.609,
        requestedMinutes=180, totalMinutes=41, unusedMinutes=139,
        points=[RoutePoint(
            order=1, placeId="catalog:msk001", catalogId="msk001",
            name="Parent", lat=55.75, lon=37.61, visitMinutes=40,
            scheduleStatus="OPEN", isFood=False,
        )],
        legs=[RouteLeg(
            fromOrder=0, toOrder=1, distanceMeters=100, durationSeconds=60,
            geometry=[[37.609, 55.749], [37.61, 55.75]],
        )], warnings=[],
    )


def child(catalog_id, relation, lat, lon):
    return PlaceCandidate(
        placeId=f"catalog:{catalog_id}", catalogId=catalog_id,
        catalogParentId="msk001", catalogRelation=relation,
        catalogLevel="POI", name=catalog_id, lat=lat, lon=lon,
        rubrics=[], schedule={}, isFood=False,
    )


def zones():
    geometry = {"type": "Polygon", "coordinates": [[
        [37.60, 55.74], [37.62, 55.74], [37.62, 55.76],
        [37.60, 55.76], [37.60, 55.74],
    ]]}
    return VisitZones({"msk001": VisitZone("msk001", geometry)})


def test_group_keeps_one_logical_stop_and_routes_both_relation_types():
    route = parent_route()
    candidates = [child("msk002", "CONTAINS", 55.751, 37.611),
                  child("msk003", "CLUSTER_MEMBER", 55.752, 37.612)]
    geo = GroupGeo()

    grouped = attach_route_groups(
        route,
        [PlaceCandidate(placeId="catalog:msk001", catalogId="msk001",
                        catalogLevel="AREA", name="Parent", lat=55.75,
                        lon=37.61, rubrics=[], schedule={}, isFood=False)],
        preview(), geo, GroupCatalog(candidates), zones(),
    )

    assert len(grouped.points) == 1
    assert grouped.routeGroupsEnabled is True
    assert [item.relation for item in grouped.routeGroups[0].waypoints] == [
        "CONTAINS", "CLUSTER_MEMBER",
    ]
    assert len(grouped.routeGroups[0].waypointLegs) == 2
    assert len(geo.calls) == 2
    assert grouped.routeGroups[0].visitZone.type == "Polygon"


def test_group_mode_collapses_selected_children_into_one_parent_stop():
    parent = PlaceCandidate(
        placeId="catalog:msk001", catalogId="msk001", catalogLevel="AREA",
        name="Parent", lat=55.75, lon=37.61, rubrics=[], schedule={}, isFood=False,
    )
    children = [child("msk002", "CONTAINS", 55.751, 37.611),
                child("msk003", "CLUSTER_MEMBER", 55.752, 37.612)]
    collapsed = logical_group_candidates(
        [*children, parent], preview(), GroupCatalog(children), zones(),
    )
    assert [item.catalogId for item in collapsed] == ["msk001"]


def test_missing_parent_zone_falls_back_without_inventing_group():
    route = parent_route()
    grouped = attach_route_groups(
        route,
        [PlaceCandidate(placeId="catalog:msk001", catalogId="msk001",
                        catalogLevel="AREA", name="Parent", lat=55.75,
                        lon=37.61, rubrics=[], schedule={}, isFood=False)],
        preview(), GroupGeo(), GroupCatalog([
            child("msk002", "CONTAINS", 55.751, 37.611),
        ]), VisitZones({}),
    )
    assert grouped.routeGroupsEnabled is True
    assert grouped.routeGroups == []
    assert grouped.points == route.points


def test_child_leg_hard_limit_and_no_route_fall_back_without_fake_geometry():
    parent = PlaceCandidate(
        placeId="catalog:msk001", catalogId="msk001", catalogLevel="AREA",
        name="Parent", lat=55.75, lon=37.61, rubrics=[], schedule={}, isFood=False,
    )
    too_long = attach_route_groups(
        parent_route(), [parent], preview(maxWalkingMinutes=1),
        GroupGeo(duration=121), GroupCatalog([
            child("msk002", "CONTAINS", 55.751, 37.611),
        ]), zones(),
    )
    assert too_long.routeGroups == []

    class NoRouteGeo(GroupGeo):
        def walking_leg(self, start, end, from_order, to_order):
            raise GeoRouteNotFound()

    unavailable = attach_route_groups(
        parent_route(), [parent], preview(), NoRouteGeo(), GroupCatalog([
            child("msk002", "CONTAINS", 55.751, 37.611),
        ]), zones(),
    )
    assert unavailable.routeGroups == []
    assert unavailable.legs == parent_route().legs

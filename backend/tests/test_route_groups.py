from types import SimpleNamespace
from uuid import uuid4

from gulyay.catalog import (CatalogPlaceProvider, PlaceCatalog,
                            bundled_seed_path, bundled_seed_paths)
from gulyay.models import (Filters, PlaceCandidate, QueryPreview, Route, RouteLeg,
                           RoutePoint, SearchArea)
from gulyay.route_groups import (attach_route_groups, logical_group_candidates,
                                 refresh_route_groups)
from gulyay.visit_zones import VisitZone, VisitZones


class GroupCatalog:
    def __init__(self, children):
        self.children = children

    def group_children(self, parent_id):
        return self.children


class GroupGeo:
    def __init__(self):
        self.calls = []

    def walking_leg(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        raise AssertionError("free-roam groups must not request internal walking legs")


def preview(**updates):
    values = dict(
        cityId="moscow", durationMinutes=180, durationSource="text",
        interests=[], includeFood=False, withChildren=False,
        unusualPlaces=False, centerOnly=False, allowSinglePlace=True, warnings=[],
    )
    values.update(updates)
    return QueryPreview.model_validate(values)


def parent_route(catalog_id="msk001", city_id="moscow"):
    return Route(
        routeId=uuid4(), routeVersion=1, status="READY", cityId=city_id,
        query="walk", filters=Filters(),
        searchArea=SearchArea(label="center", lat=55.75, lon=37.61,
                              radiusMeters=3500, source="city"),
        approximateStart=False, startLat=55.749, startLon=37.609,
        requestedMinutes=180, totalMinutes=41, unusedMinutes=139,
        points=[RoutePoint(
            order=1, placeId=f"catalog:{catalog_id}", catalogId=catalog_id,
            name="Parent", lat=55.75, lon=37.61, visitMinutes=40,
            scheduleStatus="OPEN", isFood=False,
        )],
        legs=[RouteLeg(
            fromOrder=0, toOrder=1, distanceMeters=100, durationSeconds=60,
            geometry=[[37.609, 55.749], [37.61, 55.75]],
        )], warnings=[],
    )


def parent_candidate(catalog_id="msk001"):
    return PlaceCandidate(
        placeId=f"catalog:{catalog_id}", catalogId=catalog_id, catalogLevel="AREA",
        name="Parent", lat=55.75, lon=37.61, rubrics=[], schedule={}, isFood=False,
    )


def selected_child(catalog_id, relation, lat, lon):
    return PlaceCandidate(
        placeId=f"catalog:{catalog_id}", catalogId=catalog_id,
        catalogParentId="msk001", catalogRelation=relation,
        catalogLevel="POI", name=catalog_id, lat=lat, lon=lon,
        rubrics=[], schedule={}, isFood=False,
    )


def catalog_child(catalog_id, relation, lat=None, lon=None, place_id=None):
    return SimpleNamespace(
        id=catalog_id, dgis_place_id=place_id, name=catalog_id,
        lat=lat, lon=lon, relation=relation,
    )


def zones():
    geometry = {"type": "Polygon", "coordinates": [[
        [37.60, 55.74], [37.62, 55.74], [37.62, 55.76],
        [37.60, 55.76], [37.60, 55.74],
    ]]}
    return VisitZones({"msk001": VisitZone("msk001", geometry)})


def test_group_exposes_complete_catalog_without_internal_route_or_budget_changes():
    route = parent_route()
    rows = [
        catalog_child("msk002", "CONTAINS", 55.751, 37.611, "2gis-2"),
        catalog_child("msk003", "CLUSTER_MEMBER", 55.752, 37.612),
        catalog_child("msk004", "CONTAINS"),
    ]
    geo = GroupGeo()

    grouped = attach_route_groups(
        route, [parent_candidate()], preview(interests=["NATURE"]), geo,
        GroupCatalog(rows), zones(),
    )

    assert grouped.routeGroupsEnabled is True
    assert len(grouped.routeGroups) == 1
    group = grouped.routeGroups[0]
    assert [item.catalogId for item in group.children] == [
        "msk002", "msk003", "msk004",
    ]
    assert [item.relation for item in group.children] == [
        "CONTAINS", "CLUSTER_MEMBER", "CONTAINS",
    ]
    assert group.children[2].lat is None
    assert group.waypoints == []
    assert group.waypointLegs == []
    assert group.visitZone.type == "Polygon"
    assert geo.calls == []
    assert grouped.points == route.points
    assert grouped.legs == route.legs
    assert grouped.totalMinutes == route.totalMinutes
    assert grouped.unusedMinutes == route.unusedMinutes


def test_group_mode_collapses_selected_children_into_one_parent_stop():
    parent = parent_candidate()
    children = [selected_child("msk002", "CONTAINS", 55.751, 37.611),
                selected_child("msk003", "CLUSTER_MEMBER", 55.752, 37.612)]
    collapsed = logical_group_candidates(
        [*children, parent], preview(),
        GroupCatalog([catalog_child("msk002", "CONTAINS")]), zones(),
    )
    assert [item.catalogId for item in collapsed] == ["msk001"]


def test_missing_parent_zone_keeps_group_and_point_fallback():
    grouped = attach_route_groups(
        parent_route(), [parent_candidate()], preview(), GroupGeo(),
        GroupCatalog([catalog_child("msk002", "CONTAINS", 55.751, 37.611)]),
        VisitZones({}),
    )
    assert len(grouped.routeGroups) == 1
    assert grouped.routeGroups[0].visitZone is None
    assert grouped.points == parent_route().points


def test_group_never_calls_geo_even_when_walking_filter_is_small():
    grouped = attach_route_groups(
        parent_route(), [parent_candidate()], preview(maxWalkingMinutes=1),
        GroupGeo(),
        GroupCatalog([catalog_child("msk002", "CONTAINS", 55.751, 37.611)]),
        zones(),
    )
    assert len(grouped.routeGroups) == 1
    assert grouped.legs == parent_route().legs


def test_bundled_red_square_and_kremlin_groups_expose_all_children():
    catalog = PlaceCatalog(":memory:")
    catalog.import_seed(bundled_seed_path())
    provider = CatalogPlaceProvider(catalog)

    red_square = provider.group_children("msk001")
    kremlin = provider.group_children("msk005")

    assert len(red_square) == 3
    assert len(kremlin) == 7
    assert {row.relation for row in red_square + kremlin} <= {
        "CONTAINS", "CLUSTER_MEMBER",
    }

    for interests in ([], ["NATURE"], ["HISTORY", "ARCHITECTURE"]):
        for catalog_id, expected_count in (("msk001", 3), ("msk005", 7)):
            grouped = attach_route_groups(
                parent_route(catalog_id), [parent_candidate(catalog_id)],
                preview(interests=interests), GroupGeo(), provider, VisitZones({}),
            )
            response = grouped.model_dump(mode="json")
            assert len(response["routeGroups"]) == 1
            assert len(response["routeGroups"][0]["children"]) == expected_count
            assert response["routeGroups"][0]["waypoints"] == []


def test_nizhny_kremlin_children_stay_optional_inside_route_group():
    catalog = PlaceCatalog(":memory:")
    nizhny_seed = next(path for path in bundled_seed_paths()
                       if path.name == "nizhny_novgorod_places_v0_1.csv")
    catalog.import_seed(nizhny_seed)
    provider = CatalogPlaceProvider(catalog)
    route = parent_route("nn001", "nizhny_novgorod")

    grouped = attach_route_groups(
        route, [parent_candidate("nn001")],
        preview(cityId="nizhny_novgorod"), GroupGeo(), provider, VisitZones({}),
    )

    assert grouped.points == route.points
    assert grouped.totalMinutes == route.totalMinutes
    assert len(grouped.routeGroups) == 1
    assert grouped.routeGroups[0].visitZone is None
    assert [child.catalogId for child in grouped.routeGroups[0].children] == [
        "nn002", "nn003", "nn004", "nn005", "nn006", "nn007",
    ]
def test_refresh_recovers_catalog_ids_and_reorders_complete_groups():
    catalog = PlaceCatalog(":memory:")
    catalog.import_seed(bundled_seed_path())
    provider = CatalogPlaceProvider(catalog)
    try:
        red_square, kremlin = catalog.get_by_ids(["msk001", "msk005"])
        route = parent_route().model_copy(update={"points": [
            RoutePoint(
                order=1, placeId=kremlin.dgis_place_id, name=kremlin.name,
                lat=kremlin.lat, lon=kremlin.lon, visitMinutes=40,
                scheduleStatus="OPEN", isFood=False,
            ),
            RoutePoint(
                order=2, placeId=red_square.dgis_place_id, name=red_square.name,
                lat=red_square.lat, lon=red_square.lon, visitMinutes=40,
                scheduleStatus="OPEN", isFood=False,
            ),
        ]})

        refreshed = refresh_route_groups(route, provider, VisitZones({}))

        assert [point.catalogId for point in refreshed.points] == ["msk005", "msk001"]
        assert [(group.pointOrder, group.catalogId, len(group.children))
                for group in refreshed.routeGroups] == [
            (1, "msk005", 7), (2, "msk001", 3),
        ]
        assert all(group.waypoints == [] for group in refreshed.routeGroups)
    finally:
        catalog.close()

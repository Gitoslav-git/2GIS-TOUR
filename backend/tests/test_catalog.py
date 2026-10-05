import csv
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from gulyay.catalog import (CatalogImportError, CatalogPlaceProvider,
                            PlaceCatalog, bundled_seed_path, bundled_seed_paths)
from gulyay.catalog_seed import resolve_missing
from gulyay.geo import CatalogPlaceResolution, GeoUnavailable
from gulyay.models import (CreateRoute, PlaceCandidate, QueryPreview, RouteLeg,
                           SearchArea)
from gulyay.repository import RouteRepository
from gulyay.route_builder import build_route
from gulyay.visit_categories import visit_minutes


FIELDS = [
    "id", "city_id", "name", "level", "parent_id", "relation", "type", "tags",
    "access_cost", "base_price_from_rub", "base_price_to_rub", "price_note",
    "visit_min", "visit_max", "lat", "lon", "dgis_place_id",
    "price_source_url", "notes", "search_aliases", "provider_name", "allow_coords_only",
]


def row(place_id: str, name: str, *, tags="HISTORY", place_type="monument",
        lat="55.75", lon="37.61", provider_id=None, level="POI",
        parent_id="", relation="", city_id="moscow", visit_min="20",
        visit_max="40"):
    dgis_place_id = f"dgis-{place_id}" if provider_id is None else provider_id
    return {
        "id": place_id, "city_id": city_id, "name": name, "level": level,
        "parent_id": parent_id, "relation": relation, "type": place_type,
        "tags": tags, "access_cost": "FREE", "base_price_from_rub": "0",
        "base_price_to_rub": "0", "price_note": "", "visit_min": visit_min,
        "visit_max": visit_max, "lat": lat, "lon": lon,
        "dgis_place_id": dgis_place_id,
        "allow_coords_only": "0",
        "price_source_url": "", "notes": "", "search_aliases": "",
        "provider_name": f"2ГИС {name}" if dgis_place_id else "",
    }


def seed(tmp_path: Path, rows: list[dict], name="seed.csv") -> Path:
    path = tmp_path / name
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def preview(**updates) -> QueryPreview:
    data = {
        "cityId": "moscow", "durationMinutes": 180, "durationSource": "text",
        "interests": [], "includeFood": False, "withChildren": False,
        "unusualPlaces": False, "centerOnly": False, "allowSinglePlace": False,
        "warnings": [],
    }
    data.update(updates)
    if data.get("includeFood") and "foodMode" not in updates:
        data["foodMode"] = "REQUIRED"
    return QueryPreview.model_validate(data)


def area() -> SearchArea:
    return SearchArea(label="Москва", lat=55.75, lon=37.61,
                      radiusMeters=12000, source="city")


class TrackingGeo:
    def __init__(self, fallback=None, food=None):
        self.fallback = fallback or []
        self.food = food or []
        self.attraction_searches = 0
        self.food_searches = 0
        self.routing_calls = 0

    def resolve_city_center(self, city_id):
        return 55.75, 37.61

    def resolve_search_area(self, city_id, location_hint, center):
        return area()

    def search_places(self, city_id, query_preview, search_area):
        self.attraction_searches += 1
        return self.fallback

    def search_food_places(self, city_id, query_preview, search_area):
        self.food_searches += 1
        return self.food if query_preview.includeFood else []

    def walking_leg(self, start, end, from_order, to_order):
        self.routing_calls += 1
        return RouteLeg(fromOrder=from_order, toOrder=to_order, distanceMeters=300,
                        durationSeconds=240,
                        geometry=[[start[1], start[0]], [end[1], end[0]]])


def provider(tmp_path: Path, rows: list[dict]) -> CatalogPlaceProvider:
    catalog = PlaceCatalog(tmp_path / "catalog.sqlite3")
    catalog.import_seed(seed(tmp_path, rows))
    return CatalogPlaceProvider(catalog)


def test_seed_import_is_idempotent_and_route_clear_does_not_touch_catalog(tmp_path):
    database = tmp_path / "shared.sqlite3"
    catalog = PlaceCatalog(database)
    first = catalog.import_seed(bundled_seed_path())
    second = catalog.import_seed(bundled_seed_path())
    assert first == second == 63
    assert len(catalog.list_places("moscow")) == 63
    RouteRepository(database).clear()
    assert len(catalog.list_places("moscow")) == 63


def test_reimport_of_synced_seed_keeps_current_visit_ranges(tmp_path):
    catalog = PlaceCatalog(tmp_path / "catalog.sqlite3")
    catalog.import_seed(bundled_seed_path())
    first = {place.id: (place.visit_min, place.visit_max)
             for place in catalog.list_places("moscow")}
    assert first["msk001"] == (25, 45)
    assert first["msk055"] == (60, 120)  # Поклонная гора

    catalog.import_seed(bundled_seed_path())
    repeated = {place.id: (place.visit_min, place.visit_max)
                for place in catalog.list_places("moscow")}
    assert repeated == first


def test_tula_seed_uses_multicity_catalog_and_catalog_first_route_retrieval(tmp_path):
    database = tmp_path / "shared.sqlite3"
    catalog = PlaceCatalog(database)
    catalog.import_seed(bundled_seed_path())
    tula_seed = next(path for path in bundled_seed_paths()
                     if path.name == "tula_places_v0_1.csv")
    assert catalog.import_seed(tula_seed) == 30
    assert catalog.has_city("tula")
    assert len(catalog.list_places("tula")) == 30

    by_id = {place.id: place for place in catalog.list_places("tula")}
    assert by_id["tla001"].dgis_place_id == "5067077861776228"
    assert by_id["tla001"].provider_name == "Тульский Кремль"
    assert by_id["tla001"].search_aliases == (
        "Тульский Кремль музей", "Кремль Тула",
    )
    assert (by_id["tla010"].lat, by_id["tla010"].lon) == (54.204136, 37.616189)

    # Simulate the second provider-confirmed result produced by offline
    # catalog_seed enrichment. Two ready rows activate catalog-first retrieval.
    catalog.apply_manual_overrides({
        "tla001": {"lat": 54.1958, "lon": 37.6185},
        "tla007": {"lat": 54.1947, "lon": 37.6176},
    })
    catalog_provider = CatalogPlaceProvider(catalog)
    assert catalog_provider.has_sufficient_resolved("tula")

    geo = TrackingGeo()
    geo.resolve_city_center = lambda city_id: (54.193, 37.617)
    geo.resolve_search_area = lambda city_id, location_hint, center: SearchArea(
        label="Тула", lat=54.193, lon=37.617, radiusMeters=12000, source="city",
    )
    route = build_route(
        CreateRoute(cityId="tula", query="Прогулка по Туле"),
        preview(cityId="tula"), geo,
        datetime(2026, 10, 2, 12, tzinfo=ZoneInfo("Europe/Moscow")),
        catalog=catalog_provider,
    )
    assert geo.attraction_searches == 0
    assert route.points


def test_vladimir_seed_uses_multicity_catalog_and_catalog_first_route_retrieval(tmp_path):
    catalog = PlaceCatalog(tmp_path / "shared.sqlite3")
    vladimir_seed = next(path for path in bundled_seed_paths()
                         if path.name == "vladimir_places_v0_1.csv")
    assert catalog.import_seed(vladimir_seed) == 30
    assert catalog.has_city("vladimir")
    assert len(catalog.list_places("vladimir")) == 30

    by_id = {place.id: place for place in catalog.list_places("vladimir")}
    assert by_id["vld001"].dgis_place_id == "8304040093985093"
    assert by_id["vld001"].provider_name == "Золотые Ворота"
    assert by_id["vld001"].search_aliases == (
        "Золотые ворота Владимир", "Золотые Ворота музей-заповедник",
    )

    # Simulate offline enrichment for three rows that already have verified
    # provider IDs. This is sufficient to turn on local catalogue retrieval.
    catalog.apply_manual_overrides({
        "vld001": {"lat": 56.1287, "lon": 40.4053},
        "vld003": {"lat": 56.1295, "lon": 40.4096},
        "vld004": {"lat": 56.1301, "lon": 40.4102},
    })
    catalog_provider = CatalogPlaceProvider(catalog)
    assert catalog_provider.has_sufficient_resolved("vladimir")

    geo = TrackingGeo()
    geo.resolve_city_center = lambda city_id: (56.128, 40.407)
    geo.resolve_search_area = lambda city_id, location_hint, center: SearchArea(
        label="Владимир", lat=56.128, lon=40.407, radiusMeters=12000, source="city",
    )
    route = build_route(
        CreateRoute(cityId="vladimir", query="Прогулка по Владимиру"),
        preview(cityId="vladimir"), geo,
        datetime(2026, 10, 5, 12, tzinfo=ZoneInfo("Europe/Moscow")),
        catalog=catalog_provider,
    )
    assert geo.attraction_searches == 0
    assert route.points


def test_borovsk_seed_uses_multicity_catalog_and_catalog_first_route_retrieval(tmp_path):
    catalog = PlaceCatalog(tmp_path / "shared.sqlite3")
    borovsk_seed = next(path for path in bundled_seed_paths()
                        if path.name == "borovsk_places_v0_1.csv")
    assert catalog.import_seed(borovsk_seed) == 30
    assert catalog.has_city("borovsk")
    assert len(catalog.list_places("borovsk")) == 30

    by_id = {place.id: place for place in catalog.list_places("borovsk")}
    assert by_id["brv003"].dgis_place_id == "70000001064232897"
    assert by_id["brv003"].provider_name == "Стольный город Боровск"
    catalog.apply_manual_overrides({
        "brv003": {"lat": 55.2077, "lon": 36.4863},
        "brv011": {"lat": 55.2070, "lon": 36.4849, "dgis_place_id": "brv011"},
        "brv019": {"lat": 55.2102, "lon": 36.4725},
    })
    catalog_provider = CatalogPlaceProvider(catalog)
    assert catalog_provider.has_sufficient_resolved("borovsk")

    geo = TrackingGeo()
    geo.resolve_city_center = lambda city_id: (55.207, 36.485)
    geo.resolve_search_area = lambda city_id, location_hint, center: SearchArea(
        label="Borovsk", lat=55.207, lon=36.485, radiusMeters=12000, source="city",
    )
    route = build_route(
        CreateRoute(cityId="borovsk", query="walk"),
        preview(cityId="borovsk"), geo,
        datetime(2026, 10, 5, 12, tzinfo=ZoneInfo("Europe/Moscow")),
        catalog=catalog_provider,
    )
    assert geo.attraction_searches == 0
    assert route.points


@pytest.mark.parametrize("change,expected", [
    ({"tags": "HISTORY,UNKNOWN"}, "неизвестные tags"),
    ({"relation": "OWNS", "parent_id": "root"}, "неизвестный relation"),
    ({"relation": "CONTAINS", "parent_id": "missing"}, "parent_id"),
])
def test_invalid_seed_values_are_rejected(tmp_path, change, expected):
    invalid = row("bad", "Ошибка")
    invalid.update(change)
    with pytest.raises(CatalogImportError, match=expected):
        PlaceCatalog(":memory:").import_seed(seed(tmp_path, [invalid]))


def test_moscow_is_catalog_supported_but_unresolved_seed_is_not_runtime_ready(tmp_path):
    catalog = PlaceCatalog(tmp_path / "catalog.sqlite3")
    catalog.import_seed(bundled_seed_path())
    catalog_provider = CatalogPlaceProvider(catalog)
    assert catalog_provider.has_city("moscow")
    assert not catalog_provider.has_sufficient_resolved("moscow")
    assert catalog_provider.list_candidates("moscow", preview(), area()) == []


def test_unsupported_city_keeps_provider_fallback(tmp_path):
    fallback = [PlaceCandidate(placeId="tula-1", name="Кремль", lat=55.75, lon=37.61,
                               rubrics=[], schedule={"is_24x7": True}, isFood=False),
                PlaceCandidate(placeId="tula-2", name="Набережная", lat=55.751, lon=37.611,
                               rubrics=[], schedule={"is_24x7": True}, isFood=False)]
    geo = TrackingGeo(fallback=fallback)
    catalog_provider = provider(tmp_path, [row("m1", "Москва 1"), row("m2", "Москва 2")])
    route = build_route(
        CreateRoute(cityId="tula", query="Прогулка по Туле"),
        preview(cityId="tula"), geo,
        datetime(2026, 10, 1, 12, tzinfo=ZoneInfo("Europe/Moscow")),
        catalog=catalog_provider,
    )
    assert geo.attraction_searches == 1
    assert route.points


def test_moscow_catalog_avoids_text_attraction_search_and_keeps_routing(tmp_path):
    geo = TrackingGeo()
    catalog_provider = provider(tmp_path, [
        row("m1", "Историческое место", lat="55.750", lon="37.610"),
        row("m2", "Архитектурное место", tags="ARCHITECTURE", lat="55.752", lon="37.612"),
        row("m3", "Городское место", tags="LOCAL_CULTURE", lat="55.754", lon="37.614"),
    ])
    route = build_route(
        CreateRoute(cityId="moscow", query="Прогулка по Москве"), preview(), geo,
        datetime(2026, 10, 1, 12, tzinfo=ZoneInfo("Europe/Moscow")),
        catalog=catalog_provider,
    )
    assert geo.attraction_searches == 0
    assert geo.routing_calls > 0
    assert route.points
    assert any("локального каталога" in warning for warning in route.warnings)


def test_quick_filters_are_hard_catalog_constraints(tmp_path):
    catalog_provider = provider(tmp_path, [
        row("family", "Семейное", tags="FAMILY,UNUSUAL"),
        row("unusual", "Необычное", tags="UNUSUAL"),
        row("ordinary", "Обычное", tags="HISTORY"),
    ])
    family = catalog_provider.list_candidates(
        "moscow", preview(withChildren=True), area(),
    )
    unusual = catalog_provider.list_candidates(
        "moscow", preview(unusualPlaces=True), area(),
    )
    both = catalog_provider.list_candidates(
        "moscow", preview(withChildren=True, unusualPlaces=True), area(),
    )
    assert {item.catalogId for item in family} == {"family"}
    assert {item.catalogId for item in unusual} == {"family", "unusual"}
    assert {item.catalogId for item in both} == {"family"}


def test_semantic_relevance_outweighs_distance(tmp_path):
    catalog_provider = provider(tmp_path, [
        row("near", "Рядом", tags="NATURE", lat="55.7501", lon="37.6101"),
        row("far", "История", tags="HISTORY", lat="55.82", lon="37.69"),
    ])
    ranked = catalog_provider.list_candidates(
        "moscow", preview(interests=["HISTORIC_PLACES"],
                          interestPriorities={"HISTORIC_PLACES": "HIGH"}), area(),
    )
    assert [item.catalogId for item in ranked][:2] == ["far", "near"]


def test_borovsk_partial_concept_coverage_builds_route_without_museums(tmp_path):
    """Preferences relax gracefully; an unavailable third topic is not NO_ROUTE."""
    catalog_provider = provider(tmp_path, [
        row("space", "Tsiolkovsky monument", city_id="borovsk",
            tags="SCIENCE_TECH,UNUSUAL", place_type="monument",
            lat="55.2076", lon="36.4844"),
        row("view", "Borovsk viewpoint", city_id="borovsk",
            tags="PANORAMIC", place_type="viewpoint",
            lat="55.2090", lon="36.4855"),
        row("museum", "Space museum", city_id="borovsk",
            tags="SCIENCE_TECH", place_type="science_museum",
            lat="55.2080", lon="36.4850"),
        row("neutral", "Historic street", city_id="borovsk",
            tags="HISTORY", place_type="historic_building",
            lat="55.2100", lon="36.4860"),
    ])
    geo = TrackingGeo()
    geo.resolve_city_center = lambda city_id: (55.207583, 36.484355)
    geo.resolve_search_area = lambda city_id, location_hint, center: SearchArea(
        label="Borovsk", lat=55.207583, lon=36.484355,
        radiusMeters=12000, source="city",
    )
    preferences = ["SCIENCE", "ARCHITECTURE", "VIEWPOINTS"]
    result = build_route(
        CreateRoute(cityId="borovsk", query="cosmos, unusual architecture and views; no museums"),
        preview(cityId="borovsk", durationMinutes=120, interests=preferences,
                interestPriorities={concept: "HIGH" for concept in preferences},
                hardExclusions=["MUSEUMS"]),
        geo, datetime(2026, 10, 5, 12, tzinfo=ZoneInfo("Europe/Moscow")),
        catalog=catalog_provider,
    )
    selected = {point.placeId for point in result.points}
    assert result.points
    assert "dgis-museum" not in selected
    assert "dgis-space" in selected
    assert "dgis-view" in selected


@pytest.mark.parametrize(("seed_name", "city_id", "priority", "expected_ids", "overrides", "anchor"), [
    ("moscow_places_v0_1.csv", "moscow", {"HISTORIC_PLACES": "HIGH", "ARCHITECTURE": "HIGH"},
     {"msk001", "msk002"}, {"msk001": {"lat": 55.75, "lon": 37.61},
                               "msk002": {"lat": 55.751, "lon": 37.611}}, (55.75, 37.61)),
    ("tula_places_v0_1.csv", "tula", {"MILITARY": "HIGH", "HISTORIC_PLACES": "HIGH"},
     {"tla003"}, {"tla003": {"lat": 54.196, "lon": 37.617,
                                "allow_coords_only": True}}, (54.196, 37.617)),
    ("vladimir_places_v0_1.csv", "vladimir", {"RELIGIOUS_PLACES": "HIGH", "ARCHITECTURE": "HIGH"},
     {"vld011", "vld012"}, {"vld011": {"lat": 56.129, "lon": 40.409},
                               "vld012": {"lat": 56.13, "lon": 40.41}}, (56.129, 40.409)),
    ("borovsk_places_v0_1.csv", "borovsk", {"SCIENCE": "HIGH", "UNUSUAL_PLACES": "HIGH"},
     {"brv018", "brv020"}, {"brv018": {"lat": 55.207, "lon": 36.485,
                                             "allow_coords_only": True},
                               "brv020": {"lat": 55.208, "lon": 36.486,
                                             "allow_coords_only": True}}, (55.207, 36.485)),
])
def test_catalog_city_intent_prioritizes_matching_seed_places(
        tmp_path, seed_name, city_id, priority, expected_ids, overrides, anchor):
    catalog = PlaceCatalog(tmp_path / "catalog.sqlite3")
    path = next(item for item in bundled_seed_paths() if item.name == seed_name)
    catalog.import_seed(path)
    catalog.apply_manual_overrides(overrides)
    ranked = CatalogPlaceProvider(catalog).list_candidates(
        city_id, preview(cityId=city_id, interests=list(priority), interestPriorities=priority),
        SearchArea(label="test", lat=anchor[0], lon=anchor[1], radiusMeters=20000, source="city"),
    )
    assert expected_ids.intersection(item.catalogId for item in ranked[:3])


def test_catalog_hard_free_budget_and_type_filters(tmp_path):
    paid = row("paid", "Paid", tags="HISTORY", place_type="museum")
    paid.update({"access_cost": "PAID", "base_price_from_rub": "500", "base_price_to_rub": "500"})
    mixed_free = row("mixed", "Mixed", tags="HISTORY", place_type="gallery")
    mixed_free.update({"access_cost": "MIXED", "base_price_from_rub": "0", "base_price_to_rub": "0"})
    catalog_provider = provider(tmp_path, [paid, mixed_free, row("free", "Free", tags="HISTORY")])
    free = catalog_provider.list_candidates("moscow", preview(freeOnly=True), area())
    assert {item.catalogId for item in free} == {"mixed", "free"}
    filtered = catalog_provider.list_candidates(
        "moscow", preview(maxBudgetRub=100, excludedPlaceTypes=["gallery"]), area(),
    )
    assert {item.catalogId for item in filtered} == {"free"}


def test_variety_penalizes_repeated_place_type(tmp_path):
    catalog_provider = provider(tmp_path, [
        row("museum-a", "Музей A", tags="ART_CULTURE", place_type="museum"),
        row("museum-b", "Музей B", tags="ART_CULTURE", place_type="museum"),
        row("museum-c", "Музей C", tags="ART_CULTURE", place_type="museum"),
        row("park", "Парк", tags="NATURE", place_type="urban_park"),
    ])
    ranked = catalog_provider.list_candidates("moscow", preview(), area())
    ids = [item.catalogId for item in ranked]
    park_index = ids.index("park")
    assert sum(value.startswith("museum-") for value in ids[:park_index]) <= 1


def test_complex_and_contains_child_are_not_two_visits_but_siblings_are_allowed(tmp_path):
    catalog_provider = provider(tmp_path, [
        row("complex", "Комплекс", tags="NATURE", level="COMPLEX",
            visit_min="20", visit_max="20"),
        row("child-a", "Объект A", parent_id="complex", relation="CONTAINS",
            visit_min="20", visit_max="20", lat="55.751", lon="37.611"),
        row("child-b", "Объект B", parent_id="complex", relation="CONTAINS",
            visit_min="20", visit_max="20", lat="55.752", lon="37.612"),
    ])
    geo = TrackingGeo()
    route = build_route(
        CreateRoute(cityId="moscow", query="Три места комплекса"),
        preview(durationMinutes=180, requestedPlaceCount=2,
                interests=["HISTORIC_PLACES"],
                interestPriorities={"HISTORIC_PLACES": "HIGH"}), geo,
        datetime(2026, 10, 1, 12, tzinfo=ZoneInfo("Europe/Moscow")),
        catalog=catalog_provider,
    )
    selected = set(point.placeId for point in route.points)
    assert not ({"dgis-complex", "dgis-child-a"} <= selected)
    assert not ({"dgis-complex", "dgis-child-b"} <= selected)
    assert selected == {"dgis-child-a", "dgis-child-b"}


def test_catalog_visit_range_controls_pace():
    candidate = PlaceCandidate(
        placeId="catalog", name="Каталог", lat=55.75, lon=37.61,
        rubrics=[], schedule={}, isFood=False, catalogVisitMin=30,
        catalogVisitMax=90,
    )
    assert visit_minutes(candidate, "INTENSIVE") == 30
    assert visit_minutes(candidate, "NORMAL") == 60
    assert visit_minutes(candidate, "RELAXED") == 90


def test_food_lane_is_combined_with_catalog_sights(tmp_path):
    food = PlaceCandidate(placeId="food", name="Кафе", lat=55.753, lon=37.613,
                          rubrics=["Кафе"], schedule={"is_24x7": True}, isFood=True)
    geo = TrackingGeo(food=[food])
    catalog_provider = provider(tmp_path, [
        row("m1", "Место 1", lat="55.750", lon="37.610"),
        row("m2", "Место 2", lat="55.752", lon="37.612"),
    ])
    route = build_route(
        CreateRoute(cityId="moscow", query="Москва и кафе"),
        preview(includeFood=True, foodMode="REQUIRED"), geo,
        datetime(2026, 10, 1, 12, tzinfo=ZoneInfo("Europe/Moscow")),
        catalog=catalog_provider,
    )
    assert geo.attraction_searches == 0
    assert geo.food_searches >= 1
    assert any(point.isFood for point in route.points)


def test_unresolved_rows_are_never_candidates(tmp_path):
    catalog_provider = provider(tmp_path, [
        row("resolved-a", "Готово A"), row("resolved-b", "Готово B"),
        row("missing", "Без координат", lat="", lon="", provider_id=""),
    ])
    candidates = catalog_provider.list_candidates("moscow", preview(), area())
    assert {item.catalogId for item in candidates} == {"resolved-a", "resolved-b"}


def test_area_and_complex_can_be_ready_with_coordinates_only_but_poi_cannot(tmp_path):
    catalog = PlaceCatalog(tmp_path / "catalog.sqlite3")
    catalog.import_seed(seed(tmp_path, [
        row("area", "Район", level="AREA", provider_id=""),
        row("complex", "Комплекс", level="COMPLEX", provider_id=""),
        row("poi", "Точка", level="POI", provider_id=""),
    ]))
    provider_layer = CatalogPlaceProvider(catalog)
    assert catalog.resolved_count("moscow") == 2
    assert {place.id for place in catalog.unresolved("moscow")} == {"poi"}
    candidates = provider_layer.list_candidates("moscow", preview(), area())
    assert {item.placeId for item in candidates} == {
        "catalog:area", "catalog:complex",
    }
    report = catalog.enrichment_groups("moscow")
    assert {place.id for place in report[1]} == {"area", "complex"}
    assert {place.id for place in report[2]} == {"poi"}


def test_manual_coords_only_poi_is_retrievable_and_never_auto_resolved(tmp_path):
    catalog = PlaceCatalog(tmp_path / "catalog.sqlite3")
    catalog.import_seed(seed(tmp_path, [
        row("viewpoint", "Смотровая площадка", lat="", lon="", provider_id=""),
    ]))
    catalog.apply_manual_overrides({
        "viewpoint": {"lat": 56.128, "lon": 40.407, "allow_coords_only": True},
    })

    place = catalog.get_by_ids(["viewpoint"])[0]
    assert place.allow_coords_only is True
    assert place.dgis_place_id is None
    assert catalog.resolved_count("moscow") == 1
    assert catalog.unresolved("moscow") == []
    candidates = CatalogPlaceProvider(catalog).list_candidates("moscow", preview(), area())
    assert [(candidate.placeId, candidate.lat, candidate.lon) for candidate in candidates] == [
        ("catalog:viewpoint", 56.128, 40.407),
    ]
    provider, coords_only, unresolved = catalog.enrichment_groups("moscow")
    assert provider == []
    assert [item.id for item in coords_only] == ["viewpoint"]
    assert unresolved == []

    class Resolver:
        def resolve_catalog_place(self, city_id, name, aliases=()):
            raise AssertionError("coords-only POI must not be sent to 2GIS")

    report = resolve_missing(catalog, Resolver())
    assert [item.id for item in report.resolved_coords_only] == ["viewpoint"]


def test_search_aliases_provider_name_and_confirmed_values_are_preserved(tmp_path):
    catalog = PlaceCatalog(tmp_path / "catalog.sqlite3")
    initial = row("place", "Наше название", lat="", lon="", provider_id="")
    initial["search_aliases"] = '["Алиас один", "Алиас два"]'
    catalog.import_seed(seed(tmp_path, [initial], "initial.csv"))
    catalog.apply_manual_overrides({
        "place": {
            "lat": 55.7, "lon": 37.6, "dgis_place_id": "manual-id",
            "provider_name": "Фактическое имя 2ГИС",
        },
    })
    changed_seed = row("place", "Наше название", lat="1", lon="2",
                       provider_id="seed-id")
    changed_seed["provider_name"] = "Имя из seed"
    changed_seed["search_aliases"] = '["Новый алиас"]'
    catalog.import_seed(seed(tmp_path, [changed_seed], "changed.csv"))
    place = catalog.get_by_ids(["place"])[0]
    assert place.name == "Наше название"
    assert place.provider_name == "Фактическое имя 2ГИС"
    assert place.dgis_place_id == "manual-id"
    assert (place.lat, place.lon) == (55.7, 37.6)
    assert place.search_aliases == ("Новый алиас",)


def test_reimport_preserves_empty_seed_enrichment_and_resolver_uses_aliases(tmp_path):
    catalog = PlaceCatalog(tmp_path / "catalog.sqlite3")
    initial = row("place", "Наше короткое имя", lat="", lon="", provider_id="")
    initial["search_aliases"] = '["Официальный алиас 2ГИС"]'
    catalog.import_seed(seed(tmp_path, [initial], "initial.csv"))
    catalog.apply_manual_overrides({
        "place": {
            "lat": 55.7, "lon": 37.6,
            "provider_name": "Подтверждённое имя",
        },
    })

    repeated = row("place", "Обновлённое продуктовое имя",
                   lat="", lon="", provider_id="")
    repeated["search_aliases"] = "[]"
    repeated["provider_name"] = ""
    catalog.import_seed(seed(tmp_path, [repeated], "repeated.csv"))

    preserved = catalog.get_by_ids(["place"])[0]
    assert preserved.name == "Обновлённое продуктовое имя"
    assert preserved.search_aliases == ("Официальный алиас 2ГИС",)
    assert (preserved.lat, preserved.lon) == (55.7, 37.6)
    assert preserved.provider_name == "Подтверждённое имя"
    assert preserved.dgis_place_id is None

    class AliasResolver:
        def __init__(self):
            self.calls = []

        def resolve_catalog_place(self, city_id, name, aliases=()):
            self.calls.append((city_id, name, aliases))
            if aliases != ("Официальный алиас 2ГИС",):
                return None
            return CatalogPlaceResolution(
                dgis_place_id="resolved-by-alias",
                provider_name="Имя из 2ГИС", lat=55.71, lon=37.61,
            )

    resolver = AliasResolver()
    report = resolve_missing(catalog, resolver)
    assert resolver.calls == [(
        "moscow", "Обновлённое продуктовое имя",
        ("Официальный алиас 2ГИС",),
    )]
    assert {place.id for place in report.resolved_provider} == {"place"}
    resolved = catalog.get_by_ids(["place"])[0]
    assert resolved.dgis_place_id == "resolved-by-alias"
    # Automatic enrichment cannot overwrite reviewed manual coordinates/name.
    assert (resolved.lat, resolved.lon) == (55.7, 37.6)
    assert resolved.provider_name == "Подтверждённое имя"


def test_bundled_seed_splits_composite_poi_and_uses_concrete_viewpoint(tmp_path):
    catalog = PlaceCatalog(tmp_path / "catalog.sqlite3")
    catalog.import_seed(bundled_seed_path())
    by_id = {place.id: place for place in catalog.list_places("moscow")}
    assert by_id["msk050"].name == "Большой дворец"
    assert by_id["msk063"].name == "Хлебный дом"
    assert "+" not in by_id["msk050"].name
    assert by_id["msk035"].name == "Смотровая площадка PANORAMA360"
    assert "PANORAMA360" in by_id["msk035"].search_aliases


def test_enrichment_continues_after_provider_error_and_retries_only_missing(
        tmp_path, caplog):
    catalog = PlaceCatalog(tmp_path / "catalog.sqlite3")
    catalog.import_seed(seed(tmp_path, [
        row("ready", "Уже заполнено"),
        row("failed", "Ошибка провайдера", lat="", lon="", provider_id=""),
        row("empty", "Пустая выдача", lat="", lon="", provider_id=""),
        row("success", "Найдено", lat="", lon="", provider_id=""),
    ]))

    class Resolver:
        def __init__(self):
            self.calls = []

        def resolve_catalog_place(self, city_id, name, aliases=()):
            self.calls.append((city_id, name))
            if name == "Ошибка провайдера":
                raise GeoUnavailable("temporary failure")
            if name == "Пустая выдача":
                return None
            return CatalogPlaceResolution(
                dgis_place_id="provider-success", provider_name="Найдено 2ГИС",
                lat=55.76, lon=37.62,
            )

    resolver = Resolver()
    caplog.set_level("WARNING", logger="gulyay.catalog_seed")
    report = resolve_missing(catalog, resolver)
    assert {place.id for place in report.resolved_provider} == {"ready", "success"}
    assert {place.id for place in report.unresolved} == {"failed", "empty"}
    assert [name for _, name in resolver.calls] == [
        "Пустая выдача", "Ошибка провайдера", "Найдено",
    ]
    assert "catalog_id=failed" in caplog.text
    assert "GeoUnavailable" in caplog.text
    successful = catalog.get_by_ids(["success"])[0]
    assert successful.name == "Найдено"
    assert successful.provider_name == "Найдено 2ГИС"
    assert successful.dgis_place_id == "provider-success"

    report_again = resolve_missing(catalog, resolver)
    assert {place.id for place in report_again.resolved_provider} == {"ready", "success"}
    assert {place.id for place in report_again.unresolved} == {"failed", "empty"}
    # Neither the originally complete row nor the successfully enriched row is retried.
    assert [name for _, name in resolver.calls[3:]] == [
        "Пустая выдача", "Ошибка провайдера",
    ]


def test_enrichment_accepts_coords_only_for_area_but_retries_poi_without_id(tmp_path):
    catalog = PlaceCatalog(tmp_path / "catalog.sqlite3")
    catalog.import_seed(seed(tmp_path, [
        row("area", "Большая территория", level="AREA", lat="", lon="", provider_id=""),
        row("poi", "Конкретная точка", level="POI", lat="", lon="", provider_id=""),
    ]))

    class CoordsOnlyResolver:
        def __init__(self):
            self.calls = []

        def resolve_catalog_place(self, city_id, name, aliases=()):
            self.calls.append(name)
            return CatalogPlaceResolution(
                dgis_place_id=None, provider_name=f"2ГИС: {name}", lat=55.7, lon=37.6,
            )

    resolver = CoordsOnlyResolver()
    report = resolve_missing(catalog, resolver)
    assert {place.id for place in report.resolved_coords_only} == {"area"}
    assert {place.id for place in report.unresolved} == {"poi"}
    area_place = catalog.get_by_ids(["area"])[0]
    assert area_place.name == "Большая территория"
    assert area_place.provider_name == "2ГИС: Большая территория"

    resolve_missing(catalog, resolver)
    assert resolver.calls == ["Большая территория", "Конкретная точка", "Конкретная точка"]


def test_enrichment_prefers_confirmed_provider_id_when_coordinates_are_missing(tmp_path):
    catalog = PlaceCatalog(tmp_path / "catalog.sqlite3")
    catalog.import_seed(seed(tmp_path, [
        row("known", "Наше имя", lat="", lon="", provider_id="confirmed-id"),
    ]))

    class Resolver:
        def __init__(self):
            self.calls = []

        def resolve_catalog_place_by_id(self, city_id, place_id):
            self.calls.append(("id", city_id, place_id))
            return CatalogPlaceResolution(
                dgis_place_id=place_id, provider_name="Фактическое имя 2ГИС",
                lat=55.75, lon=37.62,
            )

        def resolve_catalog_place(self, city_id, name, aliases=()):
            raise AssertionError("Поиск по имени не должен вызываться")

    resolver = Resolver()
    report = resolve_missing(catalog, resolver)
    assert resolver.calls == [("id", "moscow", "confirmed-id")]
    assert {place.id for place in report.resolved_provider} == {"known"}
    resolved = catalog.get_by_ids(["known"])[0]
    assert (resolved.lat, resolved.lon) == (55.75, 37.62)
    assert resolved.dgis_place_id == "confirmed-id"

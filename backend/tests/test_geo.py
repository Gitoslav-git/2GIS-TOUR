import json

import httpx
import pytest

from gulyay.geo import (DgisGeoProvider, GeoAuthenticationError,
                        GeoInvalidResponse, GeoPlaceNotFound, GeoRateLimited,
                        GeoRouteNotFound, GeoUnavailable, clear_geo_caches)
from gulyay.models import QueryPreview, RouteLeg
from gulyay.catalog import CatalogPlaceProvider, PlaceCatalog, bundled_seed_paths
from gulyay.route_builder import build_route
from gulyay.models import CreateRoute, SearchArea


def response(request: httpx.Request) -> httpx.Response:
    if request.url.host == "catalog.api.2gis.com":
        query = request.url.params.get("q")
        if query == "Тула":
            items = [{"id": "city-2gis", "name": "Тула", "point": {"lat": 54.193, "lon": 37.617}}]
        elif query == "Заречье, Тула":
            items = [{"id": "area-2gis", "name": "Заречье", "full_name": "Заречье, Тула",
                      "point": {"lat": 54.225, "lon": 37.62}}]
        else:
            items = [{
                "id": "real-2gis-place", "name": "Тульский кремль",
                "point": {"lat": 54.196, "lon": 37.619},
                "rubrics": [{"name": "Достопримечательности"}], "schedule": {"is_24x7": True},
                "is_routing_available": True,
            }]
        return httpx.Response(200, json={"meta": {"code": 200}, "result": {"items": items}})
    assert request.url.host == "routing.api.2gis.com"
    body = json.loads(request.content)
    assert body["transport"] == "walking"
    assert all(point["type"] == "walking" for point in body["points"])
    return httpx.Response(200, json={
        "status": "OK", "result": [{"total_distance": 430, "total_duration": 330,
            "begin_pedestrian_path": {"geometry": {"selection": "LINESTRING(37.617 54.193, 37.618 54.194)"}},
            "maneuvers": [{"outcoming_path": {"geometry": [
                {"selection": "LINESTRING(37.618 54.194 100, 37.619 54.196 110)"}]}}]}],
    })


def preview(center=True):
    return QueryPreview(cityId="tula", durationMinutes=180, durationSource="text",
                        interests=["LANDMARKS"], includeFood=False, withChildren=False,
                        unusualPlaces=False, centerOnly=center,
                        locationHint="центр" if center else None, warnings=[])


@pytest.fixture(autouse=True)
def clean_caches():
    clear_geo_caches()
    yield
    clear_geo_caches()


def test_places_and_walking_route_use_real_provider_payloads():
    provider = DgisGeoProvider("places-secret", "routing-secret", httpx.MockTransport(response))
    center = provider.resolve_city_center("tula")
    assert center == (54.193, 37.617)
    area = provider.resolve_search_area("tula", "центр", center)
    places = provider.search_places("tula", preview(), area)
    assert places[0].placeId == "real-2gis-place"
    leg = provider.walking_leg(center, (places[0].lat, places[0].lon), 0, 1)
    assert leg.distanceMeters == 430 and leg.durationSeconds == 330
    assert leg.geometry == [(37.617, 54.193), (37.618, 54.194), (37.619, 54.196)]


def test_catalog_route_with_device_geo_and_routing_key_does_not_need_places_key(tmp_path):
    calls = []

    def routing_only(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host)
        assert request.url.host == "routing.api.2gis.com"
        return httpx.Response(200, json={
            "status": "OK", "result": [{"total_distance": 200, "total_duration": 180,
                "begin_pedestrian_path": {"geometry": {"selection": "LINESTRING(37.617 54.193, 37.618 54.194)"}},
                "maneuvers": []}],
        })

    catalog = PlaceCatalog(tmp_path / "catalog.sqlite3")
    catalog.import_seed(next(path for path in bundled_seed_paths()
                             if path.name == "tula_places_v0_1.csv"))
    provider = DgisGeoProvider(places_key=None, routing_key="routing-only",
                               transport=httpx.MockTransport(routing_only))
    route = build_route(
        CreateRoute(cityId="tula", query="Прогулка", startLocation={
            "lat": 54.193, "lon": 37.617, "accuracyMeters": 10,
        }),
        QueryPreview(cityId="tula", durationMinutes=120, durationSource="default",
                     interests=[], includeFood=False, withChildren=False,
                     unusualPlaces=False, centerOnly=False, warnings=[]),
        provider, catalog=CatalogPlaceProvider(catalog),
    )
    assert route.startSource == "USER_GEO"
    assert calls and set(calls) == {"routing.api.2gis.com"}


def test_text_start_still_requires_places_geocoding():
    provider = DgisGeoProvider(places_key=None, routing_key="routing-only",
                               transport=httpx.MockTransport(response))
    with pytest.raises(GeoUnavailable):
        build_route(
            CreateRoute(cityId="tula", query="От кремля"),
            QueryPreview(cityId="tula", durationMinutes=120, durationSource="text",
                         interests=[], includeFood=False, withChildren=False,
                         unusualPlaces=False, centerOnly=False,
                         startLocationHint="Кремль", warnings=[]),
            provider,
        )


def test_borovsk_city_center_is_resolved_by_exact_city_name():
    def borovsk(request):
        assert request.url.params.get("q") == "Боровск"
        return httpx.Response(200, json={
            "meta": {"code": 200},
            "result": {"items": [{
                "id": "borovsk-city", "name": "Боровск",
                "point": {"lat": 55.2073, "lon": 36.4833},
            }]},
        })

    provider = DgisGeoProvider("p", "r", httpx.MockTransport(borovsk))
    assert provider.resolve_city_center("borovsk") == (55.2073, 36.4833)


def test_large_routing_geometry_is_bounded_and_keeps_ends():
    coordinates = ", ".join(
        f"{36.48 + index * 0.00001:.5f} {55.20 + index * 0.00001:.5f}"
        for index in range(1000)
    )

    def large_route(request):
        return httpx.Response(200, json={
            "status": "OK", "result": [{
                "total_distance": 5000, "total_duration": 3600,
                "begin_pedestrian_path": {
                    "geometry": {"selection": f"LINESTRING({coordinates})"},
                },
            }],
        })

    provider = DgisGeoProvider("p", "r", httpx.MockTransport(large_route))
    leg = provider.walking_leg((55.20, 36.48), (55.20999, 36.48999), 0, 1)
    assert len(leg.geometry) == 120
    assert leg.geometry[0] == (36.48, 55.20)
    assert leg.geometry[-1] == (36.48999, 55.20999)


def test_legacy_route_leg_geometry_is_compacted_when_loaded():
    points = [(36.48 + index * 0.00001, 55.20 + index * 0.00001)
              for index in range(700)]
    leg = RouteLeg(fromOrder=0, toOrder=1, distanceMeters=5000,
                   durationSeconds=3600, geometry=points)
    assert len(leg.geometry) == 120
    assert leg.geometry[0] == points[0]
    assert leg.geometry[-1] == points[-1]


def test_center_request_uses_smaller_search_radius():
    radii = []
    def capture(request):
        if request.url.host == "catalog.api.2gis.com":
            radii.append(request.url.params.get("radius"))
        return response(request)
    provider = DgisGeoProvider("p", "r", httpx.MockTransport(capture))
    center = (54.193, 37.617)
    provider.search_places("tula", preview(center=True), provider.resolve_search_area("tula", "центр", center))
    provider.search_places("tula", preview(center=False), provider.resolve_search_area("tula", None, center))
    assert radii == ["3500", "3500", "12000", "12000"]


def test_generic_walk_searches_outdoor_places_to_fill_evening_route():
    queries = []
    def capture(request):
        if request.url.host == "catalog.api.2gis.com":
            queries.append(request.url.params.get("q"))
        return response(request)
    provider = DgisGeoProvider("p", "r", httpx.MockTransport(capture))
    generic = preview(center=True).model_copy(update={"interests": []})
    area = provider.resolve_search_area("tula", "центр", (54.193, 37.617))
    provider.search_places("tula", generic, area)
    assert queries == [
        "Тульский кремль", "Казанская набережная",
        "достопримечательности и места для прогулок",
    ]


def test_unsafe_llm_interests_never_reach_2gis_query():
    queries = []
    def capture(request):
        if request.url.host == "catalog.api.2gis.com":
            queries.append(request.url.params.get("q"))
        return response(request)
    provider = DgisGeoProvider("p", "r", httpx.MockTransport(capture))
    unsafe = preview(center=True).model_copy(update={
        "interests": ["чтобы недалеко ходить", "без очередей"],
    })
    area = provider.resolve_search_area("tula", "центр", (54.193, 37.617))
    provider.search_places("tula", unsafe, area)
    assert queries == [
        "Тульский кремль", "Казанская набережная",
        "достопримечательности и места для прогулок",
    ]


def test_generic_search_is_ranked_from_area_and_includes_area_places():
    requests = []

    def capture(request):
        requests.append(request)
        return response(request)

    provider = DgisGeoProvider("p", "r", httpx.MockTransport(capture))
    generic = preview(center=True).model_copy(update={"interests": []})
    area = provider.resolve_search_area("tula", "центр", (54.193, 37.617))
    provider.search_places("tula", generic, area)

    assert all(request.url.params.get("location") == "37.6170000,54.1930000"
               for request in requests)
    assert "adm_div.place" in requests[0].url.params.get("type")
    assert "adm_div.place" in requests[1].url.params.get("type")


@pytest.mark.parametrize("rubric", [
    "Концертные залы", "Смотровые площадки", "Океанариумы",
    "Пешеходные улицы", "Пляжи", "Индустриальные арт-пространства",
])
def test_generic_tourist_filter_keeps_broad_walk_categories(rubric):
    def broad_place(request):
        item = {
            "id": rubric, "name": rubric,
            "point": {"lat": 54.194, "lon": 37.618},
            "rubrics": [{"name": rubric}], "is_routing_available": True,
        }
        return httpx.Response(200, json={
            "meta": {"code": 200}, "result": {"items": [item]},
        })

    provider = DgisGeoProvider("p", "r", httpx.MockTransport(broad_place))
    generic = preview(center=True).model_copy(update={"interests": []})
    area = provider.resolve_search_area("tula", "центр", (54.193, 37.617))
    assert provider.search_places("tula", generic, area)[0].name == rubric


def test_normalized_concept_is_mapped_to_backend_owned_queries():
    queries = []
    def capture(request):
        if request.url.host == "catalog.api.2gis.com":
            queries.append(request.url.params.get("q"))
        return response(request)
    provider = DgisGeoProvider("p", "r", httpx.MockTransport(capture))
    mixed = preview(center=True).model_copy(update={
        "interests": ["ARCHITECTURE", "между точками максимум 15 минут"],
    })
    area = provider.resolve_search_area("tula", "центр", (54.193, 37.617))
    provider.search_places("tula", mixed, area)
    assert queries == ["памятники архитектуры", "исторические здания"]


def test_manual_search_returns_only_provider_candidates_near_selected_city():
    provider = DgisGeoProvider("p", "r", httpx.MockTransport(response))
    places = provider.search_candidates("tula", "кремль")
    assert [place.placeId for place in places] == ["real-2gis-place"]
    assert places[0].name == "Тульский кремль"


def test_catalog_resolver_uses_wide_exact_search_for_area_and_validates_city():
    requests = []

    def catalog_area(request):
        requests.append(request)
        if request.url.params.get("q") == "Москва":
            items = [{"id": "city", "name": "Москва",
                      "point": {"lat": 55.7558, "lon": 37.6173}}]
        else:
            items = [{
                "id": "area-zaryadye", "name": "Зарядье", "type": "adm_div.place",
                "city_alias": "moscow", "point": {"lat": 55.751, "lon": 37.628},
            }]
        return httpx.Response(200, json={
            "meta": {"code": 200}, "result": {"items": items},
        })

    provider = DgisGeoProvider("p", "r", httpx.MockTransport(catalog_area))
    resolved = provider.resolve_catalog_place("moscow", "Зарядье")
    search = requests[-1]
    assert search.url.params.get("q") == "Зарядье, Москва"
    assert "type" not in search.url.params
    assert resolved is not None
    assert resolved.dgis_place_id == "area-zaryadye"
    assert resolved.provider_name == "Зарядье"


@pytest.mark.parametrize("not_found_response", [
    httpx.Response(200, json={"meta": {"code": 200}, "result": {"items": []}}),
    httpx.Response(200, json={"meta": {"code": 404,
                                       "error": {"type": "itemNotFound"}}}),
    httpx.Response(404, json={"error": "itemNotFound"}),
])
def test_catalog_resolver_treats_empty_and_item_not_found_as_unresolved(not_found_response):
    def missing(request):
        if request.url.params.get("q") == "Москва":
            return httpx.Response(200, json={
                "meta": {"code": 200}, "result": {"items": [{
                    "id": "city", "name": "Москва",
                    "point": {"lat": 55.7558, "lon": 37.6173},
                }]},
            })
        return not_found_response

    provider = DgisGeoProvider("p", "r", httpx.MockTransport(missing))
    assert provider.resolve_catalog_place("moscow", "Неизвестное место") is None


def test_catalog_resolver_rejects_ambiguous_or_foreign_matches():
    def ambiguous(request):
        if request.url.params.get("q") == "Москва":
            items = [{"id": "city", "name": "Москва",
                      "point": {"lat": 55.7558, "lon": 37.6173}}]
        else:
            items = [
                {"id": "one", "name": "Смотровая башня", "city_alias": "moscow",
                 "point": {"lat": 55.75, "lon": 37.61}},
                {"id": "two", "name": "Смотровая башня", "city_alias": "moscow",
                 "point": {"lat": 55.76, "lon": 37.62}},
                {"id": "foreign", "name": "Смотровая башня", "city_alias": "tula",
                 "point": {"lat": 54.19, "lon": 37.61}},
            ]
        return httpx.Response(200, json={
            "meta": {"code": 200}, "result": {"items": items},
        })

    provider = DgisGeoProvider("p", "r", httpx.MockTransport(ambiguous))
    assert provider.resolve_catalog_place("moscow", "Смотровая башня") is None


def test_catalog_resolver_matches_distinctive_tokens_with_extra_provider_words():
    def tsaritsyno(request):
        if request.url.params.get("q") == "Москва":
            items = [{"id": "city", "name": "Москва",
                      "point": {"lat": 55.7558, "lon": 37.6173}}]
        else:
            items = [{
                "id": "4504128908926178", "city_alias": "moscow",
                "name": "Государственный музей-заповедник Царицыно, парк",
                "point": {"lat": 55.615, "lon": 37.683},
            }]
        return httpx.Response(200, json={
            "meta": {"code": 200}, "result": {"items": items},
        })

    provider = DgisGeoProvider("p", "r", httpx.MockTransport(tsaritsyno))
    resolved = provider.resolve_catalog_place("moscow", "Парк Царицыно")
    assert resolved is not None
    assert resolved.dgis_place_id == "4504128908926178"
    assert resolved.provider_name == "Государственный музей-заповедник Царицыно, парк"


def test_catalog_resolver_does_not_match_only_generic_park_or_museum_token():
    def generic_only(request):
        if request.url.params.get("q") == "Москва":
            items = [{"id": "city", "name": "Москва",
                      "point": {"lat": 55.7558, "lon": 37.6173}}]
        else:
            items = [{
                "id": "wrong", "city_alias": "moscow", "name": "Парк Горького",
                "point": {"lat": 55.73, "lon": 37.60},
            }]
        return httpx.Response(200, json={
            "meta": {"code": 200}, "result": {"items": items},
        })

    provider = DgisGeoProvider("p", "r", httpx.MockTransport(generic_only))
    assert provider.resolve_catalog_place("moscow", "Парк Победы") is None


def test_catalog_resolver_uses_alias_only_after_main_name_fails():
    queries = []

    def alias_result(request):
        query = request.url.params.get("q")
        queries.append(query)
        if query == "Москва":
            items = [{"id": "city", "name": "Москва",
                      "point": {"lat": 55.7558, "lon": 37.6173}}]
        elif query == "ГМИИ им. Пушкина, Москва":
            items = []
        else:
            items = [{
                "id": "pushkin", "city_alias": "moscow",
                "name": "Государственный музей изобразительных искусств имени Пушкина",
                "point": {"lat": 55.747, "lon": 37.605},
            }]
        return httpx.Response(200, json={
            "meta": {"code": 200}, "result": {"items": items},
        })

    provider = DgisGeoProvider("p", "r", httpx.MockTransport(alias_result))
    resolved = provider.resolve_catalog_place(
        "moscow", "ГМИИ им. Пушкина",
        ("Государственный музей изобразительных искусств имени Пушкина",),
    )
    assert resolved is not None and resolved.dgis_place_id == "pushkin"
    assert queries == [
        "Москва", "ГМИИ им. Пушкина, Москва",
        "Государственный музей изобразительных искусств имени Пушкина, Москва",
    ]


def test_catalog_resolver_never_queries_composite_display_name_literally():
    queries = []

    def composite(request):
        query = request.url.params.get("q")
        queries.append(query)
        if query == "Москва":
            items = [{"id": "city", "name": "Москва",
                      "point": {"lat": 55.7558, "lon": 37.6173}}]
        else:
            items = [{"id": "kitay", "name": "Китай-город", "city_alias": "moscow",
                      "point": {"lat": 55.755, "lon": 37.635}}]
        return httpx.Response(200, json={
            "meta": {"code": 200}, "result": {"items": items},
        })

    provider = DgisGeoProvider("p", "r", httpx.MockTransport(composite))
    assert provider.resolve_catalog_place(
        "moscow", "Китай-город / Варварка", ("Китай-город", "Улица Варварка"),
    ) is not None
    assert "Китай-город / Варварка, Москва" not in queries
    assert queries[-1] == "Китай-город, Москва"


def test_catalog_resolver_restores_provider_name_by_confirmed_id():
    def by_id(request):
        if request.url.params.get("q") == "Москва":
            items = [{
                "id": "city", "name": "Москва",
                "point": {"lat": 55.7558, "lon": 37.6173},
            }]
        else:
            assert request.url.path.endswith("/items/byid")
            assert request.url.params.get("id") == "confirmed-id"
            items = [{
                "id": "confirmed-id", "name": "Фактическое имя 2ГИС",
                "city_alias": "moscow", "point": {"lat": 55.75, "lon": 37.62},
            }]
        return httpx.Response(200, json={
            "meta": {"code": 200}, "result": {"items": items},
        })

    provider = DgisGeoProvider("p", "r", httpx.MockTransport(by_id))
    resolved = provider.resolve_catalog_place_by_id("moscow", "confirmed-id")
    assert resolved is not None
    assert resolved.dgis_place_id == "confirmed-id"
    assert resolved.provider_name == "Фактическое имя 2ГИС"


def test_automatic_search_rejects_ritual_and_unrelated_branches():
    def mixed(request):
        items = [
            {"id": "ritual", "name": "Ритуал, бюро ритуальных услуг",
             "point": {"lat": 54.194, "lon": 37.618},
             "rubrics": [{"name": "Ритуальные услуги"}], "is_routing_available": True},
            {"id": "shop", "name": "Магазин у дома",
             "point": {"lat": 54.195, "lon": 37.619},
             "rubrics": [{"name": "Продукты"}], "is_routing_available": True},
            {"id": "museum", "name": "Музей оружия",
             "point": {"lat": 54.196, "lon": 37.620},
             "rubrics": [{"name": "Музеи"}], "is_routing_available": True},
        ]
        return httpx.Response(200, json={"meta": {"code": 200}, "result": {"items": items}})
    provider = DgisGeoProvider("p", "r", httpx.MockTransport(mixed))
    area = provider.resolve_search_area("tula", "центр", (54.193, 37.617))
    places = provider.search_places("tula", preview(), area)
    assert [place.placeId for place in places] == ["museum"]


def test_hard_exclusion_is_applied_after_2gis_returns_candidates():
    def museum(request):
        items = [{
            "id": "museum", "name": "Городской музей",
            "point": {"lat": 54.196, "lon": 37.619},
            "rubrics": [{"name": "Музеи"}], "schedule": {"is_24x7": True},
            "is_routing_available": True,
        }]
        return httpx.Response(200, json={"meta": {"code": 200},
                                        "result": {"items": items}})

    provider = DgisGeoProvider("p", "r", httpx.MockTransport(museum))
    no_museums = preview().model_copy(update={"hardExclusions": ["MUSEUMS"]})
    area = provider.resolve_search_area("tula", "центр", (54.193, 37.617))
    assert provider.search_places("tula", no_museums, area) == []


def test_food_search_does_not_turn_unrelated_branch_into_restaurant():
    def unrelated(request):
        item = {"id": "ritual", "name": "Ритуальные услуги",
                "point": {"lat": 54.194, "lon": 37.618},
                "rubrics": [{"name": "Ритуальные услуги"}], "is_routing_available": True}
        return httpx.Response(200, json={"meta": {"code": 200}, "result": {"items": [item]}})
    provider = DgisGeoProvider("p", "r", httpx.MockTransport(unrelated))
    food_preview = preview().model_copy(update={"includeFood": True})
    area = provider.resolve_search_area("tula", "центр", (54.193, 37.617))
    assert provider.search_places("tula", food_preview, area) == []


def test_resolve_places_batches_ids_and_restores_requested_order():
    calls = []
    def by_id(request):
        calls.append(request)
        if request.url.params.get("q") == "Тула":
            items = [{"id": "city", "name": "Тула", "point": {"lat": 54.193, "lon": 37.617}}]
        else:
            assert request.url.path.endswith("/items/byid")
            assert request.url.params.get("id") == "first,second"
            items = [
                {"id": "first", "name": "Кремль", "city_alias": "tula",
                 "point": {"lat": 54.196, "lon": 37.619}, "is_routing_available": True},
                {"id": "second", "name": "Набережная", "city_alias": "tula",
                 "point": {"lat": 54.197, "lon": 37.62}, "is_routing_available": True},
            ]
        return httpx.Response(200, json={"meta": {"code": 200}, "result": {"items": items}})
    provider = DgisGeoProvider("p", "r", httpx.MockTransport(by_id))
    resolved = provider.resolve_places("tula", ["second", "first"])
    assert [item.placeId for item in resolved] == ["second", "first"]
    assert len(calls) == 2


def test_resolve_places_rejects_another_city():
    def foreign(request):
        if request.url.params.get("q") == "Тула":
            items = [{"id": "city", "name": "Тула", "point": {"lat": 54.193, "lon": 37.617}}]
        else:
            items = [{"id": "foreign", "name": "Чужое место", "city_alias": "moscow",
                      "point": {"lat": 55.7558, "lon": 37.6173}}]
        return httpx.Response(200, json={"meta": {"code": 200}, "result": {"items": items}})
    provider = DgisGeoProvider("p", "r", httpx.MockTransport(foreign))
    with pytest.raises(GeoPlaceNotFound):
        provider.resolve_places("tula", ["foreign"])


def test_direction_and_named_area_become_explicit_search_anchors():
    provider = DgisGeoProvider("p", "r", httpx.MockTransport(response))
    center = (54.193, 37.617)
    north = provider.resolve_search_area("tula", "север города", center)
    named = provider.resolve_search_area("tula", "Заречье", center)
    assert north.source == "direction" and north.lat > center[0]
    assert north.label == "Север города"
    assert named.source == "2gis" and named.label == "Заречье, Тула"


def test_named_start_prefers_best_text_match_not_first_catalog_item():
    def stations(request):
        items = [
            {"id": "wrong", "name": "Кутузовский проспект",
             "full_name": "Москва, Кутузовский проспект", "point": {"lat": 55.74, "lon": 37.55}},
            {"id": "right", "name": "Кутузовская",
             "full_name": "МЦК Кутузовская, Москва", "point": {"lat": 55.74, "lon": 37.534}},
        ]
        return httpx.Response(200, json={"meta": {"code": 200}, "result": {"items": items}})
    provider = DgisGeoProvider("p", "r", httpx.MockTransport(stations))
    area = provider.resolve_search_area(
        "moscow", "МЦК Кутузовская", (55.7558, 37.6173),
    )
    assert area.label == "МЦК Кутузовская, Москва"
    assert area.lon == 37.534


def test_places_and_routing_results_are_cached():
    calls = {"places": 0, "routing": 0}
    def capture(request):
        calls["places" if request.url.host == "catalog.api.2gis.com" else "routing"] += 1
        return response(request)
    provider = DgisGeoProvider("p", "r", httpx.MockTransport(capture))
    provider.resolve_city_center("tula")
    provider.resolve_city_center("tula")
    provider.walking_leg((54.193, 37.617), (54.196, 37.619), 0, 1)
    provider.walking_leg((54.193, 37.617), (54.196, 37.619), 4, 5)
    assert calls == {"places": 1, "routing": 1}


def test_upstream_calls_are_globally_paced_when_enabled():
    now, sleeps = [100.0], []

    def sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={}))
    provider = DgisGeoProvider("p", "r", transport, sleeper=sleep, clock=lambda: now[0])
    provider.min_request_interval = 0.75
    provider._request("GET", "https://catalog.api.2gis.com/test")
    provider._request("GET", "https://catalog.api.2gis.com/test")
    assert sleeps == [0.75]


def test_rate_limit_does_not_retry_and_opens_circuit(monkeypatch):
    monkeypatch.setenv("DGIS_MAX_RETRIES", "1")
    calls, sleeps = [], []
    def limited(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "3"}, json={})
    provider = DgisGeoProvider("p", "r", httpx.MockTransport(limited),
                                sleeper=sleeps.append, clock=lambda: 100.0)
    with pytest.raises(GeoRateLimited) as first:
        provider.resolve_city_center("tula")
    assert first.value.retry_after_seconds == 3
    assert sleeps == [] and len(calls) == 1
    with pytest.raises(GeoRateLimited):
        provider.resolve_city_center("tula")
    assert len(calls) == 1


@pytest.mark.parametrize("status,error", [
    (401, GeoAuthenticationError), (403, GeoAuthenticationError),
    (500, GeoUnavailable), (503, GeoUnavailable),
])
def test_provider_errors_never_become_fake_places(status, error):
    transport = httpx.MockTransport(lambda request: httpx.Response(status, json={}))
    provider = DgisGeoProvider("p", "r", transport)
    with pytest.raises(error):
        provider.resolve_city_center("tula")


def test_provider_timeout_is_unavailable():
    def timeout(request):
        raise httpx.ReadTimeout("temporary timeout", request=request)

    provider = DgisGeoProvider("p", "r", httpx.MockTransport(timeout), sleeper=lambda _: None)
    provider.max_retries = 0
    with pytest.raises(GeoUnavailable):
        provider.resolve_city_center("tula")


def test_routing_without_geometry_is_rejected():
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={
        "status": "OK", "result": [{"total_distance": 20, "total_duration": 10}]}))
    with pytest.raises(GeoInvalidResponse):
        DgisGeoProvider("p", "r", transport).walking_leg((1, 2), (3, 4), 0, 1)


def test_missing_pedestrian_route_is_explicit():
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={
        "status": "ROUTE_NOT_FOUND", "result": []}))
    with pytest.raises(GeoRouteNotFound):
        DgisGeoProvider("p", "r", transport).walking_leg((1, 2), (3, 4), 0, 1)

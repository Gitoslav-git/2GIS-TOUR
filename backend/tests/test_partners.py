from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient

from gulyay.api import (app, get_geo_provider, get_partner_registry,
                        get_route_repository)
from gulyay.geo import (DgisGeoProvider, GeoRouteNotFound, GeoUnavailable,
                        PartnerBranch, clear_geo_caches)
from gulyay.models import (CreateRoute, Filters, Route, RouteLeg, RoutePoint,
                           SearchArea, WalkPosition, WalkSession, WalkState)
from gulyay.partners import PartnerOfferSelector, PartnerRegistry
from gulyay.repository import RouteRepository


NOW = datetime(2026, 10, 14, 12, tzinfo=timezone.utc)


class FakePartnerGeo:
    def __init__(self, branches=None, duration_seconds=240, unavailable=False):
        self.branches = branches if branches is not None else [PartnerBranch(
            dgis_place_id="branch-1", dgis_brand_id="verified-cofix",
            name="Cofix на Тверской", lat=55.76, lon=37.61,
            schedule={"is_24x7": True},
        )]
        self.duration_seconds = duration_seconds
        self.unavailable = unavailable
        self.search_calls = 0
        self.routing_calls = 0

    def search_partner_branches(self, city_id, dgis_brand_id, origin):
        self.search_calls += 1
        if self.unavailable:
            raise GeoUnavailable()
        return self.branches

    def walking_leg(self, start, end, from_order, to_order):
        self.routing_calls += 1
        if self.duration_seconds is None:
            raise GeoRouteNotFound()
        return RouteLeg(
            fromOrder=from_order, toOrder=to_order, distanceMeters=350,
            durationSeconds=self.duration_seconds,
            geometry=[[start[1], start[0]], [end[1], end[0]]],
        )


def visiting_state(*, status="ACTIVE", phase="VISITING", age_seconds=5,
                   accuracy=10) -> WalkState:
    session = WalkSession(
        walkId=uuid4(), routeId=uuid4(), routeVersion=1, status=status,
        currentPointOrder=1, startedAt=NOW - timedelta(hours=1),
        estimatedRemainingMinutes=60, phase=phase,
        visitStartedAt=NOW - timedelta(minutes=2), visitElapsedSeconds=120,
    )
    position = WalkPosition(
        lat=55.7558, lon=37.6173, accuracyMeters=accuracy,
        measuredAt=NOW - timedelta(seconds=age_seconds),
    )
    return WalkState(
        session=session, lastMeasuredAt=position.measuredAt, lastPosition=position,
    )


def activate_test_cofix(registry: PartnerRegistry, *, status="ACTIVE") -> None:
    assert registry.confirm_brand_id("cofix", "moscow", "verified-cofix")
    assert registry.set_brand_commercial_state(
        "cofix", "moscow", "ACTIVE", True, True,
    )
    registry.save_offer(
        offer_id="test_cofix_moscow_001", partner_brand_id="cofix",
        city_id="moscow", title="Зайти за кофе?",
        description=("Обычное посещение кофейни. Скидки, бонусы и промокоды "
                     "не предусмотрены."),
        valid_from=datetime(2026, 10, 13, tzinfo=timezone(timedelta(hours=3))),
        valid_until=datetime(2026, 12, 31, 23, 59, 59,
                             tzinfo=timezone(timedelta(hours=3))),
        timezone_name="Europe/Moscow", button_text="Открыть в 2ГИС",
        status=status,
    )


def test_registry_creation_and_seed_are_idempotent_and_inactive(tmp_path):
    path = tmp_path / "partners.sqlite3"
    first = PartnerRegistry(path)
    assert len(first.list_brands("moscow")) == 9
    assert all(brand.partnership_status == "CANDIDATE"
               and not brand.is_active_partner
               and not brand.partner_discovery_enabled
               and brand.dgis_brand_id is None
               for brand in first.list_brands("moscow"))
    first.confirm_brand_id("cofix", "moscow", "manually-verified")
    first.close()
    second = PartnerRegistry(path)
    assert len(second.list_brands("moscow")) == 9
    assert second.get_brand("cofix", "moscow").dgis_brand_id == "manually-verified"
    second.close()


def test_no_active_partner_returns_none_without_2gis_call():
    registry = PartnerRegistry(":memory:")
    geo = FakePartnerGeo()
    assert PartnerOfferSelector(registry, geo).select(
        visiting_state(), "moscow", NOW,
    ) is None
    assert geo.search_calls == 0 and geo.routing_calls == 0
    registry.close()


def test_candidate_or_offer_without_active_status_never_calls_2gis():
    registry = PartnerRegistry(":memory:")
    activate_test_cofix(registry, status="PAUSED")
    geo = FakePartnerGeo()
    assert PartnerOfferSelector(registry, geo).select(
        visiting_state(), "moscow", NOW,
    ) is None
    assert geo.search_calls == 0
    registry.close()


def test_valid_synthetic_offer_uses_verified_walking_time_and_2gis_action():
    registry = PartnerRegistry(":memory:")
    activate_test_cofix(registry)
    geo = FakePartnerGeo(duration_seconds=301)
    offer = PartnerOfferSelector(registry, geo).select(
        visiting_state(), "moscow", NOW,
    )
    assert offer is not None
    assert offer.offerId == "test_cofix_moscow_001"
    assert offer.venueName == "Cofix на Тверской"
    assert offer.walkingMinutes == 6
    assert offer.isCommercial is True
    assert offer.action.url == "https://2gis.ru/moscow/firm/branch-1"
    assert geo.search_calls == 1 and geo.routing_calls == 1
    registry.close()


def test_non_visiting_stale_or_inaccurate_position_hides_offer():
    registry = PartnerRegistry(":memory:")
    activate_test_cofix(registry)
    for state in (
        visiting_state(phase="MOVING"),
        visiting_state(status="PAUSED"),
        visiting_state(age_seconds=61),
        visiting_state(accuracy=51),
    ):
        geo = FakePartnerGeo()
        assert PartnerOfferSelector(registry, geo).select(state, "moscow", NOW) is None
        assert geo.search_calls == 0
    registry.close()


def test_closed_far_and_unroutable_branch_are_rejected():
    registry = PartnerRegistry(":memory:")
    activate_test_cofix(registry)
    closed = [PartnerBranch(
        dgis_place_id="closed", dgis_brand_id="verified-cofix", name="Cofix",
        lat=55.76, lon=37.61,
        schedule={"Mon": {"working_hours": [{"from": "01:00", "to": "02:00"}]}},
    )]
    assert PartnerOfferSelector(registry, FakePartnerGeo(closed, 120)).select(
        visiting_state(), "moscow", NOW,
    ) is None
    assert PartnerOfferSelector(registry, FakePartnerGeo(duration_seconds=601)).select(
        visiting_state(), "moscow", NOW,
    ) is None
    assert PartnerOfferSelector(registry, FakePartnerGeo(duration_seconds=None)).select(
        visiting_state(), "moscow", NOW,
    ) is None
    registry.close()


def test_multiple_branches_choose_preferred_then_shortest():
    registry = PartnerRegistry(":memory:")
    activate_test_cofix(registry)
    branches = [PartnerBranch(
        dgis_place_id=value, dgis_brand_id="verified-cofix", name=f"Cofix {value}",
        lat=55.76 + index * .001, lon=37.61, schedule={"is_24x7": True},
    ) for index, value in enumerate(("six", "four"))]

    class VariableGeo(FakePartnerGeo):
        def walking_leg(self, start, end, from_order, to_order):
            seconds = 360 if end[0] == branches[0].lat else 240
            return RouteLeg(fromOrder=0, toOrder=1, distanceMeters=300,
                            durationSeconds=seconds,
                            geometry=[[start[1], start[0]], [end[1], end[0]]])

    offer = PartnerOfferSelector(registry, VariableGeo(branches)).select(
        visiting_state(), "moscow", NOW,
    )
    assert offer is not None and offer.dgisPlaceId == "four"
    registry.close()


def test_provider_brand_search_requires_exact_returned_brand_id():
    clear_geo_caches()
    requests = []

    def response(request):
        requests.append(request)
        if request.url.params.get("q") == "Москва":
            items = [{"id": "city", "name": "Москва",
                      "point": {"lat": 55.7558, "lon": 37.6173}}]
        else:
            items = [
                {"id": "right", "name": "Cofix", "city_alias": "moscow",
                 "brand": {"id": "verified-cofix", "name": "Cofix"},
                 "point": {"lat": 55.756, "lon": 37.618},
                 "schedule": {"is_24x7": True}, "is_routing_available": True},
                {"id": "wrong", "name": "Похожее кафе", "city_alias": "moscow",
                 "brand": {"id": "another-brand", "name": "Cofix"},
                 "point": {"lat": 55.757, "lon": 37.619},
                 "schedule": {"is_24x7": True}, "is_routing_available": True},
            ]
        return httpx.Response(200, json={"meta": {"code": 200},
                                         "result": {"items": items}})

    provider = DgisGeoProvider("places", "routing", httpx.MockTransport(response))
    branches = provider.search_partner_branches(
        "moscow", "verified-cofix", (55.7558, 37.6173),
    )
    assert [branch.dgis_place_id for branch in branches] == ["right"]
    search = requests[-1]
    assert search.url.params["brand_id"] == "verified-cofix"
    assert search.url.params["type"] == "branch"
    assert search.url.params["sort"] == "distance"


def test_admin_discovery_does_not_guess_and_confirmation_revalidates_id():
    clear_geo_caches()

    def response(request):
        if request.url.params.get("q") == "Москва":
            items = [{"id": "city", "name": "Москва",
                      "point": {"lat": 55.7558, "lon": 37.6173}}]
        else:
            items = [{
                "id": "branch", "name": "Cofix", "city_alias": "moscow",
                "brand": {"id": "verified-cofix", "name": "Cofix"},
                "point": {"lat": 55.756, "lon": 37.618},
            }]
        return httpx.Response(200, json={"meta": {"code": 200},
                                         "result": {"items": items}})

    provider = DgisGeoProvider("places", "routing", httpx.MockTransport(response))
    candidates = provider.discover_partner_brand_candidates("moscow", "Cofix")
    assert [(item.dgis_brand_id, item.name_matches)
            for item in candidates] == [("verified-cofix", True)]
    assert provider.verify_partner_brand_id(
        "moscow", "Cofix", "verified-cofix",
    ) is True
    assert provider.verify_partner_brand_id(
        "moscow", "Другая сеть", "verified-cofix",
    ) is False


def test_batch_reference_lookup_extracts_brand_id_and_never_substitutes_org_id():
    clear_geo_caches()
    requests = []

    def response(request):
        requests.append(request)
        items = [
            {"id": "branch-with-brand", "name": "Cofix", "city_alias": "moscow",
             "brand": {"id": "brand-cofix", "name": "Cofix"},
             "org": {"id": "org-cofix", "name": "Cofix LLC"},
             "point": {"lat": 55.75, "lon": 37.61}},
            {"id": "branch-with-org-only", "name": "Restaurant", "city_alias": "moscow",
             "org": {"id": "org-only", "name": "Restaurant LLC"},
             "point": {"lat": 55.76, "lon": 37.62}},
        ]
        return httpx.Response(200, json={"meta": {"code": 200},
                                         "result": {"items": items}})

    provider = DgisGeoProvider("places", "routing", httpx.MockTransport(response))
    found = provider.resolve_partner_brand_references(
        ["branch-with-brand", "branch-with-org-only"],
    )
    assert found["branch-with-brand"].dgis_brand_id == "brand-cofix"
    assert found["branch-with-brand"].dgis_org_id == "org-cofix"
    assert found["branch-with-org-only"].dgis_brand_id is None
    assert found["branch-with-org-only"].dgis_org_id == "org-only"
    assert len(requests) == 1
    assert requests[0].url.path.endswith("/3.0/items/byid")
    assert requests[0].url.params["id"] == "branch-with-brand,branch-with-org-only"
    assert "items.brand" in requests[0].url.params["fields"]


def test_reference_match_rejects_wrong_city_and_ambiguous_brand_name():
    clear_geo_caches()

    def response(request):
        return httpx.Response(200, json={"meta": {"code": 200}, "result": {"items": [
            {"id": "city", "name": "Москва", "point": {"lat": 55.7558, "lon": 37.6173}},
        ]}})

    provider = DgisGeoProvider("places", "routing", httpx.MockTransport(response))
    from gulyay.geo import PartnerBrandReference
    wrong_city = PartnerBrandReference(
        "branch", "Cofix", "brand", "Cofix", "org", "tula", 54.19, 37.61, 1,
    )
    wrong_name = PartnerBrandReference(
        "branch", "Другое", "brand", "Другое", "org", "moscow", 55.75, 37.61, 1,
    )
    assert provider.partner_reference_matches(wrong_city, "moscow", "Cofix") is False
    assert provider.partner_reference_matches(wrong_name, "moscow", "Cofix") is False


def test_batch_reference_lookup_rejects_multiple_brand_values():
    clear_geo_caches()

    def response(request):
        item = {"id": "ambiguous", "name": "Shared branch", "city_alias": "moscow",
                "brand": [{"id": "brand-one", "name": "One"},
                          {"id": "brand-two", "name": "Two"}],
                "point": {"lat": 55.75, "lon": 37.61}}
        return httpx.Response(200, json={"meta": {"code": 200},
                                         "result": {"items": [item]}})

    provider = DgisGeoProvider("places", "routing", httpx.MockTransport(response))
    reference = provider.resolve_partner_brand_references(["ambiguous"])["ambiguous"]
    assert reference.brand_count == 2
    assert reference.dgis_brand_id is None
    assert reference.dgis_org_id is None


def test_verified_brand_id_cannot_be_silently_replaced():
    registry = PartnerRegistry(":memory:")
    assert registry.confirm_brand_id("cofix", "moscow", "brand-one") is True
    assert registry.confirm_brand_id("cofix", "moscow", "brand-two") is False
    brand = registry.get_brand("cofix", "moscow")
    assert brand.dgis_brand_id == "brand-one"
    assert brand.dgis_id_status == "VERIFIED"
    registry.close()


def route_for_api():
    return Route(
        routeId=uuid4(), routeVersion=1, status="READY", cityId="moscow",
        query="Прогулка по Москве", filters=Filters(),
        searchArea=SearchArea(label="Москва", lat=55.7558, lon=37.6173,
                              radiusMeters=12000, source="city"),
        approximateStart=True, requestedMinutes=120, totalMinutes=60,
        unusedMinutes=60,
        points=[RoutePoint(order=1, placeId="point", name="Точка", lat=55.75,
                           lon=37.61, visitMinutes=40, scheduleStatus="OPEN",
                           isFood=False)],
        legs=[RouteLeg(fromOrder=0, toOrder=1, distanceMeters=300,
                       durationSeconds=240,
                       geometry=[[37.60, 55.74], [37.61, 55.75]])], warnings=[],
    )


def test_partner_endpoint_checks_owner_and_fails_closed_on_provider_error(tmp_path):
    repository = RouteRepository(tmp_path / "routes.sqlite3")
    registry = PartnerRegistry(tmp_path / "routes.sqlite3")
    activate_test_cofix(registry)
    owner, stranger = uuid4(), uuid4()
    route = route_for_api()
    repository.save_new(route, owner, CreateRoute(
        cityId="moscow", query="Прогулка по Москве", deviceSessionId=owner,
    ))
    state = visiting_state()
    fresh_position = WalkPosition(
        lat=55.7558, lon=37.6173, accuracyMeters=10,
        measuredAt=datetime.now(timezone.utc),
    )
    state = state.model_copy(update={"session": state.session.model_copy(update={
        "routeId": route.routeId,
    }), "lastMeasuredAt": fresh_position.measuredAt,
        "lastPosition": fresh_position})
    repository.save_walk(state, owner)
    app.dependency_overrides[get_route_repository] = lambda: repository
    app.dependency_overrides[get_partner_registry] = lambda: registry
    app.dependency_overrides[get_geo_provider] = lambda: FakePartnerGeo(unavailable=True)
    try:
        client = TestClient(app)
        denied = client.get(
            f"/v1/walks/{state.session.walkId}/partner-offer",
            headers={"X-Device-Session": str(stranger)},
        )
        assert denied.status_code == 404
        response = client.get(
            f"/v1/walks/{state.session.walkId}/partner-offer",
            headers={"X-Device-Session": str(owner)},
        )
        assert response.status_code == 200
        assert response.json() == {"status": "PROVIDER_UNAVAILABLE", "offer": None}
        app.dependency_overrides[get_geo_provider] = lambda: FakePartnerGeo(
            duration_seconds=240,
        )
        available = client.get(
            f"/v1/walks/{state.session.walkId}/partner-offer",
            headers={"X-Device-Session": str(owner)},
        )
        assert available.status_code == 200
        body = available.json()
        assert body["status"] == "AVAILABLE"
        assert body["offer"]["offerId"] == "test_cofix_moscow_001"
        assert body["offer"]["walkingMinutes"] == 4
        assert body["offer"]["action"]["url"].endswith("/branch-1")
    finally:
        app.dependency_overrides.clear()
        registry.close()
        repository.close()

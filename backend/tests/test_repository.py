from uuid import uuid4

from gulyay.models import (CreateRoute, Filters, Route, RouteLeg, RoutePoint,
                           SearchArea, StartWalk)
from gulyay.repository import RouteRepository
from gulyay.walk import start_walk


def route(route_id, version=1):
    return Route(
        routeId=route_id, routeVersion=version, status="READY", cityId="tula",
        query="История три часа", filters=Filters(),
        searchArea=SearchArea(label="Центр города", lat=54.193, lon=37.617,
                              radiusMeters=3500, source="city"),
        approximateStart=True, requestedMinutes=180, totalMinutes=168, unusedMinutes=12,
        points=[RoutePoint(order=1, placeId="2gis-1", name="Кремль", lat=54.19,
                           lon=37.61, visitMinutes=40, scheduleStatus="OPEN", isFood=False)],
        legs=[RouteLeg(fromOrder=0, toOrder=1, distanceMeters=300,
                       durationSeconds=240, geometry=[[37.61, 54.19], [37.62, 54.20]])],
        warnings=[],
    )


def test_route_survives_repository_reopen(tmp_path):
    path = tmp_path / "routes.sqlite3"
    owner, route_id = uuid4(), uuid4()
    payload = CreateRoute(cityId="tula", query="История три часа", deviceSessionId=owner)
    first = RouteRepository(path)
    first.save_new(route(route_id), owner, payload)
    first.close()

    reopened = RouteRepository(path)
    stored = reopened.get(route_id, owner)
    assert stored is not None
    assert stored[0].routeId == route_id and stored[0].routeVersion == 1
    assert stored[1].query == "История три часа"
    reopened.close()


def test_atomic_replace_rejects_stale_version():
    repository = RouteRepository(":memory:")
    owner, route_id = uuid4(), uuid4()
    payload = CreateRoute(cityId="tula", query="История три часа", deviceSessionId=owner)
    repository.save_new(route(route_id), owner, payload)
    assert repository.replace(route(route_id, 2), owner, payload, base_version=1) is True
    assert repository.replace(route(route_id, 2), owner, payload, base_version=1) is False
    assert repository.get(route_id, owner)[0].routeVersion == 2
    assert repository.get_version(route_id, owner, 1).routeVersion == 1
    assert repository.get_version(route_id, owner, 2).routeVersion == 2


def test_expired_guest_route_is_not_returned(monkeypatch):
    monkeypatch.setenv("GULYAY_ROUTE_RETENTION_HOURS", "1")
    repository = RouteRepository(":memory:")
    owner, route_id = uuid4(), uuid4()
    payload = CreateRoute(cityId="tula", query="История три часа", deviceSessionId=owner)
    repository.save_new(route(route_id), owner, payload)
    with repository._connection:
        repository._connection.execute(
            "UPDATE routes SET updated_at = datetime('now', '-2 hours') WHERE route_id = ?",
            (str(route_id),),
        )
    assert repository.get(route_id, owner) is None


def test_walk_state_is_persisted_and_removed_with_route():
    repository = RouteRepository(":memory:")
    owner, route_id = uuid4(), uuid4()
    itinerary = route(route_id)
    payload = CreateRoute(cityId="tula", query="История три часа", deviceSessionId=owner)
    repository.save_new(itinerary, owner, payload)
    walk = start_walk(itinerary, StartWalk(routeVersion=1))
    repository.save_walk(walk, owner)
    assert repository.get_walk(walk.session.walkId, owner) is not None
    assert repository.find_active_walk(owner).session.walkId == walk.session.walkId
    assert repository.delete(route_id, owner) is True
    assert repository.get_walk(walk.session.walkId, owner) is None

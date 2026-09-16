"""2GIS Places and Routing adapters with bounded retries and TTL caches.

Only responses received from 2GIS are converted into places and route legs.
There is deliberately no straight-line or synthetic-place fallback.
"""
from __future__ import annotations

import math
import os
import re
import threading
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Callable, Protocol

import httpx

from .models import PlaceCandidate, QueryPreview, RouteLeg, SearchArea


class GeoUnavailable(Exception):
    """2GIS is not configured or cannot be reached."""


class GeoAuthenticationError(GeoUnavailable):
    """2GIS rejected a server API key."""


class GeoInvalidResponse(GeoUnavailable):
    """2GIS returned an unusable response."""


class GeoRateLimited(GeoUnavailable):
    """2GIS temporarily rejected traffic because its request limit was reached."""

    def __init__(self, retry_after_seconds: int = 30):
        super().__init__("2GIS request limit reached")
        self.retry_after_seconds = max(1, retry_after_seconds)


class GeoConstraintNotFound(Exception):
    """A user-supplied city area or landmark cannot be resolved safely."""


class GeoRouteNotFound(Exception):
    """No pedestrian path exists between the supplied points."""


class GeoPlaceNotFound(Exception):
    """One or more supplied provider place IDs are missing or outside the city."""


class GeoProvider(Protocol):
    def ensure_configured(self) -> None: ...
    def resolve_city_center(self, city_id: str) -> tuple[float, float]: ...
    def resolve_search_area(self, city_id: str, location_hint: str | None,
                            city_center: tuple[float, float]) -> SearchArea: ...
    def search_places(self, city_id: str, preview: QueryPreview,
                      area: SearchArea) -> list[PlaceCandidate]: ...
    def search_candidates(self, city_id: str, query: str) -> list[PlaceCandidate]: ...
    def resolve_places(self, city_id: str, place_ids: list[str]) -> list[PlaceCandidate]: ...
    def walking_leg(self, start: tuple[float, float], end: tuple[float, float],
                    from_order: int, to_order: int) -> RouteLeg: ...


CITY_NAMES = {"tula": "Тула", "vladimir": "Владимир"}
PLACES_URL = "https://catalog.api.2gis.com/3.0/items"
PLACES_BY_ID_URL = "https://catalog.api.2gis.com/3.0/items/byid"
ROUTING_URL = "https://routing.api.2gis.com/routing/7.0.0/global"


@dataclass
class _CacheEntry:
    expires_at: float
    value: object


class _TtlCache:
    def __init__(self):
        self._values: dict[object, _CacheEntry] = {}
        self._lock = threading.Lock()

    def get(self, key: object, now: float) -> object | None:
        with self._lock:
            entry = self._values.get(key)
            if entry is None:
                return None
            if entry.expires_at <= now:
                self._values.pop(key, None)
                return None
            return entry.value

    def put(self, key: object, value: object, expires_at: float) -> None:
        with self._lock:
            self._values[key] = _CacheEntry(expires_at, value)

    def clear(self) -> None:
        with self._lock:
            self._values.clear()


_PLACES_CACHE = _TtlCache()
_ROUTING_CACHE = _TtlCache()
_UPSTREAM_SLOTS = threading.BoundedSemaphore(2)
_RATE_LIMIT_LOCK = threading.Lock()
_RATE_LIMITED_UNTIL = 0.0


def clear_geo_caches() -> None:
    """Test/support hook; production caches normally expire without manual clearing."""
    global _RATE_LIMITED_UNTIL
    _PLACES_CACHE.clear()
    _ROUTING_CACHE.clear()
    with _RATE_LIMIT_LOCK:
        _RATE_LIMITED_UNTIL = 0.0


class DgisGeoProvider:
    def __init__(self, places_key: str | None = None, routing_key: str | None = None,
                 transport: httpx.BaseTransport | None = None,
                 sleeper: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic):
        self.places_key = places_key if places_key is not None else os.getenv("DGIS_PLACES_API_KEY")
        self.routing_key = routing_key if routing_key is not None else os.getenv("DGIS_ROUTING_API_KEY")
        self.transport = transport
        self.sleeper = sleeper
        self.clock = clock
        self.max_retries = _bounded_int("DGIS_MAX_RETRIES", 2, 0, 4)
        self.places_ttl = _bounded_int("DGIS_PLACES_CACHE_SECONDS", 900, 60, 86400)
        self.routing_ttl = _bounded_int("DGIS_ROUTING_CACHE_SECONDS", 1800, 60, 86400)

    def ensure_configured(self) -> None:
        if not self.places_key or not self.routing_key:
            raise GeoUnavailable("DGIS_PLACES_API_KEY and DGIS_ROUTING_API_KEY must be configured")

    def _client(self) -> httpx.Client:
        return httpx.Client(timeout=12.0, transport=self.transport,
                            headers={"User-Agent": "Gulyay-Backend/0.5"})

    def _request(self, method: str, url: str, **kwargs) -> dict:
        global _RATE_LIMITED_UNTIL
        self.ensure_configured()
        for attempt in range(self.max_retries + 1):
            now = self.clock()
            with _RATE_LIMIT_LOCK:
                remaining = math.ceil(_RATE_LIMITED_UNTIL - now)
            if remaining > 0:
                raise GeoRateLimited(remaining)
            try:
                with _UPSTREAM_SLOTS:
                    with self._client() as client:
                        response = client.request(method, url, **kwargs)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt >= self.max_retries:
                    raise GeoUnavailable() from exc
                self.sleeper(min(0.5 * (2 ** attempt), 2.0))
                continue

            if response.status_code == 429:
                retry_after = _retry_after(response, default=min(2 ** attempt, 5))
                if attempt < self.max_retries:
                    self.sleeper(retry_after)
                    continue
                with _RATE_LIMIT_LOCK:
                    _RATE_LIMITED_UNTIL = max(_RATE_LIMITED_UNTIL, self.clock() + retry_after)
                raise GeoRateLimited(retry_after)
            if response.status_code in (502, 503, 504) and attempt < self.max_retries:
                self.sleeper(min(0.5 * (2 ** attempt), 2.0))
                continue
            return self._read_json(response)
        raise GeoUnavailable()

    @staticmethod
    def _read_json(response: httpx.Response) -> dict:
        if response.status_code in (401, 403):
            raise GeoAuthenticationError()
        if response.status_code >= 500:
            raise GeoUnavailable()
        if response.status_code >= 400:
            raise GeoInvalidResponse()
        try:
            data = response.json()
        except ValueError as exc:
            raise GeoInvalidResponse() from exc
        if not isinstance(data, dict):
            raise GeoInvalidResponse()
        return data

    def _places_from(self, url: str, **params: str | int | bool) -> list[dict]:
        cache_key = (url, tuple(sorted((key, str(value)) for key, value in params.items())))
        cached = _PLACES_CACHE.get(cache_key, self.clock())
        if isinstance(cached, list):
            return cached
        data = self._request("GET", url, params={"key": self.places_key, **params})
        meta, result = data.get("meta"), data.get("result")
        if not isinstance(meta, dict) or meta.get("code") != 200 or not isinstance(result, dict):
            raise GeoInvalidResponse()
        items = result.get("items")
        if not isinstance(items, list):
            raise GeoInvalidResponse()
        clean = [item for item in items if isinstance(item, dict)]
        _PLACES_CACHE.put(cache_key, clean, self.clock() + self.places_ttl)
        return clean

    def _places(self, **params: str | int | bool) -> list[dict]:
        return self._places_from(PLACES_URL, **params)

    def resolve_city_center(self, city_id: str) -> tuple[float, float]:
        city_name = CITY_NAMES[city_id]
        items = self._places(q=city_name, type="adm_div.city", locale="ru_RU",
                             fields="items.point", page_size=5,
                             search_is_query_text_complete="true")
        for item in items:
            if str(item.get("name", "")).casefold() != city_name.casefold():
                continue
            point = item.get("point")
            if _valid_point(point):
                return float(point["lat"]), float(point["lon"])
        raise GeoInvalidResponse("2GIS did not return the selected city center")

    def resolve_search_area(self, city_id: str, location_hint: str | None,
                            city_center: tuple[float, float]) -> SearchArea:
        if not location_hint:
            return SearchArea(label="Весь город", lat=city_center[0], lon=city_center[1],
                              radiusMeters=12000, source="city")
        normalized = location_hint.strip().casefold()
        if normalized == "центр":
            return SearchArea(label="Центр города", lat=city_center[0], lon=city_center[1],
                              radiusMeters=3500, source="city")
        direction = _direction_vector(normalized)
        if direction:
            lat, lon = _offset_point(city_center, direction[0], direction[1], 4500)
            return SearchArea(label=_direction_label(normalized), lat=lat, lon=lon,
                              radiusMeters=4500, source="direction")

        items = self._places(
            q=f"{location_hint}, {CITY_NAMES[city_id]}", locale="ru_RU",
            fields="items.point,items.full_name,items.address_name", page_size=10,
            search_is_query_text_complete="true",
        )
        for item in items:
            point = item.get("point")
            if not _valid_point(point):
                continue
            coordinates = float(point["lat"]), float(point["lon"])
            if _haversine_meters(city_center, coordinates) > 25000:
                continue
            label = str(item.get("full_name") or item.get("name") or location_hint).strip()
            return SearchArea(label=label, lat=coordinates[0], lon=coordinates[1],
                              radiusMeters=3000, source="2gis")
        raise GeoConstraintNotFound(location_hint)

    def search_places(self, city_id: str, preview: QueryPreview,
                      area: SearchArea) -> list[PlaceCandidate]:
        if preview.interests:
            queries = list(preview.interests)[:2]
        else:
            # A generic walk needs schedule diversity: outdoor places remain available
            # when museums have already closed.
            queries = ["достопримечательности", "парки и скверы", "памятники"]
        if preview.unusualPlaces:
            queries.append("необычные достопримечательности")
        # At most three interest searches plus one food search keeps first-build traffic bounded.
        requests = [(query, False) for query in queries[:3]]
        if preview.includeFood:
            requests.append(("кафе ресторан", True))

        result: list[PlaceCandidate] = []
        seen: set[str] = set()
        for query, requested_as_food in requests:
            items = self._places(
                q=query, type="attraction,branch", locale="ru_RU",
                point=f"{area.lon:.7f},{area.lat:.7f}", radius=area.radiusMeters,
                fields="items.point,items.rubrics,items.schedule,items.is_routing_available",
                page_size=10, search_is_query_text_complete="true",
            )
            for item in items:
                candidate = _candidate_from_item(item, requested_as_food)
                if candidate is None or candidate.placeId in seen:
                    continue
                result.append(candidate)
                seen.add(candidate.placeId)
        sights = [candidate for candidate in result if not candidate.isFood][:20]
        food = [candidate for candidate in result if candidate.isFood][:4]
        return sights + food

    def search_candidates(self, city_id: str, query: str) -> list[PlaceCandidate]:
        center = self.resolve_city_center(city_id)
        items = self._places(
            q=query, type="attraction,branch", locale="ru_RU",
            point=f"{center[1]:.7f},{center[0]:.7f}", radius=12000,
            fields="items.point,items.rubrics,items.schedule,items.is_routing_available,items.adm_div,items.city_alias",
            page_size=10, search_is_query_text_complete="true",
        )
        result: list[PlaceCandidate] = []
        for item in items:
            candidate = _candidate_from_item(item)
            if candidate and _belongs_to_city(item, city_id, center):
                result.append(candidate)
        return result[:10]

    def resolve_places(self, city_id: str, place_ids: list[str]) -> list[PlaceCandidate]:
        if not place_ids or len(set(place_ids)) != len(place_ids):
            raise GeoPlaceNotFound()
        center = self.resolve_city_center(city_id)
        items = self._places_from(
            PLACES_BY_ID_URL, id=",".join(sorted(place_ids)), locale="ru_RU",
            fields="items.point,items.rubrics,items.schedule,items.is_routing_available,items.adm_div,items.city_alias",
        )
        by_id: dict[str, PlaceCandidate] = {}
        for item in items:
            candidate = _candidate_from_item(item)
            if candidate and _belongs_to_city(item, city_id, center):
                by_id[candidate.placeId] = candidate
        if any(place_id not in by_id for place_id in place_ids):
            raise GeoPlaceNotFound()
        return [by_id[place_id] for place_id in place_ids]

    def walking_leg(self, start: tuple[float, float], end: tuple[float, float],
                    from_order: int, to_order: int) -> RouteLeg:
        cache_key = tuple(round(value, 6) for value in (*start, *end))
        cached = _ROUTING_CACHE.get(cache_key, self.clock())
        if isinstance(cached, RouteLeg):
            return cached.model_copy(update={"fromOrder": from_order, "toOrder": to_order})
        body = {
            "points": [
                {"type": "walking", "lat": start[0], "lon": start[1]},
                {"type": "walking", "lat": end[0], "lon": end[1]},
            ],
            "transport": "walking", "route_mode": "fastest", "output": "detailed", "locale": "ru",
            "params": {"pedestrian": {"use_instructions": False}},
        }
        data = self._request("POST", ROUTING_URL, params={"key": self.routing_key}, json=body)
        if data.get("status") in {"ROUTE_NOT_FOUND", "ROUTE_DOES_NOT_EXISTS", "ATTRACT_FAIL", "POINT_EXCLUDED"}:
            raise GeoRouteNotFound()
        results = data.get("result")
        if data.get("status") != "OK" or not isinstance(results, list) or not results:
            raise GeoInvalidResponse()
        route = results[0]
        if not isinstance(route, dict):
            raise GeoInvalidResponse()
        distance, duration = route.get("total_distance"), route.get("total_duration")
        if not isinstance(distance, (int, float)) or not isinstance(duration, (int, float)):
            raise GeoInvalidResponse()
        geometry = _route_geometry(route)
        if len(geometry) < 2:
            raise GeoInvalidResponse("2GIS route has no detailed geometry")
        leg = RouteLeg(fromOrder=from_order, toOrder=to_order,
                       distanceMeters=round(distance), durationSeconds=round(duration), geometry=geometry)
        _ROUTING_CACHE.put(cache_key, leg, self.clock() + self.routing_ttl)
        return leg


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


def _retry_after(response: httpx.Response, default: int) -> int:
    raw = response.headers.get("Retry-After")
    if raw:
        try:
            return max(1, min(30, math.ceil(float(raw))))
        except ValueError:
            try:
                delta = (parsedate_to_datetime(raw) - parsedate_to_datetime(response.headers["Date"])).total_seconds()
                return max(1, min(30, math.ceil(delta)))
            except (KeyError, TypeError, ValueError):
                pass
    return max(1, default)


def _valid_point(point: object) -> bool:
    return (isinstance(point, dict)
            and isinstance(point.get("lat"), (int, float))
            and isinstance(point.get("lon"), (int, float)))


def _candidate_from_item(item: dict, requested_as_food: bool = False) -> PlaceCandidate | None:
    place_id = str(item.get("id", "")).strip()
    name = str(item.get("name", "")).strip()
    point = item.get("point")
    if (not place_id or not name or item.get("is_routing_available") is False
            or not _valid_point(point)):
        return None
    rubrics_data = item.get("rubrics")
    rubrics = ([str(r.get("name", "")).strip() for r in rubrics_data
                if isinstance(r, dict) and r.get("name")]
               if isinstance(rubrics_data, list) else [])
    food_words = ("кафе", "ресторан", "кофейн", "столов", "бар", "пицц", "бургер")
    is_food = requested_as_food or any(
        any(word in rubric.casefold() for word in food_words) for rubric in rubrics
    )
    schedule = item.get("schedule") if isinstance(item.get("schedule"), dict) else {}
    return PlaceCandidate(
        placeId=place_id, name=name, lat=float(point["lat"]), lon=float(point["lon"]),
        rubrics=rubrics, schedule=schedule, isFood=is_food,
    )


def _belongs_to_city(item: dict, city_id: str, center: tuple[float, float]) -> bool:
    expected = CITY_NAMES[city_id].casefold()
    alias = str(item.get("city_alias", "")).strip().casefold()
    if alias:
        return alias == city_id
    divisions = item.get("adm_div")
    if isinstance(divisions, list):
        saw_city = False
        for division in divisions:
            if isinstance(division, dict) and str(division.get("type", "")).casefold() == "city":
                saw_city = True
                if str(division.get("name", "")).strip().casefold() == expected:
                    return True
        if saw_city:
            return False
    point = item.get("point")
    return _valid_point(point) and _haversine_meters(
        center, (float(point["lat"]), float(point["lon"]))
    ) <= 25000


def _direction_vector(value: str) -> tuple[int, int] | None:
    directions = {
        "север города": (1, 0), "юг города": (-1, 0),
        "восток города": (0, 1), "запад города": (0, -1),
        "северо-восток города": (1, 1), "северо-запад города": (1, -1),
        "юго-восток города": (-1, 1), "юго-запад города": (-1, -1),
    }
    return directions.get(value)


def _direction_label(value: str) -> str:
    return value[0].upper() + value[1:]


def _offset_point(center: tuple[float, float], north: int, east: int,
                  distance_meters: float) -> tuple[float, float]:
    divisor = math.sqrt(north * north + east * east)
    north_meters = distance_meters * north / divisor
    east_meters = distance_meters * east / divisor
    lat = center[0] + north_meters / 111_320
    lon = center[1] + east_meters / (111_320 * math.cos(math.radians(center[0])))
    return lat, lon


def _haversine_meters(start: tuple[float, float], end: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*start, *end))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6_371_000 * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def _route_geometry(route: dict) -> list[tuple[float, float]]:
    selections: list[str] = []
    begin_path = route.get("begin_pedestrian_path")
    begin_geometry = begin_path.get("geometry") if isinstance(begin_path, dict) else None
    begin = begin_geometry.get("selection") if isinstance(begin_geometry, dict) else None
    if isinstance(begin, str):
        selections.append(begin)
    maneuvers = route.get("maneuvers")
    for maneuver in maneuvers if isinstance(maneuvers, list) else []:
        if not isinstance(maneuver, dict):
            continue
        path = maneuver.get("outcoming_path")
        segments = path.get("geometry") if isinstance(path, dict) else None
        for segment in segments if isinstance(segments, list) else []:
            if isinstance(segment, dict) and isinstance(segment.get("selection"), str):
                selections.append(segment["selection"])
    end_path = route.get("end_pedestrian_path")
    end_geometry = end_path.get("geometry") if isinstance(end_path, dict) else None
    end = end_geometry.get("selection") if isinstance(end_geometry, dict) else None
    if isinstance(end, str):
        selections.append(end)

    points: list[tuple[float, float]] = []
    for selection in selections:
        match = re.fullmatch(r"\s*LINESTRING\s*\((.*)\)\s*", selection, re.IGNORECASE)
        if not match:
            continue
        for raw_point in match.group(1).split(","):
            values = raw_point.strip().split()
            if len(values) < 2:
                continue
            try:
                point = (float(values[0]), float(values[1]))
            except ValueError:
                continue
            if not points or points[-1] != point:
                points.append(point)
    return points

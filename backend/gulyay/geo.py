"""2GIS Places and Routing adapters.

Only responses received from 2GIS are converted into places and route legs.
There is deliberately no straight-line or synthetic-place fallback.
"""
from __future__ import annotations

import os
import re
from typing import Protocol

import httpx

from .models import PlaceCandidate, QueryPreview, RouteLeg


class GeoUnavailable(Exception):
    """2GIS is not configured or cannot be reached."""


class GeoAuthenticationError(GeoUnavailable):
    """2GIS rejected a server API key."""


class GeoInvalidResponse(GeoUnavailable):
    """2GIS returned an unusable response."""


class GeoRouteNotFound(Exception):
    """No pedestrian path exists between the supplied points."""


class GeoProvider(Protocol):
    def ensure_configured(self) -> None: ...
    def resolve_city_center(self, city_id: str) -> tuple[float, float]: ...
    def search_places(self, city_id: str, preview: QueryPreview,
                      center: tuple[float, float]) -> list[PlaceCandidate]: ...
    def walking_leg(self, start: tuple[float, float], end: tuple[float, float],
                    from_order: int, to_order: int) -> RouteLeg: ...


CITY_NAMES = {"tula": "Тула", "vladimir": "Владимир"}
PLACES_URL = "https://catalog.api.2gis.com/3.0/items"
ROUTING_URL = "https://routing.api.2gis.com/routing/7.0.0/global"


class DgisGeoProvider:
    def __init__(self, places_key: str | None = None, routing_key: str | None = None,
                 transport: httpx.BaseTransport | None = None):
        self.places_key = places_key if places_key is not None else os.getenv("DGIS_PLACES_API_KEY")
        self.routing_key = routing_key if routing_key is not None else os.getenv("DGIS_ROUTING_API_KEY")
        self.transport = transport

    def ensure_configured(self) -> None:
        if not self.places_key or not self.routing_key:
            raise GeoUnavailable("DGIS_PLACES_API_KEY and DGIS_ROUTING_API_KEY must be configured")

    def _client(self) -> httpx.Client:
        return httpx.Client(timeout=12.0, transport=self.transport,
                            headers={"User-Agent": "Gulyay-Backend/0.3"})

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

    def _places(self, **params: str | int | bool) -> list[dict]:
        self.ensure_configured()
        try:
            with self._client() as client:
                response = client.get(PLACES_URL, params={"key": self.places_key, **params})
            data = self._read_json(response)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise GeoUnavailable() from exc
        meta, result = data.get("meta"), data.get("result")
        if not isinstance(meta, dict) or meta.get("code") != 200 or not isinstance(result, dict):
            raise GeoInvalidResponse()
        items = result.get("items")
        if not isinstance(items, list):
            raise GeoInvalidResponse()
        return [item for item in items if isinstance(item, dict)]

    def resolve_city_center(self, city_id: str) -> tuple[float, float]:
        city_name = CITY_NAMES[city_id]
        items = self._places(q=city_name, type="adm_div.city", locale="ru_RU",
                             fields="items.point", page_size=5,
                             search_is_query_text_complete="true")
        for item in items:
            if str(item.get("name", "")).casefold() != city_name.casefold():
                continue
            point = item.get("point")
            if not isinstance(point, dict):
                continue
            if isinstance(point.get("lat"), (int, float)) and isinstance(point.get("lon"), (int, float)):
                return float(point["lat"]), float(point["lon"])
        raise GeoInvalidResponse("2GIS did not return the selected city center")

    def search_places(self, city_id: str, preview: QueryPreview,
                      center: tuple[float, float]) -> list[PlaceCandidate]:
        queries = list(preview.interests) or ["достопримечательности"]
        if preview.unusualPlaces:
            queries.append("необычные достопримечательности")
        requests = [(query, False) for query in queries[:4]]
        if preview.includeFood:
            requests.append(("кафе ресторан", True))

        radius = 3500 if preview.centerOnly else 12000
        result: list[PlaceCandidate] = []
        seen: set[str] = set()
        for query, requested_as_food in requests:
            items = self._places(
                q=query, type="attraction,branch", locale="ru_RU",
                point=f"{center[1]:.7f},{center[0]:.7f}", radius=radius,
                fields="items.point,items.rubrics,items.schedule,items.is_routing_available",
                page_size=10, search_is_query_text_complete="true",
            )
            for item in items:
                place_id, name = str(item.get("id", "")).strip(), str(item.get("name", "")).strip()
                point = item.get("point")
                rubrics_data = item.get("rubrics")
                if (not place_id or not name or place_id in seen or item.get("is_routing_available") is False
                        or not isinstance(point, dict)
                        or not isinstance(point.get("lat"), (int, float))
                        or not isinstance(point.get("lon"), (int, float))):
                    continue
                rubrics = ([str(r.get("name", "")).strip() for r in rubrics_data
                            if isinstance(r, dict) and r.get("name")]
                           if isinstance(rubrics_data, list) else [])
                food_words = ("кафе", "ресторан", "кофейн", "столов", "бар", "пицц", "бургер")
                is_food = requested_as_food or any(any(word in rubric.casefold() for word in food_words)
                                                   for rubric in rubrics)
                result.append(PlaceCandidate(
                    placeId=place_id, name=name, lat=float(point["lat"]), lon=float(point["lon"]),
                    rubrics=rubrics, schedule=item.get("schedule") if isinstance(item.get("schedule"), dict) else {},
                    isFood=is_food,
                ))
                seen.add(place_id)
                if len(result) >= 20:
                    return result
        return result

    def walking_leg(self, start: tuple[float, float], end: tuple[float, float],
                    from_order: int, to_order: int) -> RouteLeg:
        self.ensure_configured()
        body = {
            "points": [
                {"type": "walking", "lat": start[0], "lon": start[1]},
                {"type": "walking", "lat": end[0], "lon": end[1]},
            ],
            "transport": "walking", "route_mode": "fastest", "output": "detailed", "locale": "ru",
            "params": {"pedestrian": {"use_instructions": False}},
        }
        try:
            with self._client() as client:
                response = client.post(ROUTING_URL, params={"key": self.routing_key}, json=body)
            data = self._read_json(response)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise GeoUnavailable() from exc
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
        return RouteLeg(fromOrder=from_order, toOrder=to_order,
                        distanceMeters=round(distance), durationSeconds=round(duration), geometry=geometry)


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

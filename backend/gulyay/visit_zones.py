"""Load and validate optional GeoJSON visit zones for catalogue places."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


class VisitZoneValidationError(ValueError):
    """A visit-zone file cannot be used without losing geometric integrity."""


@dataclass(frozen=True)
class VisitZone:
    catalog_id: str
    geometry: dict[str, object]


class VisitZones:
    """Immutable-by-convention lookup; a missing zone intentionally returns None."""

    def __init__(self, zones: dict[str, VisitZone]):
        self._zones = dict(zones)

    def __len__(self) -> int:
        return len(self._zones)

    def __contains__(self, catalog_id: str) -> bool:
        return catalog_id in self._zones

    @property
    def catalog_ids(self) -> tuple[str, ...]:
        return tuple(self._zones)

    def get(self, catalog_id: str) -> VisitZone | None:
        return self._zones.get(catalog_id)


def bundled_visit_zones_path() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "visit_zones.geojson"


def load_visit_zones(path: str | Path, catalog_ids: Iterable[str]) -> VisitZones:
    """Load one Polygon/MultiPolygon Feature per known catalogue ID."""
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VisitZoneValidationError(f"Не удалось прочитать GeoJSON геозон: {source}") from exc

    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
        raise VisitZoneValidationError("GeoJSON геозон должен быть FeatureCollection")
    features = payload.get("features")
    if not isinstance(features, list):
        raise VisitZoneValidationError("FeatureCollection.features должен быть массивом")

    known_ids = set(catalog_ids)
    zones: dict[str, VisitZone] = {}
    for index, feature in enumerate(features):
        context = f"Feature {index}"
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise VisitZoneValidationError(f"{context}: ожидается GeoJSON Feature")
        properties = feature.get("properties")
        if not isinstance(properties, dict):
            raise VisitZoneValidationError(f"{context}: properties должен быть объектом")
        catalog_id = properties.get("catalog_id")
        if not isinstance(catalog_id, str) or not catalog_id.strip():
            raise VisitZoneValidationError(f"{context}: отсутствует catalog_id")
        catalog_id = catalog_id.strip()
        if catalog_id not in known_ids:
            raise VisitZoneValidationError(
                f"{context}: catalog_id {catalog_id!r} отсутствует в каталоге"
            )
        if catalog_id in zones:
            raise VisitZoneValidationError(f"Повторная геозона catalog_id {catalog_id!r}")

        geometry = feature.get("geometry")
        _validate_geometry(geometry, f"{context} ({catalog_id})")
        zones[catalog_id] = VisitZone(catalog_id, geometry)
    return VisitZones(zones)


def _validate_geometry(value: object, context: str) -> None:
    if not isinstance(value, dict):
        raise VisitZoneValidationError(f"{context}: geometry должен быть объектом")
    geometry_type = value.get("type")
    coordinates = value.get("coordinates")
    if geometry_type == "Polygon":
        polygons = [coordinates]
    elif geometry_type == "MultiPolygon":
        if not isinstance(coordinates, list) or not coordinates:
            raise VisitZoneValidationError(f"{context}: пустой MultiPolygon")
        polygons = coordinates
    else:
        raise VisitZoneValidationError(
            f"{context}: поддерживаются только Polygon и MultiPolygon"
        )

    for polygon_index, polygon in enumerate(polygons):
        # Parts are validated independently. Hand-drawn source parts may overlap,
        # and changing or unioning those contours is deliberately out of scope.
        _validate_polygon(polygon, f"{context}, polygon {polygon_index}")


def _validate_polygon(value: object, context: str) -> list[list[tuple[float, float]]]:
    if not isinstance(value, list) or not value:
        raise VisitZoneValidationError(f"{context}: Polygon не содержит колец")
    rings = [_validate_ring(ring, f"{context}, ring {index}")
             for index, ring in enumerate(value)]
    outer, holes = rings[0], rings[1:]
    for index, hole in enumerate(holes):
        if _rings_intersect(outer, hole) or not _point_in_ring(hole[0], outer):
            raise VisitZoneValidationError(
                f"{context}: внутреннее кольцо {index + 1} выходит за внешнее"
            )
    for left_index, left in enumerate(holes):
        for right_index, right in enumerate(holes[left_index + 1:], left_index + 1):
            if (_rings_intersect(left, right)
                    or _point_in_ring(left[0], right)
                    or _point_in_ring(right[0], left)):
                raise VisitZoneValidationError(
                    f"{context}: внутренние кольца {left_index + 1} и "
                    f"{right_index + 1} пересекаются"
                )
    return rings


def _validate_ring(value: object, context: str) -> list[tuple[float, float]]:
    if not isinstance(value, list) or len(value) < 4:
        raise VisitZoneValidationError(f"{context}: кольцо должно содержать минимум 4 точки")
    ring = [_validate_position(position, f"{context}, point {index}")
            for index, position in enumerate(value)]
    if ring[0] != ring[-1]:
        raise VisitZoneValidationError(f"{context}: кольцо не замкнуто")
    if len(set(ring[:-1])) < 3:
        raise VisitZoneValidationError(f"{context}: недостаточно различных вершин")
    if any(ring[index] == ring[index + 1] for index in range(len(ring) - 1)):
        raise VisitZoneValidationError(f"{context}: соседние вершины совпадают")
    if _ring_self_intersects(ring):
        raise VisitZoneValidationError(f"{context}: кольцо самопересекается")
    area_twice = sum(
        ring[index][0] * ring[index + 1][1]
        - ring[index + 1][0] * ring[index][1]
        for index in range(len(ring) - 1)
    )
    if abs(area_twice) <= 1e-15:
        raise VisitZoneValidationError(f"{context}: кольцо имеет нулевую площадь")
    return ring


def _validate_position(value: object, context: str) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) != 2:
        raise VisitZoneValidationError(
            f"{context}: координата должна быть [longitude, latitude]"
        )
    lon, lat = value
    if (isinstance(lon, bool) or isinstance(lat, bool)
            or not isinstance(lon, (int, float))
            or not isinstance(lat, (int, float))):
        raise VisitZoneValidationError(f"{context}: координаты должны быть числами")
    lon, lat = float(lon), float(lat)
    if not math.isfinite(lon) or not math.isfinite(lat):
        raise VisitZoneValidationError(f"{context}: координаты должны быть конечными")
    if not -180 <= lon <= 180 or not -90 <= lat <= 90:
        raise VisitZoneValidationError(
            f"{context}: неверный порядок или диапазон [longitude, latitude]"
        )
    return lon, lat


def _ring_self_intersects(ring: list[tuple[float, float]]) -> bool:
    segment_count = len(ring) - 1
    for left in range(segment_count):
        for right in range(left + 1, segment_count):
            if right == left + 1 or (left == 0 and right == segment_count - 1):
                continue
            if _segments_intersect(
                ring[left], ring[left + 1], ring[right], ring[right + 1],
            ):
                return True
    return False


def _rings_intersect(left: list[tuple[float, float]],
                     right: list[tuple[float, float]]) -> bool:
    return any(
        _segments_intersect(left[a], left[a + 1], right[b], right[b + 1])
        for a in range(len(left) - 1)
        for b in range(len(right) - 1)
    )


def _segments_intersect(a: tuple[float, float], b: tuple[float, float],
                        c: tuple[float, float], d: tuple[float, float]) -> bool:
    orientations = (
        _orientation(a, b, c), _orientation(a, b, d),
        _orientation(c, d, a), _orientation(c, d, b),
    )
    if orientations[0] != orientations[1] and orientations[2] != orientations[3]:
        return True
    return any((
        orientations[0] == 0 and _on_segment(a, b, c),
        orientations[1] == 0 and _on_segment(a, b, d),
        orientations[2] == 0 and _on_segment(c, d, a),
        orientations[3] == 0 and _on_segment(c, d, b),
    ))


def _orientation(a: tuple[float, float], b: tuple[float, float],
                 c: tuple[float, float]) -> int:
    cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    if abs(cross) <= 1e-12:
        return 0
    return 1 if cross > 0 else -1


def _on_segment(a: tuple[float, float], b: tuple[float, float],
                point: tuple[float, float]) -> bool:
    return (
        min(a[0], b[0]) - 1e-12 <= point[0] <= max(a[0], b[0]) + 1e-12
        and min(a[1], b[1]) - 1e-12 <= point[1] <= max(a[1], b[1]) + 1e-12
    )


def _point_in_ring(point: tuple[float, float], ring: list[tuple[float, float]]) -> bool:
    inside = False
    for index in range(len(ring) - 1):
        left, right = ring[index], ring[index + 1]
        if _orientation(left, right, point) == 0 and _on_segment(left, right, point):
            return False
        if ((left[1] > point[1]) != (right[1] > point[1])
                and point[0] < (right[0] - left[0]) * (point[1] - left[1])
                / (right[1] - left[1]) + left[0]):
            inside = not inside
    return inside


def distance_to_geometry_meters(lat: float, lon: float,
                                geometry: object) -> tuple[float, bool]:
    """Return distance to a Polygon/MultiPolygon and whether the point is inside.

    Geometry is the immutable route-version snapshot, not the current bundled
    GeoJSON, so an active walk cannot change when catalogue data is refreshed.
    """
    if not isinstance(geometry, dict):
        raise ValueError("visit-zone geometry must be an object")
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if geometry_type == "Polygon":
        polygons = [coordinates]
    elif geometry_type == "MultiPolygon":
        polygons = coordinates
    else:
        raise ValueError("unsupported visit-zone geometry")
    if not isinstance(polygons, list) or not polygons:
        raise ValueError("empty visit-zone geometry")
    point = (float(lon), float(lat))
    results = [_distance_to_polygon(point, polygon) for polygon in polygons]
    inside = any(item[1] for item in results)
    return (0.0 if inside else min(item[0] for item in results), inside)


def distance_to_polyline_meters(lat: float, lon: float,
                                geometry: list[tuple[float, float]]) -> float:
    """Distance to a verified 2GIS leg whose coordinates are [lon, lat]."""
    point = (float(lon), float(lat))
    if not geometry:
        return math.inf
    if len(geometry) == 1:
        return _distance_lon_lat_meters(point, geometry[0])
    return min(
        _distance_to_segment_meters(point, geometry[index], geometry[index + 1])
        for index in range(len(geometry) - 1)
    )


def _distance_to_polygon(point: tuple[float, float], polygon: object) -> tuple[float, bool]:
    if not isinstance(polygon, list) or not polygon:
        raise ValueError("empty visit-zone polygon")
    rings = [[(float(position[0]), float(position[1])) for position in ring]
             for ring in polygon]
    on_boundary = any(_point_on_ring(point, ring) for ring in rings)
    inside_outer = _point_in_ring(point, rings[0])
    inside_hole = any(_point_in_ring(point, ring) for ring in rings[1:])
    inside = on_boundary or (inside_outer and not inside_hole)
    distance = min(
        _distance_to_segment_meters(point, ring[index], ring[index + 1])
        for ring in rings for index in range(len(ring) - 1)
    )
    return (0.0 if inside else distance), inside


def _point_on_ring(point: tuple[float, float], ring: list[tuple[float, float]]) -> bool:
    return any(
        _orientation(ring[index], ring[index + 1], point) == 0
        and _on_segment(ring[index], ring[index + 1], point)
        for index in range(len(ring) - 1)
    )


def _distance_to_segment_meters(point: tuple[float, float],
                                start: tuple[float, float],
                                end: tuple[float, float]) -> float:
    reference_lat = math.radians(point[1])
    scale_x = 111_320.0 * max(1e-9, math.cos(reference_lat))
    scale_y = 110_540.0
    ax, ay = (start[0] - point[0]) * scale_x, (start[1] - point[1]) * scale_y
    bx, by = (end[0] - point[0]) * scale_x, (end[1] - point[1]) * scale_y
    dx, dy = bx - ax, by - ay
    denominator = dx * dx + dy * dy
    if denominator == 0:
        return math.hypot(ax, ay)
    fraction = max(0.0, min(1.0, -(ax * dx + ay * dy) / denominator))
    return math.hypot(ax + fraction * dx, ay + fraction * dy)


def _distance_lon_lat_meters(left: tuple[float, float],
                             right: tuple[float, float]) -> float:
    return _distance_to_segment_meters(left, right, right)

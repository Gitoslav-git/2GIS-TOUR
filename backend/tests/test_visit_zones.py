import json

import pytest

from gulyay.catalog import PlaceCatalog, bundled_seed_path, bundled_seed_paths
from gulyay.visit_zones import (VisitZoneValidationError,
                                bundled_visit_zones_path,
                                distance_to_geometry_meters, load_visit_zones)


def catalog_ids(tmp_path):
    catalog = PlaceCatalog(tmp_path / "catalog.sqlite3")
    catalog.import_seed(bundled_seed_path())
    return {place.id for place in catalog.list_places("moscow")}


def write_zones(tmp_path, features):
    path = tmp_path / "zones.geojson"
    path.write_text(json.dumps({
        "type": "FeatureCollection",
        "features": features,
    }), encoding="utf-8")
    return path


def feature(catalog_id="msk001", coordinates=None):
    return {
        "type": "Feature",
        "properties": {"catalog_id": catalog_id},
        "geometry": {
            "type": "Polygon",
            "coordinates": coordinates or [[
                [37.61, 55.75], [37.62, 55.75],
                [37.62, 55.76], [37.61, 55.75],
            ]],
        },
    }


def test_bundled_visit_zones_load_against_catalog_and_keep_unique_ids(tmp_path):
    zones = load_visit_zones(bundled_visit_zones_path(), catalog_ids(tmp_path))

    assert len(zones) == 35
    for catalog_id in ("msk019", "msk029", "msk030", "msk031", "msk060"):
        assert zones.get(catalog_id) is not None
    assert zones.get("msk025") is None
    assert len(zones.catalog_ids) == len(set(zones.catalog_ids))
    assert zones.get("msk005").geometry["type"] == "Polygon"
    assert zones.get("msk032").geometry["type"] == "Polygon"


def test_bundled_multi_polygons_keep_every_drawn_part(tmp_path):
    zones = load_visit_zones(bundled_visit_zones_path(), catalog_ids(tmp_path))

    alexander_garden = zones.get("msk013").geometry
    vdnh = zones.get("msk036").geometry
    assert alexander_garden["type"] == "MultiPolygon"
    assert len(alexander_garden["coordinates"]) == 5
    assert vdnh["type"] == "MultiPolygon"
    assert len(vdnh["coordinates"]) == 6


def test_bundled_coordinates_are_closed_longitude_latitude_pairs_in_moscow(tmp_path):
    zones = load_visit_zones(bundled_visit_zones_path(), catalog_ids(tmp_path))

    for catalog_id in zones.catalog_ids:
        geometry = zones.get(catalog_id).geometry
        polygons = (geometry["coordinates"] if geometry["type"] == "MultiPolygon"
                    else [geometry["coordinates"]])
        for polygon in polygons:
            for ring in polygon:
                assert ring[0] == ring[-1]
                assert all(len(position) == 2 for position in ring)
                assert all(36 <= lon <= 39 and 54 <= lat <= 57 for lon, lat in ring)


def test_unknown_catalog_id_is_rejected(tmp_path):
    path = write_zones(tmp_path, [feature("msk999")])

    with pytest.raises(VisitZoneValidationError, match="отсутствует в каталоге"):
        load_visit_zones(path, catalog_ids(tmp_path))


def test_duplicate_catalog_binding_is_rejected(tmp_path):
    path = write_zones(tmp_path, [feature(), feature()])

    with pytest.raises(VisitZoneValidationError, match="Повторная геозона"):
        load_visit_zones(path, catalog_ids(tmp_path))


@pytest.mark.parametrize("coordinates, message", [
    ([[[37.61, 55.75], [37.62, 55.75], [37.62, 55.76], [37.61, 55.76]]],
     "не замкнуто"),
    ([[[37.61, 55.75], [37.62, 55.76], [37.61, 55.76],
       [37.62, 55.75], [37.61, 55.75]]], "самопересекается"),
    ([[[181, 55.75], [182, 55.75], [182, 55.76], [181, 55.75]]],
     "longitude, latitude"),
])
def test_invalid_geometry_is_rejected(tmp_path, coordinates, message):
    path = write_zones(tmp_path, [feature(coordinates=coordinates)])

    with pytest.raises(VisitZoneValidationError, match=message):
        load_visit_zones(path, catalog_ids(tmp_path))


def test_missing_zone_is_optional_for_point_fallback(tmp_path):
    zones = load_visit_zones(bundled_visit_zones_path(), catalog_ids(tmp_path))

    assert zones.get("msk069") is None
    assert "msk069" not in zones


def test_nizhny_novgorod_has_no_fake_zones_and_uses_point_fallback(tmp_path):
    catalog = PlaceCatalog(tmp_path / "all-cities.sqlite3")
    for seed_path in bundled_seed_paths():
        catalog.import_seed(seed_path)
    all_ids = {
        place.id
        for city_id in ("moscow", "tula", "vladimir", "borovsk", "nizhny_novgorod")
        for place in catalog.list_places(city_id)
    }
    zones = load_visit_zones(bundled_visit_zones_path(), all_ids)

    assert not any(catalog_id.startswith("nn") for catalog_id in zones.catalog_ids)
    assert zones.get("nn001") is None


def test_distance_supports_polygon_boundary_and_outside():
    geometry = {"type": "Polygon", "coordinates": [[
        [37.0, 55.0], [37.002, 55.0], [37.002, 55.002],
        [37.0, 55.002], [37.0, 55.0],
    ]]}
    assert distance_to_geometry_meters(55.001, 37.001, geometry) == (0.0, True)
    assert distance_to_geometry_meters(55.001, 37.0, geometry) == (0.0, True)
    distance, inside = distance_to_geometry_meters(55.004, 37.001, geometry)
    assert inside is False
    assert 215 < distance < 230

    distance_75, _ = distance_to_geometry_meters(
        55.002 + 75 / 110_540, 37.001, geometry,
    )
    distance_70, _ = distance_to_geometry_meters(
        55.002 + 70 / 110_540, 37.001, geometry,
    )
    assert 74 < distance_75 < 76
    assert 69 < distance_70 < 71


def test_distance_supports_separate_multipolygon_parts():
    square = lambda lon: [[
        [lon, 55.0], [lon + 0.001, 55.0], [lon + 0.001, 55.001],
        [lon, 55.001], [lon, 55.0],
    ]]
    geometry = {"type": "MultiPolygon", "coordinates": [
        square(37.0), square(37.01),
    ]}
    assert distance_to_geometry_meters(55.0005, 37.0105, geometry) == (0.0, True)
    distance, inside = distance_to_geometry_meters(55.0005, 37.005, geometry)
    assert inside is False
    assert distance > 250

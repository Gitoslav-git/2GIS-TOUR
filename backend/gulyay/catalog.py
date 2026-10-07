"""Local multi-city attraction catalogue and deterministic retrieval."""
from __future__ import annotations

import csv
import json
import math
import os
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .catalog_intent import (CONCEPT_TAGS, PRIORITY_WEIGHTS, RELATED_TAGS, CatalogQuery,
                             catalog_query_from_preview, normalize_lexical_tokens,
                             type_matches_concept)
from .models import PlaceCandidate, QueryPreview, SearchArea


ALLOWED_LEVELS = frozenset({"AREA", "COMPLEX", "POI"})
ALLOWED_RELATIONS = frozenset({"CONTAINS", "CLUSTER_MEMBER"})
ALLOWED_ACCESS_COSTS = frozenset({"FREE", "PAID", "MIXED"})
ALLOWED_TAGS = frozenset({
    "HISTORY", "ARCHITECTURE", "ART_CULTURE", "RELIGION", "NATURE",
    "SCIENCE_TECH", "MILITARY", "SOVIET", "LOCAL_CULTURE",
    "CONTEMPORARY", "UNUSUAL", "PANORAMIC", "PHOTOGENIC",
    "ATMOSPHERIC", "QUIET", "FAMILY", "ACTIVE", "INDOOR",
})

class CatalogImportError(ValueError):
    """The supplied seed cannot be imported without losing integrity."""


@dataclass(frozen=True)
class CatalogPlace:
    id: str
    city_id: str
    name: str
    level: str
    parent_id: str | None
    relation: str | None
    place_type: str
    tags: tuple[str, ...]
    access_cost: str
    base_price_from_rub: int | None
    base_price_to_rub: int | None
    price_note: str | None
    visit_min: int
    visit_max: int
    lat: float | None
    lon: float | None
    dgis_place_id: str | None
    provider_name: str | None
    search_aliases: tuple[str, ...]
    allow_coords_only: bool
    price_source_url: str | None
    is_active: bool


def default_catalog_path() -> str:
    configured = os.getenv("GULYAY_DB_PATH")
    if configured:
        return configured
    return str(Path(__file__).resolve().parent.parent / "data" / "gulyay.sqlite3")


def bundled_seed_path() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "moscow_places_v0_1.csv"


def bundled_seed_paths() -> tuple[Path, ...]:
    data_dir = Path(__file__).resolve().parent.parent / "data"
    return tuple(sorted(data_dir.glob("*_places_v0_1.csv")))


class PlaceCatalog:
    """Catalogue persistence isolated from route lifecycle cleanup."""

    def __init__(self, path: str | Path | None = None):
        resolved = str(path) if path is not None else default_catalog_path()
        if resolved != ":memory:":
            resolved = str(Path(resolved).expanduser().resolve())
            Path(resolved).parent.mkdir(parents=True, exist_ok=True)
        self.path = resolved
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(resolved, check_same_thread=False, timeout=10)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA busy_timeout = 10000")
        self._connection.execute("PRAGMA foreign_keys = ON")
        if resolved != ":memory:":
            self._connection.execute("PRAGMA journal_mode = WAL")
        self._create_schema()

    def _create_schema(self) -> None:
        with self._lock, self._connection:
            self._connection.execute("""
                CREATE TABLE IF NOT EXISTS cities (
                    city_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL
                )
            """)
            self._connection.execute("""
                CREATE TABLE IF NOT EXISTS places (
                    id TEXT PRIMARY KEY,
                    city_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    level TEXT NOT NULL,
                    parent_id TEXT NULL,
                    relation TEXT NULL,
                    place_type TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    access_cost TEXT NOT NULL,
                    base_price_from_rub INTEGER NULL,
                    base_price_to_rub INTEGER NULL,
                    price_note TEXT NULL,
                    visit_min INTEGER NOT NULL,
                    visit_max INTEGER NOT NULL,
                    lat REAL NULL,
                    lon REAL NULL,
                    dgis_place_id TEXT NULL,
                    provider_name TEXT NULL,
                    search_aliases_json TEXT NOT NULL DEFAULT '[]',
                    allow_coords_only INTEGER NOT NULL DEFAULT 0,
                    price_source_url TEXT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (city_id) REFERENCES cities(city_id),
                    FOREIGN KEY (parent_id) REFERENCES places(id)
                )
            """)
            columns = {
                row["name"] for row in self._connection.execute("PRAGMA table_info(places)")
            }
            if "provider_name" not in columns:
                self._connection.execute(
                    "ALTER TABLE places ADD COLUMN provider_name TEXT NULL"
                )
            if "search_aliases_json" not in columns:
                self._connection.execute(
                    "ALTER TABLE places ADD COLUMN search_aliases_json TEXT NOT NULL DEFAULT '[]'"
                )
            if "allow_coords_only" not in columns:
                self._connection.execute(
                    "ALTER TABLE places ADD COLUMN allow_coords_only INTEGER NOT NULL DEFAULT 0"
                )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_places_city ON places(city_id)"
            )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_places_parent ON places(parent_id)"
            )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_places_level ON places(level)"
            )

    def import_seed(self, seed_path: str | Path, *, city_names: dict[str, str] | None = None,
                    dry_run: bool = False) -> int:
        rows = self._read_seed(seed_path)
        city_names = {
            "moscow": "Москва",
            "tula": "Тула",
            "vladimir": "Владимир",
            "borovsk": "Боровск",
            **(city_names or {}),
        }
        known_ids = {row[0] for row in self._connection.execute("SELECT id FROM places")}
        incoming_ids = {row.id for row in rows}
        for row in rows:
            if row.parent_id and row.parent_id not in incoming_ids | known_ids:
                raise CatalogImportError(
                    f"{row.id}: parent_id {row.parent_id!r} отсутствует в seed и каталоге"
                )
        if dry_run:
            return len(rows)
        with self._lock, self._connection:
            for city_id in sorted({row.city_id for row in rows}):
                self._connection.execute(
                    "INSERT INTO cities(city_id, name) VALUES (?, ?) "
                    "ON CONFLICT(city_id) DO UPDATE SET name = excluded.name",
                    (city_id, city_names.get(city_id, city_id)),
                )
            # Parents can appear after children in future seeds. Upsert roots first,
            # then descendants once their FK target is guaranteed to exist.
            pending = list(rows)
            imported: set[str] = set(known_ids)
            while pending:
                ready = [row for row in pending if not row.parent_id or row.parent_id in imported]
                if not ready:
                    raise CatalogImportError("Обнаружен цикл parent_id в seed")
                for row in ready:
                    self._upsert(row)
                    imported.add(row.id)
                    pending.remove(row)
        return len(rows)

    def _read_seed(self, seed_path: str | Path) -> list[CatalogPlace]:
        path = Path(seed_path)
        try:
            handle = path.open("r", encoding="utf-8-sig", newline="")
        except OSError as exc:
            raise CatalogImportError(f"Не удалось открыть seed: {path}") from exc
        with handle:
            reader = csv.DictReader(handle)
            required = {
                "id", "city_id", "name", "level", "parent_id", "relation", "type",
                "tags", "access_cost", "base_price_from_rub", "base_price_to_rub",
                "price_note", "visit_min", "visit_max", "lat", "lon",
                "dgis_place_id", "price_source_url",
            }
            if not reader.fieldnames or not required.issubset(reader.fieldnames):
                missing = sorted(required - set(reader.fieldnames or []))
                raise CatalogImportError(f"В seed отсутствуют поля: {', '.join(missing)}")
            result: list[CatalogPlace] = []
            seen: set[str] = set()
            for line_number, raw in enumerate(reader, 2):
                row = self._validate_row(raw, line_number)
                if row.id in seen:
                    raise CatalogImportError(f"Строка {line_number}: повтор id {row.id}")
                seen.add(row.id)
                result.append(row)
        return result

    @staticmethod
    def _validate_row(raw: dict[str, str | None], line: int) -> CatalogPlace:
        def text(name: str) -> str:
            return (raw.get(name) or "").strip()

        def optional_text(name: str) -> str | None:
            return text(name) or None

        def integer(name: str, *, required: bool = False) -> int | None:
            value = text(name)
            if not value and not required:
                return None
            try:
                return int(value)
            except ValueError as exc:
                raise CatalogImportError(f"Строка {line}: {name} должен быть целым") from exc

        def number(name: str) -> float | None:
            value = text(name)
            if not value:
                return None
            try:
                return float(value)
            except ValueError as exc:
                raise CatalogImportError(f"Строка {line}: {name} должен быть числом") from exc

        def json_strings(name: str) -> tuple[str, ...]:
            value = text(name)
            if not value:
                return ()
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError as exc:
                raise CatalogImportError(
                    f"Строка {line}: {name} должен быть JSON-массивом строк"
                ) from exc
            if (not isinstance(parsed, list)
                    or any(not isinstance(item, str) or not item.strip() for item in parsed)):
                raise CatalogImportError(
                    f"Строка {line}: {name} должен быть JSON-массивом непустых строк"
                )
            return tuple(dict.fromkeys(item.strip() for item in parsed))

        place_id, city_id, name = text("id"), text("city_id"), text("name")
        if not place_id or not city_id or not name:
            raise CatalogImportError(f"Строка {line}: id, city_id и name обязательны")
        level, relation = text("level"), optional_text("relation")
        if level not in ALLOWED_LEVELS:
            raise CatalogImportError(f"Строка {line}: неизвестный level {level!r}")
        if relation and relation not in ALLOWED_RELATIONS:
            raise CatalogImportError(f"Строка {line}: неизвестный relation {relation!r}")
        parent_id = optional_text("parent_id")
        if bool(parent_id) != bool(relation):
            raise CatalogImportError(
                f"Строка {line}: parent_id и relation должны быть заполнены вместе"
            )
        place_type = text("type")
        if not place_type:
            raise CatalogImportError(f"Строка {line}: type обязателен")
        tags = tuple(dict.fromkeys(
            value.strip() for value in text("tags").split(",") if value.strip()
        ))
        unknown_tags = sorted(set(tags) - ALLOWED_TAGS)
        if unknown_tags:
            raise CatalogImportError(
                f"Строка {line}: неизвестные tags: {', '.join(unknown_tags)}"
            )
        access_cost = text("access_cost")
        if access_cost not in ALLOWED_ACCESS_COSTS:
            raise CatalogImportError(
                f"Строка {line}: неизвестный access_cost {access_cost!r}"
            )
        price_from = integer("base_price_from_rub")
        price_to = integer("base_price_to_rub")
        if price_from is not None and price_from < 0 or price_to is not None and price_to < 0:
            raise CatalogImportError(f"Строка {line}: цена не может быть отрицательной")
        if price_from is not None and price_to is not None and price_from > price_to:
            raise CatalogImportError(f"Строка {line}: нижняя цена выше верхней")
        if access_cost == "FREE" and (price_from != 0 or price_to != 0):
            raise CatalogImportError(f"Строка {line}: FREE должен иметь цены 0 и 0")
        price_note = optional_text("price_note")
        if access_cost != "FREE" and price_from is None and price_to is None:
            if not price_note or "tbd" not in price_note.casefold():
                raise CatalogImportError(
                    f"Строка {line}: пустая цена допустима только с пометкой TBD"
                )
        visit_min = integer("visit_min", required=True)
        visit_max = integer("visit_max", required=True)
        assert visit_min is not None and visit_max is not None
        if visit_min <= 0 or visit_min > visit_max:
            raise CatalogImportError(
                f"Строка {line}: visit_min должен быть > 0 и <= visit_max"
            )
        lat, lon = number("lat"), number("lon")
        if (lat is None) != (lon is None):
            raise CatalogImportError(f"Строка {line}: lat и lon заполняются вместе")
        if lat is not None and not -90 <= lat <= 90 or lon is not None and not -180 <= lon <= 180:
            raise CatalogImportError(f"Строка {line}: координаты вне допустимого диапазона")
        allow_coords_only_raw = text("allow_coords_only")
        if allow_coords_only_raw not in {"", "0", "1"}:
            raise CatalogImportError(
                f"Row {line}: allow_coords_only must be 0 or 1"
            )
        return CatalogPlace(
            id=place_id, city_id=city_id, name=name, level=level,
            parent_id=parent_id, relation=relation, place_type=place_type, tags=tags,
            access_cost=access_cost, base_price_from_rub=price_from,
            base_price_to_rub=price_to, price_note=price_note,
            visit_min=visit_min, visit_max=visit_max, lat=lat, lon=lon,
            dgis_place_id=optional_text("dgis_place_id"),
            provider_name=optional_text("provider_name"),
            search_aliases=json_strings(
                "search_aliases_json" if "search_aliases_json" in raw else "search_aliases"
            ),
            allow_coords_only=allow_coords_only_raw == "1",
            price_source_url=optional_text("price_source_url"), is_active=True,
        )

    def _upsert(self, row: CatalogPlace) -> None:
        self._connection.execute("""
            INSERT INTO places (
                id, city_id, name, level, parent_id, relation, place_type, tags_json,
                access_cost, base_price_from_rub, base_price_to_rub, price_note,
                visit_min, visit_max, lat, lon, dgis_place_id, price_source_url,
                provider_name, search_aliases_json, allow_coords_only, is_active, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name, level=excluded.level,
                parent_id=excluded.parent_id, relation=excluded.relation,
                place_type=excluded.place_type, tags_json=excluded.tags_json,
                access_cost=excluded.access_cost,
                base_price_from_rub=excluded.base_price_from_rub,
                base_price_to_rub=excluded.base_price_to_rub,
                price_note=excluded.price_note, visit_min=excluded.visit_min,
                visit_max=excluded.visit_max,
                lat=COALESCE(places.lat, excluded.lat),
                lon=COALESCE(places.lon, excluded.lon),
                dgis_place_id=COALESCE(places.dgis_place_id, excluded.dgis_place_id),
                provider_name=COALESCE(places.provider_name, excluded.provider_name),
                search_aliases_json=CASE
                    WHEN excluded.search_aliases_json IS NOT NULL
                         AND excluded.search_aliases_json != '[]'
                    THEN excluded.search_aliases_json
                    ELSE places.search_aliases_json
                END,
                allow_coords_only=MAX(places.allow_coords_only, excluded.allow_coords_only),
                price_source_url=excluded.price_source_url,
                updated_at=CURRENT_TIMESTAMP
        """, (
            row.id, row.city_id, row.name, row.level, row.parent_id, row.relation,
            row.place_type, json.dumps(row.tags, ensure_ascii=False), row.access_cost,
            row.base_price_from_rub, row.base_price_to_rub, row.price_note,
            row.visit_min, row.visit_max, row.lat, row.lon, row.dgis_place_id,
            row.price_source_url, row.provider_name,
            json.dumps(row.search_aliases, ensure_ascii=False), int(row.allow_coords_only),
            int(row.is_active),
        ))

    def has_city(self, city_id: str) -> bool:
        with self._lock:
            return self._connection.execute(
                "SELECT 1 FROM cities WHERE city_id = ?", (city_id,)
            ).fetchone() is not None

    def city_name(self, city_id: str) -> str | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT name FROM cities WHERE city_id = ?", (city_id,)
            ).fetchone()
        return str(row[0]) if row else None

    def resolved_count(self, city_id: str) -> int:
        with self._lock:
            row = self._connection.execute(
                """SELECT COUNT(*) FROM places WHERE city_id = ? AND is_active = 1
                   AND lat IS NOT NULL AND lon IS NOT NULL
                   AND (level IN ('AREA', 'COMPLEX') OR allow_coords_only = 1
                        OR dgis_place_id IS NOT NULL)""",
                (city_id,),
            ).fetchone()
        return int(row[0]) if row else 0

    def list_places(self, city_id: str, *, resolved_only: bool = False) -> list[CatalogPlace]:
        query = "SELECT * FROM places WHERE city_id = ? AND is_active = 1"
        if resolved_only:
            query += (" AND lat IS NOT NULL AND lon IS NOT NULL"
                      " AND (level IN ('AREA', 'COMPLEX') OR allow_coords_only = 1"
                      " OR dgis_place_id IS NOT NULL)")
        query += " ORDER BY id"
        with self._lock:
            rows = self._connection.execute(query, (city_id,)).fetchall()
        return [self._from_row(row) for row in rows]

    def get_by_ids(self, place_ids: Iterable[str]) -> list[CatalogPlace]:
        identifiers = list(dict.fromkeys(place_ids))
        if not identifiers:
            return []
        placeholders = ",".join("?" for _ in identifiers)
        with self._lock:
            rows = self._connection.execute(
                f"SELECT * FROM places WHERE id IN ({placeholders})", identifiers,
            ).fetchall()
        by_id = {row[0]: self._from_row(row) for row in rows}
        return [by_id[value] for value in identifiers if value in by_id]

    def children_of(self, parent_id: str) -> list[CatalogPlace]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM places WHERE parent_id = ? AND is_active = 1 ORDER BY id",
                (parent_id,),
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def unresolved(self, city_id: str | None = None) -> list[CatalogPlace]:
        query = """SELECT * FROM places WHERE is_active = 1 AND
                   (lat IS NULL OR lon IS NULL OR
                    (allow_coords_only = 0 AND level = 'POI' AND dgis_place_id IS NULL) OR
                    (allow_coords_only = 0 AND dgis_place_id IS NOT NULL
                     AND provider_name IS NULL))"""
        params: tuple[str, ...] = ()
        if city_id:
            query += " AND city_id = ?"
            params = (city_id,)
        query += " ORDER BY city_id, id"
        with self._lock:
            rows = self._connection.execute(query, params).fetchall()
        return [self._from_row(row) for row in rows]

    def update_resolution(self, catalog_id: str, dgis_place_id: str | None,
                          provider_name: str, lat: float, lon: float) -> None:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """UPDATE places SET
                   dgis_place_id = COALESCE(dgis_place_id, ?),
                   provider_name = COALESCE(provider_name, ?),
                   lat = CASE WHEN lat IS NULL OR lon IS NULL THEN ? ELSE lat END,
                   lon = CASE WHEN lat IS NULL OR lon IS NULL THEN ? ELSE lon END,
                   updated_at = CURRENT_TIMESTAMP WHERE id = ?""",
                (dgis_place_id, provider_name, lat, lon, catalog_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(catalog_id)

    def apply_manual_overrides(self, overrides: dict[str, dict[str, object]]) -> int:
        """Apply explicitly reviewed provider/coordinate values, overwriting old ones."""
        allowed = {"lat", "lon", "dgis_place_id", "provider_name", "allow_coords_only"}
        applied = 0
        with self._lock, self._connection:
            for catalog_id, values in overrides.items():
                if not isinstance(catalog_id, str) or not isinstance(values, dict):
                    raise CatalogImportError("Manual overrides должны быть объектом id -> поля")
                unknown = set(values) - allowed
                if unknown:
                    raise CatalogImportError(
                        f"{catalog_id}: неизвестные override-поля: {', '.join(sorted(unknown))}"
                    )
                has_lat, has_lon = "lat" in values, "lon" in values
                if has_lat != has_lon:
                    raise CatalogImportError(
                        f"{catalog_id}: lat и lon в override должны задаваться вместе"
                    )
                assignments: list[str] = []
                params: list[object] = []
                if has_lat:
                    try:
                        lat, lon = float(values["lat"]), float(values["lon"])
                    except (TypeError, ValueError) as exc:
                        raise CatalogImportError(
                            f"{catalog_id}: lat/lon должны быть числами"
                        ) from exc
                    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
                        raise CatalogImportError(f"{catalog_id}: координаты вне диапазона")
                    assignments.extend(("lat = ?", "lon = ?"))
                    params.extend((lat, lon))
                for field in ("dgis_place_id", "provider_name"):
                    if field in values:
                        value = values[field]
                        if value is not None and (not isinstance(value, str) or not value.strip()):
                            raise CatalogImportError(
                                f"{catalog_id}: {field} должен быть непустой строкой или null"
                            )
                        assignments.append(f"{field} = ?")
                        params.append(value.strip() if isinstance(value, str) else None)
                if "allow_coords_only" in values:
                    value = values["allow_coords_only"]
                    if value not in {True, False, 0, 1}:
                        raise CatalogImportError(
                            f"{catalog_id}: allow_coords_only must be boolean or 0/1"
                        )
                    assignments.append("allow_coords_only = ?")
                    params.append(int(bool(value)))
                if not assignments:
                    raise CatalogImportError(f"{catalog_id}: override не содержит данных")
                params.append(catalog_id)
                cursor = self._connection.execute(
                    f"UPDATE places SET {', '.join(assignments)}, "
                    "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    params,
                )
                if cursor.rowcount != 1:
                    raise CatalogImportError(f"Неизвестный catalog id в override: {catalog_id}")
                applied += 1
        return applied

    def enrichment_groups(self, city_id: str | None = None) -> tuple[
            list[CatalogPlace], list[CatalogPlace], list[CatalogPlace]]:
        if city_id:
            places = self.list_places(city_id)
        else:
            with self._lock:
                rows = self._connection.execute(
                    "SELECT * FROM places WHERE is_active = 1 ORDER BY city_id, id"
                ).fetchall()
            places = [self._from_row(row) for row in rows]
        provider = [place for place in places
                    if place.lat is not None and place.lon is not None
                    and place.dgis_place_id is not None
                    and place.provider_name is not None]
        coords_only = [place for place in places
                       if place.lat is not None and place.lon is not None
                       and (place.level in {"AREA", "COMPLEX"} or place.allow_coords_only)
                       and not (place.dgis_place_id is not None and place.provider_name is not None)]
        ready_ids = {place.id for place in [*provider, *coords_only]}
        unresolved = [place for place in places if place.id not in ready_ids]
        return provider, coords_only, unresolved

    @staticmethod
    def _from_row(row: sqlite3.Row) -> CatalogPlace:
        return CatalogPlace(
            id=row["id"], city_id=row["city_id"], name=row["name"],
            level=row["level"], parent_id=row["parent_id"], relation=row["relation"],
            place_type=row["place_type"], tags=tuple(json.loads(row["tags_json"])),
            access_cost=row["access_cost"],
            base_price_from_rub=row["base_price_from_rub"],
            base_price_to_rub=row["base_price_to_rub"], price_note=row["price_note"],
            visit_min=row["visit_min"], visit_max=row["visit_max"], lat=row["lat"],
            lon=row["lon"], dgis_place_id=row["dgis_place_id"],
            provider_name=row["provider_name"],
            search_aliases=tuple(json.loads(row["search_aliases_json"] or "[]")),
            allow_coords_only=bool(row["allow_coords_only"]),
            price_source_url=row["price_source_url"], is_active=bool(row["is_active"]),
        )

    def close(self) -> None:
        with self._lock:
            self._connection.close()


class CatalogPlaceProvider:
    """Apply catalogue hard filters and rank a compact planner shortlist."""

    def __init__(self, catalog: PlaceCatalog, minimum_resolved: int = 2):
        self.catalog = catalog
        self.minimum_resolved = max(2, minimum_resolved)

    def has_city(self, city_id: str) -> bool:
        return self.catalog.has_city(city_id)

    def has_sufficient_resolved(self, city_id: str) -> bool:
        return self.catalog.resolved_count(city_id) >= self.minimum_resolved

    def get_by_ids(self, place_ids: Iterable[str]) -> list[CatalogPlace]:
        return self.catalog.get_by_ids(place_ids)

    def children_of(self, parent_id: str) -> list[CatalogPlace]:
        return self.catalog.children_of(parent_id)

    def list_candidates(self, city_id: str, preview: QueryPreview,
                        anchor: SearchArea) -> list[PlaceCandidate]:
        ranked, trace = self.rank_candidates(city_id, preview, anchor)
        scores = {str(item["id"]): item for item in trace}
        return [self._to_candidate(
            row, preview, self._relaxation_level(row, catalog_query_from_preview(preview)),
            semantic_score=float(scores[row.id]["semantic_score"]),
            final_score=float(scores[row.id]["final_score"]),
            lexical_score=float(scores[row.id].get("lexical_score", 0.0)),
        ) for row in ranked]

    def rank_candidates(self, city_id: str, preview: QueryPreview,
                        anchor: SearchArea) -> tuple[list[CatalogPlace], list[dict[str, object]]]:
        """Return deterministic shortlist and diagnostic values without provider calls."""
        query = catalog_query_from_preview(preview)
        rows = self.catalog.list_places(city_id, resolved_only=True)
        rows = [row for row in rows if self._passes_hard_filters(row, query)]
        if not rows:
            return [], []
        lexical = {row.id: self._lexical_score(row, query) for row in rows}
        semantic = {row.id: self._semantic_score(row, query, lexical[row.id]) for row in rows}
        geo = {row.id: self._geo_score(row, anchor) for row in rows}
        levels = {row.id: self._relaxation_level(row, query) for row in rows}
        ranked: list[CatalogPlace] = []
        trace: list[dict[str, object]] = []
        type_counts: dict[str, int] = {}
        narrow_type = self._narrow_type_request(query)
        for level in range(4):
            remaining = [row for row in rows if levels[row.id] == level]
            while remaining and len(ranked) < 50:
                def score(row: CatalogPlace) -> float:
                    repeats = type_counts.get(row.place_type, 0)
                    variety = 1.0 if narrow_type else max(0.0, 1.0 - repeats * 0.35)
                    return semantic[row.id] * 0.60 + geo[row.id] * 0.25 + variety * 0.15
                selected = max(remaining, key=lambda row: (score(row), row.id))
                repeats = type_counts.get(selected.place_type, 0)
                variety = 1.0 if narrow_type else max(0.0, 1.0 - repeats * 0.35)
                trace.append({
                    "id": selected.id, "name": selected.name, "type": selected.place_type,
                    "tags": list(selected.tags), "relaxation_level": level,
                    "semantic_score": round(semantic[selected.id], 4),
                    "lexical_score": round(lexical[selected.id], 4),
                    "geo_score": round(geo[selected.id], 4),
                    "variety_adjustment": round(variety, 4),
                    "final_score": round(score(selected), 4),
                })
                remaining.remove(selected)
                ranked.append(selected)
                type_counts[selected.place_type] = type_counts.get(selected.place_type, 0) + 1
        return ranked[:50], trace[:50]

    @staticmethod
    def _passes_hard_filters(row: CatalogPlace, query: CatalogQuery) -> bool:
        if row.place_type in query.excluded_types or set(row.tags).intersection(query.excluded_tags):
            return False
        if any(_row_matches_concept(row, concept) for concept in query.excluded_concepts):
            return False
        if query.free_only and not (row.access_cost == "FREE" or
                                    (row.access_cost == "MIXED"
                                     and row.base_price_from_rub == 0)):
            return False
        if (query.max_budget is not None and row.base_price_from_rub is not None
                and row.base_price_from_rub > query.max_budget):
            return False
        return all(_row_matches_concept(row, concept) for concept in query.hard_concepts)

    @staticmethod
    def _semantic_score(row: CatalogPlace, query: CatalogQuery,
                        lexical_score: float = 0.0) -> float:
        if not query.requested_concepts:
            base = 0.55 + (0.15 if "LOCAL_CULTURE" in row.tags else 0.0)
            return min(1.0, base + lexical_score * 0.25)
        possible = sum(PRIORITY_WEIGHTS[priority] for priority in query.requested_tags.values())
        matched = sum(PRIORITY_WEIGHTS[priority] for tag, priority in query.requested_tags.items()
                      if tag in row.tags)
        # Explicit museum/park requests can be expressed by type even with sparse tags.
        for concept in query.requested_concepts:
            if type_matches_concept(row.place_type, concept):
                matched += PRIORITY_WEIGHTS.get("MEDIUM", 2) * 0.35
                possible += PRIORITY_WEIGHTS.get("MEDIUM", 2) * 0.35
        base = matched / max(1, possible)
        # Tags remain primary; a direct name/alias signal differentiates a
        # specific request ("фрески", "Циолковский") among similar tagged POI.
        return min(1.0, base * 0.78 + lexical_score * 0.22)

    @staticmethod
    def _lexical_score(row: CatalogPlace, query: CatalogQuery) -> float:
        if not query.specific_terms:
            return 0.0
        haystack = normalize_lexical_tokens(" ".join(
            [row.name, row.provider_name or "", *row.search_aliases]
        ))
        if not haystack:
            return 0.0
        matched = sum(1 for term in query.specific_terms
                      if _lexical_term_matches(term, haystack))
        return matched / len(query.specific_terms)

    @staticmethod
    def _relaxation_level(row: CatalogPlace, query: CatalogQuery) -> int:
        """0=all concepts, 1=some direct, 2=related, 3=neutral fill."""
        concepts = query.requested_concepts
        if not concepts:
            return 3
        direct = [_row_matches_concept(row, concept) for concept in concepts]
        if all(direct):
            return 0
        if any(direct):
            return 1
        related = set().union(*(RELATED_TAGS.get(tag, frozenset())
                                for tag in query.requested_tags))
        return 2 if related.intersection(row.tags) else 3

    @staticmethod
    def _geo_score(row: CatalogPlace, anchor: SearchArea) -> float:
        assert row.lat is not None and row.lon is not None
        distance = _haversine_meters((anchor.lat, anchor.lon), (row.lat, row.lon))
        scale = max(1500, anchor.radiusMeters)
        return max(0.0, 1.0 - distance / (scale * 1.5))

    @staticmethod
    def _narrow_type_request(query: CatalogQuery) -> bool:
        return len(query.requested_concepts) == 1 and query.requested_concepts[0] in {
            "MUSEUMS", "PARKS", "RELIGIOUS_PLACES", "VIEWPOINTS",
        }

    @staticmethod
    def _to_candidate(row: CatalogPlace, preview: QueryPreview,
                      relaxation_level: int | None = None,
                      semantic_score: float | None = None,
                      final_score: float | None = None,
                      lexical_score: float | None = None) -> PlaceCandidate:
        assert row.lat is not None and row.lon is not None
        concepts = [concept for concept in preview.interests
                    if _row_matches_concept(row, concept)]
        return PlaceCandidate(
            placeId=row.dgis_place_id or f"catalog:{row.id}",
            name=row.name, lat=row.lat, lon=row.lon,
            rubrics=[row.place_type, *row.tags], schedule={}, isFood=False,
            providerType=row.place_type, matchedConcepts=concepts,
            catalogId=row.id, catalogLevel=row.level, catalogParentId=row.parent_id,
            catalogRelation=row.relation, catalogType=row.place_type,
            catalogTags=list(row.tags), catalogAccessCost=row.access_cost,
            catalogPriceFromRub=row.base_price_from_rub,
            catalogPriceToRub=row.base_price_to_rub,
            catalogVisitMin=row.visit_min, catalogVisitMax=row.visit_max,
            catalogRelaxationLevel=relaxation_level,
            catalogSemanticScore=semantic_score, catalogFinalScore=final_score,
            catalogLexicalScore=lexical_score,
        )


def _row_matches_concept(row: CatalogPlace, concept: str) -> bool:
    tags = CONCEPT_TAGS.get(concept, frozenset())
    if tags and tags.intersection(row.tags):
        return True
    return type_matches_concept(row.place_type, concept)


def _lexical_term_matches(term: str, haystack: tuple[str, ...]) -> bool:
    """Small deterministic Russian normalization; intentionally no edit distance."""
    stems = {
        "космос": ("космос", "космич"),
        "космический": ("космос", "космич"),
        "фрески": ("фреск", "роспис"),
        "фреска": ("фреск", "роспис"),
        "росписи": ("роспис", "фреск"),
        "роспись": ("роспис", "фреск"),
    }.get(term, (term,))
    return any(token.startswith(stem) for stem in stems for token in haystack)


def _haversine_meters(start: tuple[float, float], end: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*start, *end))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6_371_000 * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))

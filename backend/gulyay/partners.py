"""Fail-closed partner registry and optional offer selection.

Production data contains candidate brands only. A commercial card can be
created only when an operator has verified the provider brand id, explicitly
activated the registry row, and inserted a currently active offer.
"""
from __future__ import annotations

import math
import os
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .catalog import default_catalog_path
from .geo import (DgisGeoProvider, GeoRouteNotFound, PartnerBranch)
from .models import (PartnerOffer, PartnerOfferAction, WalkState)
from .route_builder import city_timezone, schedule_status_at


PARTNER_BRANDS = (
    ("cofix", "Cofix", "COFFEE", "Cofix"),
    ("surf", "Surf Coffee", "COFFEE", "Surf Coffee"),
    ("drinkit", "Дринкит", "COFFEE", "Дринкит"),
    ("oneprice", "One Price Coffee", "COFFEE", "One Price Coffee"),
    ("thebull", "THE БЫК", "RESTAURANT", "THE БЫК"),
    ("tanuki", "Тануки", "RESTAURANT", "Тануки"),
    ("frank", "FRANK by Баста", "RESTAURANT", "FRANK by Баста"),
    ("chaihona1", "Чайхона №1 (Тимура Ланского)", "RESTAURANT",
     "Чайхона №1 Тимура Ланского"),
    ("syrovarnya", "Сыроварня", "RESTAURANT", "Сыроварня"),
)

NAME_SEARCH_PILOT = (
    ("drinkit", "Дринкит", "COFFEE"),
    ("surf", "Surf Coffee", "COFFEE"),
    ("oneprice", "One Price Coffee", "COFFEE"),
    ("thebull", "THE БЫК", "RESTAURANT"),
    ("tanuki", "Тануки", "RESTAURANT"),
    ("frank", "FRANK by Баста", "RESTAURANT"),
    ("syrovarnya", "Сыроварня", "RESTAURANT"),
)

MAX_WALKING_MINUTES = {"COFFEE": 25, "RESTAURANT": 25}
PREFERRED_WALKING_MINUTES = {"COFFEE": 20, "RESTAURANT": 20}
MAX_POSITION_AGE_SECONDS = 60
MAX_POSITION_ACCURACY_METERS = 50
BRANCHES_PER_BRAND_LIMIT = 3
ROUTING_CANDIDATE_LIMIT = 5
GEOGRAPHIC_PREFILTER_METERS = 4_000


@dataclass(frozen=True)
class PartnerBrand:
    partner_brand_id: str
    brand_name: str
    segment: str
    city_id: str
    dgis_brand_id: str | None
    dgis_id_status: str
    partnership_status: str
    is_active_partner: bool
    partner_discovery_enabled: bool
    initial_search_q: str


@dataclass(frozen=True)
class CommercialOffer:
    offer_id: str
    partner_brand_id: str
    city_id: str
    segment: str
    dgis_brand_id: str | None
    search_query: str
    title: str
    description: str
    valid_from: datetime
    valid_until: datetime
    button_text: str


class PartnerRegistry:
    def __init__(self, path: str | Path | None = None):
        resolved = str(path) if path is not None else default_catalog_path()
        if resolved != ":memory:":
            resolved = str(Path(resolved).expanduser().resolve())
            Path(resolved).parent.mkdir(parents=True, exist_ok=True)
        self.path = resolved
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(
            resolved, check_same_thread=False, timeout=10,
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA busy_timeout = 10000")
        self._connection.execute("PRAGMA foreign_keys = ON")
        if resolved != ":memory:":
            self._connection.execute("PRAGMA journal_mode = WAL")
        self._create_schema()
        self._seed_candidates()

    def _create_schema(self) -> None:
        with self._lock, self._connection:
            # A distinct registry name deliberately leaves the obsolete fixed-
            # venue partner_brands table intact if a pre-release DB contains it.
            self._connection.execute("""
                CREATE TABLE IF NOT EXISTS partner_brand_registry (
                    partner_brand_id TEXT NOT NULL,
                    brand_name TEXT NOT NULL,
                    segment TEXT NOT NULL CHECK (segment IN ('COFFEE', 'RESTAURANT')),
                    city_id TEXT NOT NULL,
                    dgis_brand_id TEXT NULL,
                    dgis_org_id TEXT NULL,
                    initial_search_q TEXT NOT NULL,
                    dgis_id_status TEXT NOT NULL DEFAULT 'PENDING_VERIFICATION'
                        CHECK (dgis_id_status IN
                            ('PENDING_VERIFICATION', 'VERIFIED', 'AMBIGUOUS', 'NOT_FOUND')),
                    partnership_status TEXT NOT NULL DEFAULT 'CANDIDATE'
                        CHECK (partnership_status IN
                            ('CANDIDATE', 'NEGOTIATING', 'ACTIVE', 'PAUSED', 'REJECTED')),
                    is_active_partner INTEGER NOT NULL DEFAULT 0
                        CHECK (is_active_partner IN (0, 1)),
                    partner_discovery_enabled INTEGER NOT NULL DEFAULT 0
                        CHECK (partner_discovery_enabled IN (0, 1)),
                    website TEXT NULL,
                    notes TEXT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (partner_brand_id, city_id)
                )
            """)
            self._connection.execute("""
                CREATE TABLE IF NOT EXISTS partner_offers (
                    offer_id TEXT PRIMARY KEY,
                    partner_brand_id TEXT NOT NULL,
                    city_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    valid_from TEXT NOT NULL,
                    valid_until TEXT NOT NULL,
                    timezone TEXT NOT NULL,
                    button_text TEXT NOT NULL,
                    action_type TEXT NOT NULL CHECK (action_type = 'OPEN_DGIS'),
                    status TEXT NOT NULL DEFAULT 'PAUSED'
                        CHECK (status IN ('ACTIVE', 'PAUSED')),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (partner_brand_id, city_id)
                        REFERENCES partner_brand_registry(partner_brand_id, city_id)
                )
            """)
            self._connection.execute("""
                CREATE INDEX IF NOT EXISTS idx_partner_offer_selection
                ON partner_offers (city_id, status, valid_from, valid_until)
            """)

    def _seed_candidates(self) -> None:
        with self._lock, self._connection:
            self._connection.executemany("""
                INSERT OR IGNORE INTO partner_brand_registry
                    (partner_brand_id, brand_name, segment, city_id,
                     initial_search_q, dgis_id_status, partnership_status,
                     is_active_partner, partner_discovery_enabled)
                VALUES (?, ?, ?, 'moscow', ?, 'PENDING_VERIFICATION',
                        'CANDIDATE', 0, 0)
            """, PARTNER_BRANDS)

    def list_brands(self, city_id: str | None = None) -> list[PartnerBrand]:
        sql = "SELECT * FROM partner_brand_registry"
        params: tuple[str, ...] = ()
        if city_id is not None:
            sql += " WHERE city_id = ?"
            params = (city_id,)
        sql += " ORDER BY city_id, partner_brand_id"
        with self._lock:
            rows = self._connection.execute(sql, params).fetchall()
        return [self._brand_from_row(row) for row in rows]

    def get_brand(self, partner_brand_id: str, city_id: str) -> PartnerBrand | None:
        with self._lock:
            row = self._connection.execute("""
                SELECT * FROM partner_brand_registry
                WHERE partner_brand_id = ? AND city_id = ?
            """, (partner_brand_id, city_id)).fetchone()
        return None if row is None else self._brand_from_row(row)

    def confirm_brand_id(self, partner_brand_id: str, city_id: str,
                         dgis_brand_id: str) -> bool:
        with self._lock, self._connection:
            existing = self._connection.execute("""
                SELECT dgis_brand_id, dgis_id_status
                FROM partner_brand_registry
                WHERE partner_brand_id = ? AND city_id = ?
            """, (partner_brand_id, city_id)).fetchone()
            if existing is None:
                return False
            if (existing["dgis_id_status"] == "VERIFIED"
                    and existing["dgis_brand_id"]
                    and existing["dgis_brand_id"] != dgis_brand_id):
                return False
            cursor = self._connection.execute("""
                UPDATE partner_brand_registry
                SET dgis_brand_id = ?, dgis_id_status = 'VERIFIED',
                    updated_at = CURRENT_TIMESTAMP
                WHERE partner_brand_id = ? AND city_id = ?
            """, (dgis_brand_id, partner_brand_id, city_id))
            return cursor.rowcount == 1

    def set_brand_commercial_state(self, partner_brand_id: str, city_id: str,
                                   partnership_status: str,
                                   is_active_partner: bool,
                                   discovery_enabled: bool) -> bool:
        if partnership_status not in {
                "CANDIDATE", "NEGOTIATING", "ACTIVE", "PAUSED", "REJECTED"}:
            raise ValueError("Unsupported partnership status")
        with self._lock, self._connection:
            cursor = self._connection.execute("""
                UPDATE partner_brand_registry
                SET partnership_status = ?, is_active_partner = ?,
                    partner_discovery_enabled = ?, updated_at = CURRENT_TIMESTAMP
                WHERE partner_brand_id = ? AND city_id = ?
            """, (partnership_status, int(is_active_partner), int(discovery_enabled),
                  partner_brand_id, city_id))
            return cursor.rowcount == 1

    def save_offer(self, *, offer_id: str, partner_brand_id: str, city_id: str,
                   title: str, description: str, valid_from: datetime,
                   valid_until: datetime, timezone_name: str,
                   button_text: str, status: str) -> None:
        if status not in {"ACTIVE", "PAUSED"}:
            raise ValueError("Unsupported offer status")
        if valid_from.tzinfo is None or valid_until.tzinfo is None:
            raise ValueError("Offer dates must include timezone")
        if valid_until <= valid_from:
            raise ValueError("Offer end must be after start")
        try:
            ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Unknown offer timezone") from exc
        with self._lock, self._connection:
            self._connection.execute("""
                INSERT INTO partner_offers
                    (offer_id, partner_brand_id, city_id, title, description,
                     valid_from, valid_until, timezone, button_text,
                     action_type, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN_DGIS', ?)
                ON CONFLICT(offer_id) DO UPDATE SET
                    title = excluded.title,
                    description = excluded.description,
                    valid_from = excluded.valid_from,
                    valid_until = excluded.valid_until,
                    timezone = excluded.timezone,
                    button_text = excluded.button_text,
                    action_type = excluded.action_type,
                    status = excluded.status,
                    updated_at = CURRENT_TIMESTAMP
            """, (offer_id, partner_brand_id, city_id, title, description,
                  _utc_text(valid_from), _utc_text(valid_until), timezone_name,
                  button_text, status))

    def eligible_offers(self, city_id: str, moment: datetime) -> list[CommercialOffer]:
        current = _utc_text(moment)
        with self._lock:
            rows = self._connection.execute("""
                SELECT offers.*, brands.segment, brands.initial_search_q, brands.dgis_brand_id
                FROM partner_offers AS offers
                JOIN partner_brand_registry AS brands
                  ON brands.partner_brand_id = offers.partner_brand_id
                 AND brands.city_id = offers.city_id
                WHERE offers.city_id = ?
                  AND offers.status = 'ACTIVE'
                  AND offers.valid_from <= ? AND offers.valid_until >= ?
                  AND brands.partnership_status = 'ACTIVE'
                  AND brands.is_active_partner = 1
                  AND brands.partner_discovery_enabled = 1
                ORDER BY offers.offer_id
            """, (city_id, current, current)).fetchall()
        return [CommercialOffer(
            offer_id=row["offer_id"], partner_brand_id=row["partner_brand_id"],
            city_id=row["city_id"], segment=row["segment"],
            dgis_brand_id=row["dgis_brand_id"],
            search_query=row["initial_search_q"], title=row["title"],
            description=row["description"],
            valid_from=_parse_utc(row["valid_from"]),
            valid_until=_parse_utc(row["valid_until"]),
            button_text=row["button_text"],
        ) for row in rows]

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    @staticmethod
    def _brand_from_row(row: sqlite3.Row) -> PartnerBrand:
        return PartnerBrand(
            partner_brand_id=row["partner_brand_id"], brand_name=row["brand_name"],
            segment=row["segment"], city_id=row["city_id"],
            dgis_brand_id=row["dgis_brand_id"], dgis_id_status=row["dgis_id_status"],
            partnership_status=row["partnership_status"],
            is_active_partner=bool(row["is_active_partner"]),
            partner_discovery_enabled=bool(row["partner_discovery_enabled"]),
            initial_search_q=row["initial_search_q"],
        )


def _name_search_preview_offers(moment: datetime) -> list[CommercialOffer]:
    """Transient preview only; these networks are not commercial partners."""
    return [CommercialOffer(
        offer_id=f"preview_{partner_id}_moscow", partner_brand_id=partner_id,
        city_id="moscow", segment=segment, dgis_brand_id=None,
        search_query=name, title="Зайти по пути?",
        description="Тестовый поиск заведений. Не реклама и не партнёрская акция.",
        valid_from=moment, valid_until=moment, button_text="Открыть в 2ГИС",
    ) for partner_id, name, segment in NAME_SEARCH_PILOT]


class PartnerOfferSelector:
    def __init__(self, registry: PartnerRegistry, geo: DgisGeoProvider):
        self.registry = registry
        self.geo = geo

    def select(self, state: WalkState, city_id: str,
               now: datetime | None = None) -> PartnerOffer | None:
        moment = _utc(now or datetime.now(timezone.utc))
        session = state.session
        if session.status != "ACTIVE" or session.phase != "VISITING":
            return None

        # This database check intentionally precedes every 2GIS operation.
        preview = (city_id == "moscow"
                   and os.getenv("GULYAY_ENV") in {"test", "development"}
                   and os.getenv("GULYAY_PARTNER_PREVIEW") == "1")
        offers = (_name_search_preview_offers(moment) if preview else
                  self.registry.eligible_offers(city_id, moment))
        if not offers:
            return None
        position = state.lastPosition
        if position is None or position.accuracyMeters > MAX_POSITION_ACCURACY_METERS:
            return None
        measured = _utc(position.measuredAt)
        age = (moment - measured).total_seconds()
        if age < -5 or age > MAX_POSITION_AGE_SECONDS:
            return None

        origin = (position.lat, position.lon)
        # Search only verified active brands, merge their nearby branches, then
        # spend a single bounded routing budget across the combined pool.
        offers_by_name: dict[str, list[CommercialOffer]] = {}
        for offer in offers:
            offers_by_name.setdefault(offer.search_query, []).append(offer)
        candidates: list[tuple[float, CommercialOffer, PartnerBranch]] = []
        for name, brand_offers in offers_by_name.items():
            branches = self.geo.search_partner_branches_by_name(city_id, name, origin)
            for branch in branches[:BRANCHES_PER_BRAND_LIMIT]:
                direct_distance = _haversine(origin, (branch.lat, branch.lon))
                if direct_distance > GEOGRAPHIC_PREFILTER_METERS:
                    continue
                for offer in brand_offers:
                    candidates.append((direct_distance, offer, branch))
        candidates.sort(key=lambda value: (
            value[0], value[1].offer_id, value[2].dgis_place_id,
        ))

        choices: list[tuple[tuple[int, int, int, str], CommercialOffer,
                            PartnerBranch, int]] = []
        routed_branches: dict[str, object] = {}
        routing_attempts = 0
        for _, offer, branch in candidates:
            if branch.dgis_place_id in routed_branches:
                leg = routed_branches[branch.dgis_place_id]
            else:
                if routing_attempts >= ROUTING_CANDIDATE_LIMIT:
                    break
                routing_attempts += 1
                try:
                    leg = self.geo.walking_leg(
                        origin, (branch.lat, branch.lon), 0, 1,
                    )
                except GeoRouteNotFound:
                    routed_branches[branch.dgis_place_id] = None
                    continue
                routed_branches[branch.dgis_place_id] = leg
            if leg is None or leg.durationSeconds > MAX_WALKING_MINUTES[offer.segment] * 60:
                continue
            arrival = moment.astimezone(city_timezone()) + timedelta(
                seconds=leg.durationSeconds,
            )
            if schedule_status_at(branch.schedule, arrival, 1) != "OPEN":
                continue
            minutes = max(1, math.ceil(leg.durationSeconds / 60))
            score = (int(minutes > PREFERRED_WALKING_MINUTES[offer.segment]),
                     leg.durationSeconds, leg.distanceMeters, offer.offer_id)
            choices.append((score, offer, branch, minutes))
        if not choices:
            return None
        _, offer, branch, minutes = min(choices, key=lambda choice: choice[0])
        safe_place_id = quote(branch.dgis_place_id, safe="")
        return PartnerOffer(
            offerId=offer.offer_id,
            partnerBrandId=offer.partner_brand_id,
            dgisPlaceId=branch.dgis_place_id,
            title=offer.title,
            description=offer.description,
            venueName=branch.name,
            walkingMinutes=minutes,
            isCommercial=not preview,
            action=PartnerOfferAction(
                type="OPEN_DGIS", label=offer.button_text,
                url=f"https://2gis.ru/{city_id}/firm/{safe_place_id}",
            ),
        )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timezone-aware datetime required")
    return value.astimezone(timezone.utc)


def _utc_text(value: datetime) -> str:
    return _utc(value).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _haversine(start: tuple[float, float], end: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*start, *end))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    value = (math.sin(dlat / 2) ** 2
             + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2)
    return 6_371_000 * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))

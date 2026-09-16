"""Persistent route state used by API-07 and API-08.

SQLite is part of Python, works on Windows without a separate server and keeps
route revisions available after a backend restart.
"""
from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path
from uuid import UUID

from .models import CreateRoute, Route, WalkState


class RouteRepository:
    def __init__(self, path: str | Path | None = None):
        resolved = str(path) if path is not None else os.getenv("GULYAY_DB_PATH")
        if not resolved:
            resolved = str(Path(__file__).resolve().parent.parent / "data" / "gulyay.sqlite3")
        if resolved != ":memory:":
            resolved = str(Path(resolved).expanduser().resolve())
            Path(resolved).parent.mkdir(parents=True, exist_ok=True)
        self.path = resolved
        try:
            retention = int(os.getenv("GULYAY_ROUTE_RETENTION_HOURS", "24"))
        except ValueError:
            retention = 24
        self.retention_hours = max(1, min(168, retention))
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(resolved, check_same_thread=False, timeout=10)
        self._connection.execute("PRAGMA busy_timeout = 10000")
        self._connection.execute("PRAGMA foreign_keys = ON")
        if resolved != ":memory:":
            self._connection.execute("PRAGMA journal_mode = WAL")
        self._connection.execute("""
            CREATE TABLE IF NOT EXISTS routes (
                route_id TEXT PRIMARY KEY,
                owner_session TEXT NOT NULL,
                route_version INTEGER NOT NULL,
                route_json TEXT NOT NULL,
                input_json TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self._connection.execute("""
            CREATE TABLE IF NOT EXISTS route_versions (
                route_id TEXT NOT NULL,
                route_version INTEGER NOT NULL,
                route_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (route_id, route_version),
                FOREIGN KEY (route_id) REFERENCES routes(route_id) ON DELETE CASCADE
            )
        """)
        self._connection.execute("""
            CREATE TABLE IF NOT EXISTS walks (
                walk_id TEXT PRIMARY KEY,
                route_id TEXT NOT NULL,
                owner_session TEXT NOT NULL,
                walk_json TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (route_id) REFERENCES routes(route_id) ON DELETE CASCADE
            )
        """)
        self._connection.execute("""
            INSERT OR IGNORE INTO route_versions (route_id, route_version, route_json, created_at)
            SELECT route_id, route_version, route_json, updated_at FROM routes
        """)
        self._connection.commit()
        self.purge_expired()

    def save_new(self, route: Route, owner: UUID, payload: CreateRoute) -> None:
        self.purge_expired()
        with self._lock, self._connection:
            self._connection.execute(
                """INSERT INTO routes
                   (route_id, owner_session, route_version, route_json, input_json, updated_at)
                   VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                (str(route.routeId), str(owner), route.routeVersion,
                 route.model_dump_json(), payload.model_dump_json()),
            )
            self._connection.execute(
                """INSERT INTO route_versions (route_id, route_version, route_json)
                   VALUES (?, ?, ?)""",
                (str(route.routeId), route.routeVersion, route.model_dump_json()),
            )

    def get(self, route_id: UUID, owner: UUID) -> tuple[Route, CreateRoute] | None:
        self.purge_expired()
        with self._lock:
            row = self._connection.execute(
                "SELECT route_json, input_json FROM routes WHERE route_id = ? AND owner_session = ?",
                (str(route_id), str(owner)),
            ).fetchone()
        if row is None:
            return None
        try:
            return Route.model_validate_json(row[0]), CreateRoute.model_validate_json(row[1])
        except ValueError:
            return None

    def replace(self, route: Route, owner: UUID, payload: CreateRoute,
                base_version: int) -> bool:
        self.purge_expired()
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """UPDATE routes
                   SET route_version = ?, route_json = ?, input_json = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE route_id = ? AND owner_session = ? AND route_version = ?""",
                (route.routeVersion, route.model_dump_json(), payload.model_dump_json(),
                 str(route.routeId), str(owner), base_version),
            )
            if cursor.rowcount != 1:
                return False
            self._connection.execute(
                """INSERT INTO route_versions (route_id, route_version, route_json)
                   VALUES (?, ?, ?)""",
                (str(route.routeId), route.routeVersion, route.model_dump_json()),
            )
            return True

    def get_version(self, route_id: UUID, owner: UUID, version: int) -> Route | None:
        self.purge_expired()
        with self._lock:
            row = self._connection.execute(
                """SELECT versions.route_json
                   FROM route_versions AS versions
                   JOIN routes ON routes.route_id = versions.route_id
                   WHERE versions.route_id = ? AND routes.owner_session = ?
                         AND versions.route_version = ?""",
                (str(route_id), str(owner), version),
            ).fetchone()
        if row is None:
            return None
        try:
            return Route.model_validate_json(row[0])
        except ValueError:
            return None

    def delete(self, route_id: UUID, owner: UUID) -> bool:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                "DELETE FROM routes WHERE route_id = ? AND owner_session = ?",
                (str(route_id), str(owner)),
            )
            return cursor.rowcount == 1

    def save_walk(self, state: WalkState, owner: UUID) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """INSERT INTO walks
                   (walk_id, route_id, owner_session, walk_json, updated_at)
                   VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                (str(state.session.walkId), str(state.session.routeId), str(owner),
                 state.model_dump_json()),
            )
            self._connection.execute(
                "UPDATE routes SET updated_at = CURRENT_TIMESTAMP WHERE route_id = ?",
                (str(state.session.routeId),),
            )

    def get_walk(self, walk_id: UUID, owner: UUID) -> WalkState | None:
        self.purge_expired()
        with self._lock:
            row = self._connection.execute(
                "SELECT walk_json FROM walks WHERE walk_id = ? AND owner_session = ?",
                (str(walk_id), str(owner)),
            ).fetchone()
        if row is None:
            return None
        try:
            return WalkState.model_validate_json(row[0])
        except ValueError:
            return None

    def replace_walk(self, state: WalkState, owner: UUID) -> bool:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """UPDATE walks SET walk_json = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE walk_id = ? AND owner_session = ?""",
                (state.model_dump_json(), str(state.session.walkId), str(owner)),
            )
            if cursor.rowcount == 1:
                self._connection.execute(
                    "UPDATE routes SET updated_at = CURRENT_TIMESTAMP WHERE route_id = ?",
                    (str(state.session.routeId),),
                )
            return cursor.rowcount == 1

    def find_active_walk(self, owner: UUID) -> WalkState | None:
        with self._lock:
            rows = self._connection.execute(
                """SELECT walk_json FROM walks WHERE owner_session = ?
                   ORDER BY updated_at DESC""", (str(owner),),
            ).fetchall()
        for row in rows:
            try:
                state = WalkState.model_validate_json(row[0])
            except ValueError:
                continue
            if state.session.status in {"ACTIVE", "PAUSED"}:
                return state
        return None

    def clear(self) -> None:
        with self._lock, self._connection:
            self._connection.execute("DELETE FROM walks")
            self._connection.execute("DELETE FROM route_versions")
            self._connection.execute("DELETE FROM routes")

    def purge_expired(self) -> None:
        modifier = f"-{self.retention_hours} hours"
        with self._lock, self._connection:
            self._connection.execute(
                "DELETE FROM routes WHERE updated_at < datetime('now', ?)", (modifier,)
            )
            self._connection.execute(
                "DELETE FROM route_versions WHERE route_id NOT IN (SELECT route_id FROM routes)"
            )

    def close(self) -> None:
        with self._lock:
            self._connection.close()

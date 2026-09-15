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

from .models import CreateRoute, Route


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
            return cursor.rowcount == 1

    def clear(self) -> None:
        with self._lock, self._connection:
            self._connection.execute("DELETE FROM routes")

    def purge_expired(self) -> None:
        modifier = f"-{self.retention_hours} hours"
        with self._lock, self._connection:
            self._connection.execute(
                "DELETE FROM routes WHERE updated_at < datetime('now', ?)", (modifier,)
            )

    def close(self) -> None:
        with self._lock:
            self._connection.close()

"""Structured diagnostics for one route-planning request."""
from __future__ import annotations

import json
import logging
import os
from typing import Any


LOGGER = logging.getLogger("gulyay.planning")
LOGGER.setLevel(logging.INFO)


def planning_log(trace_id: str | None, step: str, **details: Any) -> None:
    """Emit one searchable JSON record without changing API responses."""
    payload = {"traceId": trace_id or "local", "step": step, **details}
    LOGGER.info("route_planning %s", json.dumps(
        payload, ensure_ascii=False, default=str, separators=(",", ":"),
    ))


def catalog_debug_log(trace_id: str | None, step: str, **details: Any) -> None:
    """Verbose catalog-only trace, explicitly opt-in and never containing secrets."""
    if os.getenv("GULYAY_CATALOG_DEBUG", "").strip().lower() not in {"1", "true", "yes"}:
        return
    planning_log(trace_id, f"catalog_debug:{step}", **details)

"""Structured diagnostics for one route-planning request."""
from __future__ import annotations

import json
import logging
from typing import Any


LOGGER = logging.getLogger("gulyay.planning")
LOGGER.setLevel(logging.INFO)


def planning_log(trace_id: str | None, step: str, **details: Any) -> None:
    """Emit one searchable JSON record without changing API responses."""
    payload = {"traceId": trace_id or "local", "step": step, **details}
    LOGGER.info("route_planning %s", json.dumps(
        payload, ensure_ascii=False, default=str, separators=(",", ":"),
    ))

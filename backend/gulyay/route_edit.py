"""Apply explicit chat edits to the latest persisted route point list."""
from __future__ import annotations

from dataclasses import dataclass
import re

from .models import CreateRoute, PlaceCandidate, Route
from .route_builder import rebuild_route_with_points


class RouteEditNeedsClarification(Exception):
    def __init__(self, message: str):
        self.message = message


@dataclass(frozen=True)
class RouteEdit:
    operation: str
    first: str | None = None
    second: str | None = None
    unlimited_time: bool = False


def parse_route_edit(message: str) -> RouteEdit:
    text = " ".join(message.strip().split())
    normalized = _normalize(text)
    unlimited = bool(
        re.search(r"\b(?:время|продолжительность)\s+не\s+ограничен\w*\b", normalized)
        or re.search(r"\bбез\s+ограничени\w*\s+(?:по\s+)?времени\b", normalized)
    )
    if re.search(r"\b(?:перестрой|составь|построй)\w*\b.{0,30}\b(?:полностью|заново)\b", normalized):
        return RouteEdit("REBUILD", unlimited_time=unlimited)

    match = re.search(
        r"\b(?:поменяй|переставь)\s+(.+?)\s+(?:и|с)\s+(.+?)\s+местами\b",
        text, re.IGNORECASE,
    )
    if match:
        return RouteEdit("SWAP", _clean_name(match.group(1)),
                         _clean_name(match.group(2)), unlimited)

    match = re.search(r"\bзамени\s+(.+?)\s+на\s+(.+?)(?=\s*[,;(]|$)",
                      text, re.IGNORECASE)
    if match:
        return RouteEdit("REPLACE", _clean_name(match.group(1)),
                         _clean_name(match.group(2)), unlimited)

    match = re.search(r"\b(?:убери|удали|исключи)\s+(.+?)(?=\s*[,;(]|\s+а\s+все\b|$)",
                      text, re.IGNORECASE)
    if match:
        return RouteEdit("REMOVE", _clean_name(match.group(1)),
                         unlimited_time=unlimited)

    match = re.search(r"\b(?:добавь|добавить)\s+(.+?)(?=\s*[,;(]|$)",
                      text, re.IGNORECASE)
    if match:
        return RouteEdit("ADD", _clean_name(match.group(1)),
                         unlimited_time=unlimited)

    if unlimited:
        return RouteEdit("DURATION", unlimited_time=True)
    raise RouteEditNeedsClarification(
        "Уточните точечное изменение: что добавить, убрать, заменить или переставить"
    )


def apply_route_edit(current: Route, source: CreateRoute, edit: RouteEdit,
                     geo) -> tuple[Route, CreateRoute]:
    candidates = [_candidate_from_point(point) for point in current.points]
    if edit.operation == "REMOVE":
        index = _current_index(current, edit.first)
        candidates.pop(index)
    elif edit.operation == "ADD":
        if _optional_current_index(current, edit.first) is None:
            candidates.append(_resolve_new_candidate(current.cityId, edit.first, geo))
    elif edit.operation == "REPLACE":
        index = _current_index(current, edit.first)
        existing_replacement = _optional_current_index(current, edit.second)
        if existing_replacement is not None and existing_replacement != index:
            raise RouteEditNeedsClarification("Эта точка уже есть в маршруте")
        candidates[index] = _resolve_new_candidate(current.cityId, edit.second, geo)
    elif edit.operation == "SWAP":
        first = _current_index(current, edit.first)
        second = _current_index(current, edit.second)
        candidates[first], candidates[second] = candidates[second], candidates[first]
    elif edit.operation != "DURATION":
        raise RouteEditNeedsClarification("Не удалось определить изменение маршрута")

    filters = source.filters
    route_source = current
    if edit.unlimited_time:
        filters = filters.model_copy(update={"durationMinutes": None})
        route_source = current.model_copy(update={
            "durationSource": "default", "durationMode": "DEFAULT",
            "maxDurationMinutes": None, "durationOverrunAccepted": False,
        })
    next_query = source.query + "\nУточнение к текущему маршруту: " + _edit_summary(edit)
    payload = source.model_copy(update={"query": next_query, "filters": filters})
    rebuilt = rebuild_route_with_points(
        route_source, payload, candidates, geo,
        allow_duration_overrun=edit.unlimited_time,
    )
    updates: dict[str, object] = {
        "query": next_query,
        "filters": filters,
    }
    if edit.unlimited_time:
        requested = max(current.requestedMinutes, rebuilt.totalMinutes)
        updates.update({
            "requestedMinutes": requested,
            "unusedMinutes": requested - rebuilt.totalMinutes,
            "durationSource": "default",
            "durationMode": "DEFAULT",
            "maxDurationMinutes": None,
            "durationOverrunAccepted": False,
            "durationUtilization": round(rebuilt.totalMinutes / requested, 3),
        })
    return rebuilt.model_copy(update=updates), payload


def _candidate_from_point(point) -> PlaceCandidate:
    return PlaceCandidate(
        placeId=point.placeId, name=point.name, lat=point.lat, lon=point.lon,
        rubrics=[], schedule={}, isFood=point.isFood,
    )


def _resolve_new_candidate(city_id: str, requested_name: str | None, geo) -> PlaceCandidate:
    if not requested_name:
        raise RouteEditNeedsClarification("Не указано название точки")
    candidates = geo.search_candidates(city_id, requested_name)
    normalized = _normalize(requested_name)
    exact = [item for item in candidates if _normalize(item.name) == normalized]
    if len(exact) == 1:
        return exact[0]
    related = [item for item in candidates
               if normalized in _normalize(item.name) or _normalize(item.name) in normalized]
    if len(related) == 1:
        return related[0]
    if not candidates:
        raise RouteEditNeedsClarification(f"Точка «{requested_name}» не найдена")
    raise RouteEditNeedsClarification(
        f"Название «{requested_name}» неоднозначно — уточните место"
    )


def _current_index(route: Route, requested_name: str | None) -> int:
    index = _optional_current_index(route, requested_name)
    if index is None:
        raise RouteEditNeedsClarification(
            f"Точки «{requested_name or ''}» нет в текущем маршруте"
        )
    return index


def _optional_current_index(route: Route, requested_name: str | None) -> int | None:
    if not requested_name:
        return None
    requested = _normalize(requested_name)
    exact = [index for index, point in enumerate(route.points)
             if _normalize(point.name) == requested]
    if len(exact) == 1:
        return exact[0]
    related = [index for index, point in enumerate(route.points)
               if requested in _normalize(point.name) or _normalize(point.name) in requested]
    return related[0] if len(related) == 1 else None


def _clean_name(value: str) -> str:
    cleaned = value.strip(" \t\n\r.,;:()[]{}\"'«»")
    cleaned = re.sub(r"^(?:точку|место|объект)\s+", "", cleaned,
                     flags=re.IGNORECASE)
    return cleaned.strip()


def _normalize(value: str) -> str:
    return " ".join(re.findall(r"[а-яa-z0-9]+", value.casefold().replace("ё", "е")))


def _edit_summary(edit: RouteEdit) -> str:
    if edit.operation == "REMOVE":
        result = f"убрать {edit.first}"
    elif edit.operation == "ADD":
        result = f"добавить {edit.first}"
    elif edit.operation == "REPLACE":
        result = f"заменить {edit.first} на {edit.second}"
    elif edit.operation == "SWAP":
        result = f"поменять местами {edit.first} и {edit.second}"
    else:
        result = "изменить ограничение времени"
    return result + ("; время не ограничено" if edit.unlimited_time else "")

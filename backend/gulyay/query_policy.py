"""Safety rules for text that may become a 2GIS catalogue search query.

The LLM is allowed to describe user preferences, but route controls (walking
limits, time, start, direction and other instructions) must never leak into the
free-text ``q`` parameter of the 2GIS Places API.
"""
from __future__ import annotations

import re


_WALKING_CONSTRAINT = re.compile(
    r"(?:"
    r"(?:не\s+хочу\s+)?(?:далеко|много)\s+(?:идти|ходить)|"
    r"(?:идти|ходить)\s+(?:было\s+)?(?:не\s*далеко|недалеко|мало)|"
    r"недалеко\s+(?:идти|ходить)|"
    r"(?:меньше|мало)\s+ходить|"
    r"(?:коротк\w*|небольш\w*)\s+(?:пеш\w*\s+)?переход\w*|"
    r"без\s+(?:долг\w*|длинн\w*)\s+(?:пеш\w*\s+)?переход\w*|"
    r"(?:места|точки|локаци\w*)\s+(?:были\s+)?рядом|"
    r"до\s+(?:мест|точек|локаци\w*)[^,.]{0,50}(?:идти|ходить|пешком)|"
    r"между\s+(?:местами|точками|локациями)[^,.]{0,60}"
    r"(?:минут|метр|км|километр|идти|ходить|пешком)|"
    r"(?:идти|ходить|пешком|переход\w*)[^,.]{0,50}"
    r"(?:максимум|не\s+больше|не\s+дольше|не\s+дальше|до)\s*\d+"
    r")",
    re.IGNORECASE,
)

_NON_SEARCH_INSTRUCTION = re.compile(
    r"\b(?:чтобы|желательно|пожалуйста|маршрут|старт(?:овать)?|"
    r"нач(?:ать|инать)|в\s+сторону|по\s+направлению|между\s+точками|"
    r"между\s+локациями|максимум|не\s+больше|не\s+дольше|"
    r"без\s+очередей|по\s+пути|на\s+ваше\s+усмотрение|не\s+знаю)\b",
    re.IGNORECASE,
)


def normalize_user_text(value: str) -> str:
    return " ".join(value.strip(" \t\r\n,.;:").split())


def looks_like_walking_constraint(value: str | None) -> bool:
    if not value:
        return False
    normalized = normalize_user_text(value).casefold().replace("ё", "е")
    return bool(_WALKING_CONSTRAINT.search(normalized))


def sanitize_interest(value: str | None) -> str | None:
    """Return a catalogue-safe interest or drop a route/control instruction."""
    if not value:
        return None
    normalized = normalize_user_text(value)
    if not normalized or len(normalized) > 80:
        return None
    folded = normalized.casefold().replace("ё", "е")
    if looks_like_walking_constraint(folded) or _NON_SEARCH_INSTRUCTION.search(folded):
        return None
    if not re.search(r"[а-яa-z0-9]", folded):
        return None
    return normalized


def sanitize_interests(values: list[str]) -> list[str]:
    """Clean and deduplicate LLM interests without failing the whole route."""
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        safe = sanitize_interest(value)
        if safe is None:
            continue
        key = safe.casefold().replace("ё", "е")
        if key in seen:
            continue
        seen.add(key)
        result.append(safe)
    return result

"""Deterministic translation from public route intent to catalogue constraints."""
from __future__ import annotations

from dataclasses import dataclass

from .models import QueryPreview


PRIORITY_WEIGHTS = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}

# Keep this mapping independent from 2GIS rubrics. It describes our own seed tags.
CONCEPT_TAGS: dict[str, frozenset[str]] = {
    "ARCHITECTURE": frozenset({"ARCHITECTURE"}),
    "HISTORIC_PLACES": frozenset({"HISTORY"}),
    "LANDMARKS": frozenset({"HISTORY", "LOCAL_CULTURE"}),
    "PARKS": frozenset({"NATURE"}),
    "VIEWPOINTS": frozenset({"PANORAMIC"}),
    "RELIGIOUS_PLACES": frozenset({"RELIGION"}),
    "STREET_ART": frozenset({"ART_CULTURE", "CONTEMPORARY"}),
    "UNUSUAL_PLACES": frozenset({"UNUSUAL"}),
    "CHILD_FRIENDLY": frozenset({"FAMILY"}),
    "CULTURE": frozenset({"ART_CULTURE"}),
    "NATURE": frozenset({"NATURE"}),
    "ENTERTAINMENT": frozenset({"ACTIVE", "FAMILY"}),
    "SCIENCE": frozenset({"SCIENCE_TECH"}),
    "SOVIET": frozenset({"SOVIET"}),
    "MILITARY": frozenset({"MILITARY"}),
}

MUSEUM_LIKE_TYPES = frozenset({
    "museum", "art_museum", "history_museum", "science_museum", "house_museum",
    "city_museum", "gallery", "art_gallery",
})

# A controlled broadening used only after direct preference matches. It is not a
# replacement for the requested concept and never weakens explicit exclusions.
RELATED_TAGS: dict[str, frozenset[str]] = {
    "HISTORY": frozenset({"ARCHITECTURE", "LOCAL_CULTURE", "MILITARY"}),
    "ARCHITECTURE": frozenset({"HISTORY", "RELIGION", "ART_CULTURE"}),
    "SCIENCE_TECH": frozenset({"HISTORY", "UNUSUAL", "LOCAL_CULTURE"}),
    "UNUSUAL": frozenset({"CONTEMPORARY", "SCIENCE_TECH", "ART_CULTURE"}),
    "PANORAMIC": frozenset({"PHOTOGENIC", "NATURE", "ARCHITECTURE"}),
    "RELIGION": frozenset({"HISTORY", "ARCHITECTURE"}),
}


@dataclass(frozen=True)
class CatalogQuery:
    requested_tags: dict[str, str]
    required_tags: frozenset[str]
    excluded_concepts: frozenset[str]
    excluded_tags: frozenset[str]
    excluded_types: frozenset[str]
    with_children: bool
    unusual_places: bool
    free_only: bool
    max_budget: int | None
    include_food: bool
    duration: int
    pace: str
    requested_concepts: tuple[str, ...]
    hard_concepts: tuple[str, ...]


def catalog_query_from_preview(preview: QueryPreview) -> CatalogQuery:
    requested: dict[str, str] = {}
    for concept in preview.interests:
        priority = preview.interestPriorities.get(concept, "MEDIUM")
        for tag in CONCEPT_TAGS.get(concept, frozenset()):
            old = requested.get(tag)
            if old is None or PRIORITY_WEIGHTS[priority] > PRIORITY_WEIGHTS[old]:
                requested[tag] = priority

    required: set[str] = set()
    if preview.withChildren:
        required.add("FAMILY")
    if preview.unusualPlaces:
        required.add("UNUSUAL")

    excluded: set[str] = set()
    for concept in preview.hardExclusions:
        excluded.update(CONCEPT_TAGS.get(concept, frozenset()))

    return CatalogQuery(
        requested_tags=requested,
        required_tags=frozenset(required),
        excluded_concepts=frozenset(preview.hardExclusions),
        excluded_tags=frozenset(excluded),
        excluded_types=frozenset(preview.excludedPlaceTypes),
        with_children=preview.withChildren,
        unusual_places=preview.unusualPlaces,
        free_only=preview.freeOnly,
        max_budget=preview.maxBudgetRub,
        include_food=preview.includeFood,
        duration=preview.targetDurationMinutes or preview.durationMinutes,
        pace=preview.routePace,
        requested_concepts=tuple(preview.interests),
        # Positive intent is deliberately soft: a route may cover only part of it.
        hard_concepts=(),
    )


def type_matches_concept(place_type: str, concept: str) -> bool:
    normalized = place_type.casefold()
    if concept == "MUSEUMS":
        return normalized in MUSEUM_LIKE_TYPES or "museum" in normalized or "gallery" in normalized
    if concept == "PARKS":
        return any(value in normalized for value in ("park", "garden", "boulevard"))
    if concept == "SHOPPING":
        return "shopping" in normalized or "market" in normalized
    return False

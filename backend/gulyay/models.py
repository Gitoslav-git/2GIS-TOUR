from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class City(StrictModel):
    cityId: str
    name: str


class StartLocation(StrictModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    accuracyMeters: float = Field(ge=0)


class Filters(StrictModel):
    durationMinutes: int | None = Field(default=None, ge=30, le=720)
    withChildren: bool | None = None
    includeFood: bool | None = None
    unusualPlaces: bool | None = None


class CreateRoute(StrictModel):
    cityId: str
    query: str = Field(min_length=3, max_length=1000)
    filters: Filters = Field(default_factory=Filters)
    startLocation: StartLocation | None = None
    deviceSessionId: UUID | None = None

    @field_validator("query")
    @classmethod
    def nonempty_query(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 3:
            raise ValueError("Введите не менее трёх символов")
        return stripped


InterestConcept = Literal[
    "ARCHITECTURE", "HISTORIC_PLACES", "LANDMARKS", "MUSEUMS", "PARKS",
    "VIEWPOINTS", "RELIGIOUS_PLACES", "STREET_ART", "UNUSUAL_PLACES",
    "CHILD_FRIENDLY", "CULTURE", "NATURE", "SHOPPING", "ENTERTAINMENT",
]


class DurationIntent(StrictModel):
    mode: Literal["TARGET", "MAXIMUM", "APPROXIMATE", "DEFAULT"]
    targetMinutes: int | None = Field(ge=30, le=720)
    maxMinutes: int | None = Field(ge=30, le=720)
    minMinutes: int | None = Field(ge=30, le=720)


class StartIntent(StrictModel):
    explicitLocationText: str | None = Field(max_length=160)
    isExplicit: bool
    isAmbiguous: bool


class AreaIntent(StrictModel):
    preference: Literal[
        "ANY", "CENTER", "NORTH", "SOUTH", "EAST", "WEST", "DISTRICT",
        "NEAR_LOCATION",
    ]
    locationText: str | None = Field(max_length=120)
    strength: Literal["SOFT", "HARD"]


class MobilityIntent(StrictModel):
    transportMode: Literal["WALKING", "DRIVING"]
    walkingEffort: Literal["VERY_LOW", "LOW", "NORMAL", "HIGH", "NOT_SPECIFIED"]
    compactness: Literal["LOW", "NORMAL", "HIGH"]
    minimizeTotalWalking: bool
    preferredLegMinutes: int | None = Field(ge=1, le=120)
    maxLegMinutes: int | None = Field(ge=1, le=120)
    maxLegDistanceMeters: int | None = Field(ge=50, le=20000)
    maxTotalWalkingMinutes: int | None = Field(ge=1, le=720)
    maxTotalWalkingDistanceMeters: int | None = Field(ge=100, le=50000)


class InterestIntent(StrictModel):
    concept: InterestConcept
    priority: Literal["LOW", "MEDIUM", "HIGH"]
    strength: Literal["SOFT", "HARD"]
    sourceText: str = Field(min_length=1, max_length=120)
    broadeningAllowed: bool


class ExclusionIntent(StrictModel):
    concept: InterestConcept
    strength: Literal["SOFT_NEGATIVE", "HARD_EXCLUSION"]


FoodPreference = Literal[
    "COFFEE", "BREAKFAST", "LUNCH", "DINNER", "DESSERT", "VEGETARIAN",
    "LOCAL_CUISINE", "FAMILY", "FAST_FOOD",
]


class FoodIntent(StrictModel):
    mode: Literal["NONE", "OPTIONAL", "REQUIRED"]
    timing: Literal["ANY", "START", "MIDDLE", "END", "EXACT_TIME"]
    exactTime: str | None = Field(max_length=5, pattern=r"^\d{2}:\d{2}$")
    preferences: list[FoodPreference] = Field(max_length=6)
    excludedPreferences: list[FoodPreference] = Field(max_length=6)


class RouteStyleIntent(StrictModel):
    pace: Literal["RELAXED", "NORMAL", "INTENSIVE"]
    placeDensity: Literal["LOW", "NORMAL", "HIGH"]
    variety: Literal["LOW", "NORMAL", "HIGH"]
    popularityPreference: Literal[
        "POPULAR", "BALANCED", "NON_TOURISTIC", "NOT_SPECIFIED",
    ]


class IntentExtraction(StrictModel):
    """Strict LLM output: intent only, never provider facts or API parameters."""

    schemaVersion: Literal["1.0"]
    cityText: str | None = Field(max_length=100)
    duration: DurationIntent
    start: StartIntent
    area: AreaIntent
    directionHint: str | None = Field(max_length=120)
    mobility: MobilityIntent
    interests: list[InterestIntent] = Field(max_length=8)
    exclusions: list[ExclusionIntent] = Field(max_length=8)
    food: FoodIntent
    routeStyle: RouteStyleIntent
    withChildren: bool
    unusualPlaces: bool
    clarificationFields: list[Literal[
        "cityId", "durationMinutes", "startLocationHint", "area",
    ]] = Field(max_length=4)


class QueryPreview(StrictModel):
    cityId: str
    durationMinutes: int
    durationSource: Literal["text", "filter", "default"]
    durationMode: Literal["TARGET", "MAXIMUM", "APPROXIMATE", "DEFAULT"] = "TARGET"
    targetDurationMinutes: int | None = Field(default=None, ge=30, le=720)
    maxDurationMinutes: int | None = Field(default=None, ge=30, le=720)
    minDurationMinutes: int | None = Field(default=None, ge=30, le=720)
    interests: list[str]
    interestPriorities: dict[str, Literal["LOW", "MEDIUM", "HIGH"]] = Field(
        default_factory=dict,
    )
    hardExclusions: list[str] = Field(default_factory=list)
    softExclusions: list[str] = Field(default_factory=list)
    includeFood: bool
    foodMode: Literal["NONE", "OPTIONAL", "REQUIRED"] = "NONE"
    foodTiming: Literal["ANY", "START", "MIDDLE", "END", "EXACT_TIME"] = "ANY"
    foodPreferences: list[str] = Field(default_factory=list)
    excludedFoodPreferences: list[str] = Field(default_factory=list)
    withChildren: bool
    unusualPlaces: bool
    centerOnly: bool
    areaStrength: Literal["SOFT", "HARD"] = "SOFT"
    locationHint: str | None = Field(default=None, max_length=120)
    startLocationHint: str | None = Field(default=None, max_length=160)
    directionHint: str | None = Field(default=None, max_length=120)
    preferShortWalks: bool = False
    walkingEffort: Literal[
        "VERY_LOW", "LOW", "NORMAL", "HIGH", "NOT_SPECIFIED",
    ] = "NOT_SPECIFIED"
    compactness: Literal["LOW", "NORMAL", "HIGH"] = "NORMAL"
    minimizeTotalWalking: bool = False
    preferredWalkingMinutes: int | None = Field(default=None, ge=1, le=120)
    maxWalkingMinutes: int | None = Field(default=None, ge=1, le=120)
    maxWalkingDistanceMeters: int | None = Field(default=None, ge=50, le=20000)
    maxTotalWalkingMinutes: int | None = Field(default=None, ge=1, le=720)
    maxTotalWalkingDistanceMeters: int | None = Field(default=None, ge=100, le=50000)
    routePace: Literal["RELAXED", "NORMAL", "INTENSIVE"] = "NORMAL"
    placeDensity: Literal["LOW", "NORMAL", "HIGH"] = "NORMAL"
    variety: Literal["LOW", "NORMAL", "HIGH"] = "NORMAL"
    popularityPreference: Literal[
        "POPULAR", "BALANCED", "NON_TOURISTIC", "NOT_SPECIFIED",
    ] = "NOT_SPECIFIED"
    warnings: list[str]


class SearchArea(StrictModel):
    label: str
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    radiusMeters: int = Field(ge=500, le=20000)
    source: Literal["city", "direction", "2gis"]


class PlaceCandidate(StrictModel):
    placeId: str
    name: str
    lat: float
    lon: float
    rubrics: list[str]
    schedule: dict
    isFood: bool


class PlaceSummary(StrictModel):
    placeId: str
    name: str
    lat: float
    lon: float
    isFood: bool


class RoutePoint(StrictModel):
    order: int
    placeId: str
    name: str
    lat: float
    lon: float
    visitMinutes: int
    scheduleStatus: Literal["OPEN", "CLOSED", "UNKNOWN"]
    isFood: bool


class RouteLeg(StrictModel):
    fromOrder: int
    toOrder: int
    distanceMeters: int
    durationSeconds: int
    geometry: list[tuple[float, float]]

    @field_validator("geometry")
    @classmethod
    def bound_geometry_for_mobile_map(
            cls, points: list[tuple[float, float]]) -> list[tuple[float, float]]:
        """Also compacts routes restored from databases created by older releases."""
        max_points = 120
        if len(points) <= max_points:
            return points
        last_index = len(points) - 1
        sampled: list[tuple[float, float]] = []
        for position in range(max_points):
            point = points[round(position * last_index / (max_points - 1))]
            if not sampled or sampled[-1] != point:
                sampled.append(point)
        return sampled


class Route(StrictModel):
    routeId: UUID
    routeVersion: int
    status: Literal["READY", "ACTIVE", "COMPLETED", "STOPPED"]
    cityId: str
    query: str
    filters: Filters
    searchArea: SearchArea
    approximateStart: bool
    startLat: float | None = Field(default=None, ge=-90, le=90)
    startLon: float | None = Field(default=None, ge=-180, le=180)
    startSource: Literal["USER_GEO", "TEXT_ANCHOR", "CITY_CENTER", "LEGACY"] = "LEGACY"
    maxWalkingMinutes: int | None = Field(default=None, ge=1, le=120)
    planningStatus: Literal["SUCCESS", "DEGRADED"] = "SUCCESS"
    durationUtilization: float = Field(default=1.0, ge=0)
    unmetPreferences: list[str] = Field(default_factory=list)
    requestedMinutes: int
    totalMinutes: int
    unusedMinutes: int
    points: list[RoutePoint]
    legs: list[RouteLeg]
    warnings: list[str]


class RouteRevision(StrictModel):
    baseVersion: int = Field(ge=1)
    mode: Literal["CHANGE_QUERY", "EDIT_POINTS"]
    query: str | None = Field(default=None, min_length=3, max_length=1000)
    filters: Filters | None = None
    pointIds: list[str] | None = Field(default=None, min_length=1, max_length=8)

    @field_validator("query")
    @classmethod
    def nonempty_revision_query(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if len(stripped) < 3:
            raise ValueError("Введите не менее трёх символов")
        return stripped

    @field_validator("pointIds")
    @classmethod
    def unique_point_ids(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        cleaned = [value.strip() for value in values]
        if any(not value or len(value) > 200 or "," in value for value in cleaned):
            raise ValueError("Некорректный идентификатор точки")
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("Точки маршрута не должны повторяться")
        return cleaned


class StartWalk(StrictModel):
    routeVersion: int = Field(ge=1)


class WalkPosition(StrictModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    accuracyMeters: float = Field(ge=0)
    measuredAt: datetime

    @field_validator("measuredAt")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("measuredAt must include timezone")
        return value


class WalkAction(StrictModel):
    action: Literal["PAUSE", "RESUME", "STOP"]


class Visit(StrictModel):
    pointOrder: int = Field(ge=1, le=8)
    reachedAt: datetime


class WalkSession(StrictModel):
    walkId: UUID
    routeId: UUID
    routeVersion: int = Field(ge=1)
    status: Literal["ACTIVE", "PAUSED", "COMPLETED", "STOPPED"]
    currentPointOrder: int | None = Field(default=None, ge=1, le=8)
    startedAt: datetime
    endedAt: datetime | None = None
    estimatedRemainingMinutes: int = Field(ge=0)
    visits: list[Visit] = Field(default_factory=list)


class WalkProgress(StrictModel):
    walk: WalkSession
    pointReached: bool
    distanceMeters: int | None = Field(default=None, ge=0)


class WalkState(StrictModel):
    session: WalkSession
    lastMeasuredAt: datetime | None = None
    proximityStartedAt: datetime | None = None
    proximityPointOrder: int | None = Field(default=None, ge=1, le=8)
    pausedAt: datetime | None = None
    pausedSeconds: int = Field(default=0, ge=0)

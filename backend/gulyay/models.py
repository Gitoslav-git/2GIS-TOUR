from __future__ import annotations

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


class IntentExtraction(StrictModel):
    """LLM output. Only preferences: the model cannot supply provider place IDs or coordinates."""

    cityText: str | None
    durationMinutes: int | None
    interests: list[str] = Field(max_length=12)
    includeFood: bool | None
    withChildren: bool | None
    unusualPlaces: bool | None
    centerOnly: bool | None
    locationHint: str | None = Field(max_length=120)
    startLocationHint: str | None = Field(max_length=160)
    directionHint: str | None = Field(max_length=120)
    startLocationAmbiguous: bool
    preferShortWalks: bool | None

    @field_validator("interests")
    @classmethod
    def valid_interests(cls, values: list[str]) -> list[str]:
        if any(not item.strip() or len(item) > 80 for item in values):
            raise ValueError("Invalid interest")
        return values


class QueryPreview(StrictModel):
    cityId: str
    durationMinutes: int
    durationSource: Literal["text", "filter", "default"]
    interests: list[str]
    includeFood: bool
    withChildren: bool
    unusualPlaces: bool
    centerOnly: bool
    locationHint: str | None = Field(default=None, max_length=120)
    startLocationHint: str | None = Field(default=None, max_length=160)
    directionHint: str | None = Field(default=None, max_length=120)
    preferShortWalks: bool = False
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

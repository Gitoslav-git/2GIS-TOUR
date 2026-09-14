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
    approximateStart: bool
    totalMinutes: int
    points: list[RoutePoint]
    legs: list[RouteLeg]
    warnings: list[str]

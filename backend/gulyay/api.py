from __future__ import annotations

import json
import os
import threading
import time
from uuid import UUID

from fastapi import Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .geo import (DgisGeoProvider, GeoAuthenticationError, GeoConstraintNotFound,
                  GeoInvalidResponse, GeoRateLimited, GeoUnavailable)
from .intent import (IntentAuthenticationError, IntentInvalidResponse,
                     IntentNeedsClarification, IntentUnavailable,
                     OpenAIIntentProvider, interpret)
from .models import City, CreateRoute, QueryPreview, Route, RouteRevision
from .route_builder import RouteNotFound, TimeBudgetExceeded, build_route

app = FastAPI(title="Гуляй API", version="0.4.0")
CITIES = (City(cityId="tula", name="Тула"), City(cityId="vladimir", name="Владимир"))
ROUTES: dict[UUID, Route] = {}
ROUTE_OWNERS: dict[UUID, UUID] = {}
ROUTE_INPUTS: dict[UUID, CreateRoute] = {}
IDEMPOTENT_ROUTES: dict[tuple[UUID, UUID], Route] = {}
IDEMPOTENT_REVISIONS: dict[tuple[UUID, UUID], Route] = {}
RECENT_ROUTES: dict[tuple[UUID, str], tuple[float, Route]] = {}
STATE_LOCK = threading.RLock()


def failure(code: str, message: str, status: int, request_id: str | None = None,
            details: dict | None = None, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {
        "code": code, "message": message, "details": details or {}, "requestId": request_id,
    }}, headers=headers)


def get_intent_provider() -> OpenAIIntentProvider:
    return OpenAIIntentProvider()


def get_geo_provider() -> DgisGeoProvider:
    return DgisGeoProvider()


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    return failure("VALIDATION_ERROR", "Проверьте заполненные поля", 400,
                   request.headers.get("X-Request-Id"))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.4.0"}


@app.get("/v1/cities", response_model=dict[str, list[City]])
def cities() -> dict[str, list[City]]:
    return {"cities": list(CITIES)}


@app.post("/v1/routes/interpret", response_model=QueryPreview)
def preview_route(payload: CreateRoute,
                  x_device_session: UUID | None = Header(default=None),
                  x_request_id: UUID | None = Header(default=None),
                  provider: OpenAIIntentProvider = Depends(get_intent_provider)) -> QueryPreview | JSONResponse:
    request_id = str(x_request_id) if x_request_id else None
    authorization = _authorize_create(payload, x_device_session, request_id)
    if authorization:
        return authorization
    try:
        return interpret(payload, provider)
    except IntentNeedsClarification as exc:
        return failure("QUERY_NEEDS_CLARIFICATION", "Уточните запрос и выбранный город или длительность", 422,
                       request_id, {"fields": exc.fields})
    except IntentAuthenticationError:
        return failure("LLM_AUTH_ERROR", "Ключ LLM не принят сервером", 503, request_id)
    except IntentUnavailable:
        return failure("LLM_UNAVAILABLE", "Разбор запроса пока недоступен", 503, request_id)
    except IntentInvalidResponse:
        return failure("LLM_INVALID_RESPONSE", "Не удалось понять пожелания. Попробуйте ещё раз", 502, request_id)


@app.post("/v1/routes", response_model=Route)
def create_route(payload: CreateRoute, x_device_session: UUID | None = Header(default=None),
                 x_request_id: UUID | None = Header(default=None),
                 intent_provider: OpenAIIntentProvider = Depends(get_intent_provider),
                 geo: DgisGeoProvider = Depends(get_geo_provider)) -> Route | JSONResponse:
    request_id = str(x_request_id) if x_request_id else None
    authorization = _authorize_create(payload, x_device_session, request_id)
    if authorization:
        return authorization
    assert x_device_session is not None
    cache_key = (x_device_session, x_request_id) if x_request_id else None
    recent_key = (x_device_session, _payload_fingerprint(payload))
    with STATE_LOCK:
        if cache_key and cache_key in IDEMPOTENT_ROUTES:
            return IDEMPOTENT_ROUTES[cache_key]
        recent = RECENT_ROUTES.get(recent_key)
        if recent and recent[0] > time.monotonic():
            return recent[1]
        if recent:
            RECENT_ROUTES.pop(recent_key, None)
    route_or_error = _build(payload, intent_provider, geo, request_id)
    if isinstance(route_or_error, JSONResponse):
        return route_or_error
    route = route_or_error
    with STATE_LOCK:
        ROUTES[route.routeId] = route
        ROUTE_OWNERS[route.routeId] = x_device_session
        ROUTE_INPUTS[route.routeId] = payload
        RECENT_ROUTES[recent_key] = (time.monotonic() + _recent_route_ttl(), route)
        if cache_key:
            IDEMPOTENT_ROUTES[cache_key] = route
    return route


@app.get("/v1/routes/{route_id}", response_model=Route)
def get_route(route_id: UUID, x_device_session: UUID | None = Header(default=None),
              x_request_id: UUID | None = Header(default=None)) -> Route | JSONResponse:
    request_id = str(x_request_id) if x_request_id else None
    with STATE_LOCK:
        route = ROUTES.get(route_id)
        owner = ROUTE_OWNERS.get(route_id)
    if route is None or x_device_session is None or owner != x_device_session:
        return failure("NOT_FOUND", "Маршрут не найден", 404, request_id)
    return route


@app.post("/v1/routes/{route_id}/revisions", response_model=Route)
def revise_route(route_id: UUID, revision: RouteRevision,
                 x_device_session: UUID | None = Header(default=None),
                 x_request_id: UUID | None = Header(default=None),
                 intent_provider: OpenAIIntentProvider = Depends(get_intent_provider),
                 geo: DgisGeoProvider = Depends(get_geo_provider)) -> Route | JSONResponse:
    request_id = str(x_request_id) if x_request_id else None
    if x_device_session is None:
        return failure("NOT_FOUND", "Маршрут не найден", 404, request_id)
    idempotency_key = (x_device_session, x_request_id) if x_request_id else None
    with STATE_LOCK:
        if idempotency_key and idempotency_key in IDEMPOTENT_REVISIONS:
            return IDEMPOTENT_REVISIONS[idempotency_key]
        current = ROUTES.get(route_id)
        owner = ROUTE_OWNERS.get(route_id)
        source = ROUTE_INPUTS.get(route_id)
        if current is None or owner != x_device_session or source is None:
            return failure("NOT_FOUND", "Маршрут не найден", 404, request_id)
        if revision.baseVersion != current.routeVersion:
            return failure("VERSION_CONFLICT", "Маршрут уже изменён", 409, request_id,
                           {"currentVersion": current.routeVersion})
    if revision.query is None:
        return failure("VALIDATION_ERROR", "Для изменения маршрута нужен новый текст", 400, request_id,
                       {"fields": ["query"]})
    payload = CreateRoute(
        cityId=source.cityId, query=revision.query,
        filters=revision.filters if revision.filters is not None else source.filters,
        startLocation=source.startLocation, deviceSessionId=x_device_session,
    )
    route_or_error = _build(payload, intent_provider, geo, request_id)
    if isinstance(route_or_error, JSONResponse):
        return route_or_error
    replacement = route_or_error.model_copy(update={
        "routeId": route_id, "routeVersion": revision.baseVersion + 1,
    })
    with STATE_LOCK:
        latest = ROUTES.get(route_id)
        if latest is None or latest.routeVersion != revision.baseVersion:
            current_version = latest.routeVersion if latest else revision.baseVersion
            return failure("VERSION_CONFLICT", "Маршрут уже изменён", 409, request_id,
                           {"currentVersion": current_version})
        ROUTES[route_id] = replacement
        ROUTE_INPUTS[route_id] = payload
        if idempotency_key:
            IDEMPOTENT_REVISIONS[idempotency_key] = replacement
    return replacement


def _authorize_create(payload: CreateRoute, session: UUID | None,
                      request_id: str | None) -> JSONResponse | None:
    if payload.cityId not in {city.cityId for city in CITIES}:
        return failure("VALIDATION_ERROR", "Выберите доступный город", 400, request_id)
    if payload.deviceSessionId is None or session != payload.deviceSessionId:
        return failure("UNAUTHORIZED", "Укажите гостевую сессию", 401, request_id)
    return None


def _build(payload: CreateRoute, intent_provider: OpenAIIntentProvider,
           geo: DgisGeoProvider, request_id: str | None) -> Route | JSONResponse:
    try:
        geo.ensure_configured()
        preview = interpret(payload, intent_provider)
        return build_route(payload, preview, geo)
    except IntentNeedsClarification as exc:
        return failure("QUERY_NEEDS_CLARIFICATION", "Уточните выбранный город или длительность", 422,
                       request_id, {"fields": exc.fields})
    except IntentAuthenticationError:
        return failure("LLM_AUTH_ERROR", "Ключ LLM не принят сервером", 503, request_id)
    except IntentUnavailable:
        return failure("LLM_UNAVAILABLE", "Разбор запроса пока недоступен", 503, request_id)
    except IntentInvalidResponse:
        return failure("LLM_INVALID_RESPONSE", "Не удалось понять пожелания. Попробуйте ещё раз", 502, request_id)
    except GeoAuthenticationError:
        return failure("GEO_UNAVAILABLE", "Ключ 2ГИС не принят сервером", 503, request_id,
                       {"reason": "authentication"})
    except GeoRateLimited as exc:
        seconds = exc.retry_after_seconds
        return failure("RATE_LIMITED", f"Лимит запросов 2ГИС. Повторите через {seconds} сек.", 429,
                       request_id, {"retryAfterSeconds": seconds, "dependency": "2gis"},
                       {"Retry-After": str(seconds)})
    except GeoConstraintNotFound:
        return failure("GEO_CONSTRAINT_NOT_FOUND", "Не удалось найти указанную часть города в 2ГИС", 422,
                       request_id, {"fields": ["locationHint"]})
    except (GeoInvalidResponse, GeoUnavailable):
        return failure("GEO_UNAVAILABLE", "Сервис мест или пеших маршрутов 2ГИС недоступен", 503, request_id)
    except TimeBudgetExceeded as exc:
        details = {"minimumMinutes": exc.minimum_minutes} if exc.minimum_minutes else {}
        return failure("TIME_BUDGET_EXCEEDED", "Точки не помещаются в выбранное время", 422,
                       request_id, details)
    except RouteNotFound:
        return failure("ROUTE_NOT_FOUND", "Не найден маршрут по подходящим открытым местам", 422, request_id)


def _payload_fingerprint(payload: CreateRoute) -> str:
    return json.dumps(payload.model_dump(mode="json", exclude={"deviceSessionId"}),
                      ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _recent_route_ttl() -> int:
    try:
        value = int(os.getenv("ROUTE_RESULT_CACHE_SECONDS", "600"))
    except ValueError:
        return 600
    return max(60, min(3600, value))

from __future__ import annotations

import json
import os
import threading
import time
from collections import defaultdict, deque
from uuid import UUID

from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .geo import (DgisGeoProvider, GeoAuthenticationError, GeoConstraintNotFound,
                  GeoInvalidResponse, GeoPlaceNotFound, GeoRateLimited,
                  GeoUnavailable)
from .intent import (IntentAuthenticationError, IntentInvalidResponse,
                     IntentNeedsClarification, IntentUnavailable,
                     OpenAIIntentProvider, interpret)
from .models import (City, CreateRoute, PlaceSummary, QueryPreview, Route,
                     RouteRevision)
from .repository import RouteRepository
from .route_builder import (RouteNotFound, TimeBudgetExceeded, build_route,
                            rebuild_route_with_points)

app = FastAPI(title="Гуляй API", version="0.5.1")
CITIES = (City(cityId="tula", name="Тула"), City(cityId="vladimir", name="Владимир"),
          City(cityId="moscow", name="Москва"))
ROUTE_REPOSITORY = RouteRepository()
IDEMPOTENT_ROUTES: dict[tuple[UUID, UUID], Route] = {}
IDEMPOTENT_REVISIONS: dict[tuple[UUID, UUID], Route] = {}
RECENT_ROUTES: dict[tuple[UUID, str], tuple[float, Route]] = {}
STATE_LOCK = threading.RLock()
CLIENT_REQUESTS: dict[UUID, deque[float]] = defaultdict(deque)


def failure(code: str, message: str, status: int, request_id: str | None = None,
            details: dict | None = None, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {
        "code": code, "message": message, "details": details or {}, "requestId": request_id,
    }}, headers=headers)


def get_intent_provider() -> OpenAIIntentProvider:
    return OpenAIIntentProvider()


def get_geo_provider() -> DgisGeoProvider:
    return DgisGeoProvider()


def get_route_repository() -> RouteRepository:
    return ROUTE_REPOSITORY


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    return failure("VALIDATION_ERROR", "Проверьте заполненные поля", 400,
                   request.headers.get("X-Request-Id"))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.5.1"}


@app.get("/v1/cities", response_model=dict[str, list[City]])
def cities() -> dict[str, list[City]]:
    return {"cities": list(CITIES)}


@app.get("/v1/places", response_model=dict[str, list[PlaceSummary]])
def places(cityId: str, q: str = Query(min_length=2, max_length=120),
           x_device_session: UUID | None = Header(default=None),
           x_request_id: UUID | None = Header(default=None),
           geo: DgisGeoProvider = Depends(get_geo_provider)) -> dict | JSONResponse:
    request_id = str(x_request_id) if x_request_id else None
    if x_device_session is None:
        return failure("UNAUTHORIZED", "Укажите гостевую сессию", 401, request_id)
    if cityId not in {city.cityId for city in CITIES} or len(q.strip()) < 2:
        return failure("VALIDATION_ERROR", "Проверьте город и строку поиска", 400, request_id)
    limited = _client_rate_limit(x_device_session, request_id)
    if limited:
        return limited
    try:
        candidates = geo.search_candidates(cityId, q.strip())
        return {"items": [PlaceSummary(
            placeId=item.placeId, name=item.name, lat=item.lat, lon=item.lon,
            isFood=item.isFood,
        ) for item in candidates]}
    except GeoAuthenticationError:
        return failure("GEO_UNAVAILABLE", "Ключ 2ГИС не принят сервером", 503, request_id,
                       {"reason": "authentication"})
    except GeoRateLimited as exc:
        return failure("RATE_LIMITED", f"Лимит запросов 2ГИС. Повторите через {exc.retry_after_seconds} сек.",
                       429, request_id, {"retryAfterSeconds": exc.retry_after_seconds,
                                         "dependency": "2gis"},
                       {"Retry-After": str(exc.retry_after_seconds)})
    except (GeoInvalidResponse, GeoUnavailable):
        return failure("GEO_UNAVAILABLE", "Поиск мест 2ГИС недоступен", 503, request_id)


@app.post("/v1/routes/interpret", response_model=QueryPreview)
def preview_route(payload: CreateRoute,
                  x_device_session: UUID | None = Header(default=None),
                  x_request_id: UUID | None = Header(default=None),
                  provider: OpenAIIntentProvider = Depends(get_intent_provider)) -> QueryPreview | JSONResponse:
    request_id = str(x_request_id) if x_request_id else None
    authorization = _authorize_create(payload, x_device_session, request_id)
    if authorization:
        return authorization
    limited = _client_rate_limit(x_device_session, request_id)
    if limited:
        return limited
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
                 geo: DgisGeoProvider = Depends(get_geo_provider),
                 repository: RouteRepository = Depends(get_route_repository)) -> Route | JSONResponse:
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
    limited = _client_rate_limit(x_device_session, request_id)
    if limited:
        return limited
    route_or_error = _build(payload, intent_provider, geo, request_id)
    if isinstance(route_or_error, JSONResponse):
        return route_or_error
    route = route_or_error
    repository.save_new(route, x_device_session, payload)
    with STATE_LOCK:
        RECENT_ROUTES[recent_key] = (time.monotonic() + _recent_route_ttl(), route)
        if cache_key:
            IDEMPOTENT_ROUTES[cache_key] = route
    return route


@app.get("/v1/routes/{route_id}", response_model=Route)
def get_route(route_id: UUID, x_device_session: UUID | None = Header(default=None),
              x_request_id: UUID | None = Header(default=None),
              repository: RouteRepository = Depends(get_route_repository)) -> Route | JSONResponse:
    request_id = str(x_request_id) if x_request_id else None
    if x_device_session is None:
        return failure("NOT_FOUND", "Маршрут не найден", 404, request_id)
    state = repository.get(route_id, x_device_session)
    if state is None:
        return failure("NOT_FOUND", "Маршрут не найден", 404, request_id)
    return state[0]


@app.post("/v1/routes/{route_id}/revisions", response_model=Route)
def revise_route(route_id: UUID, revision: RouteRevision,
                 x_device_session: UUID | None = Header(default=None),
                 x_request_id: UUID | None = Header(default=None),
                 intent_provider: OpenAIIntentProvider = Depends(get_intent_provider),
                 geo: DgisGeoProvider = Depends(get_geo_provider),
                 repository: RouteRepository = Depends(get_route_repository)) -> Route | JSONResponse:
    request_id = str(x_request_id) if x_request_id else None
    if x_device_session is None:
        return failure("NOT_FOUND", "Маршрут не найден", 404, request_id)
    idempotency_key = (x_device_session, x_request_id) if x_request_id else None
    with STATE_LOCK:
        if idempotency_key and idempotency_key in IDEMPOTENT_REVISIONS:
            return IDEMPOTENT_REVISIONS[idempotency_key]
    limited = _client_rate_limit(x_device_session, request_id)
    if limited:
        return limited
    state = repository.get(route_id, x_device_session)
    if state is None:
        return failure("NOT_FOUND", "Маршрут не найден", 404, request_id)
    current, source = state
    if revision.baseVersion != current.routeVersion:
        return failure("VERSION_CONFLICT", "Маршрут уже изменён", 409, request_id,
                       {"currentVersion": current.routeVersion})
    if revision.mode == "CHANGE_QUERY":
        if revision.query is None or revision.pointIds is not None:
            return failure("VALIDATION_ERROR", "Для изменения маршрута нужен новый текст", 400,
                           request_id, {"fields": ["query"]})
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
    else:
        if revision.pointIds is None or revision.query is not None or revision.filters is not None:
            return failure("VALIDATION_ERROR", "Передайте итоговый порядок точек", 400,
                           request_id, {"fields": ["pointIds"]})
        payload = source
        try:
            candidates = geo.resolve_places(current.cityId, revision.pointIds)
            replacement = rebuild_route_with_points(current, source, candidates, geo).model_copy(
                update={"routeVersion": revision.baseVersion + 1}
            )
        except GeoPlaceNotFound:
            return failure("ROUTE_NOT_FOUND", "Одна из точек не найдена в выбранном городе", 422,
                           request_id)
        except GeoAuthenticationError:
            return failure("GEO_UNAVAILABLE", "Ключ 2ГИС не принят сервером", 503, request_id,
                           {"reason": "authentication"})
        except GeoRateLimited as exc:
            return failure("RATE_LIMITED",
                           f"Лимит запросов 2ГИС. Повторите через {exc.retry_after_seconds} сек.",
                           429, request_id, {"retryAfterSeconds": exc.retry_after_seconds,
                                             "dependency": "2gis"},
                           {"Retry-After": str(exc.retry_after_seconds)})
        except (GeoInvalidResponse, GeoUnavailable):
            return failure("GEO_UNAVAILABLE", "Сервис мест или пеших маршрутов 2ГИС недоступен",
                           503, request_id)
        except TimeBudgetExceeded as exc:
            details = {"minimumMinutes": exc.minimum_minutes} if exc.minimum_minutes else {}
            return failure("TIME_BUDGET_EXCEEDED", "Точки не помещаются в выбранное время", 422,
                           request_id, details)
        except RouteNotFound:
            return failure("ROUTE_NOT_FOUND", "Нельзя построить маршрут в выбранном порядке", 422,
                           request_id)
    if not repository.replace(replacement, x_device_session, payload, revision.baseVersion):
        latest = repository.get(route_id, x_device_session)
        current_version = latest[0].routeVersion if latest else revision.baseVersion
        return failure("VERSION_CONFLICT", "Маршрут уже изменён", 409, request_id,
                       {"currentVersion": current_version})
    with STATE_LOCK:
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


def _client_rate_limit(session: UUID | None, request_id: str | None) -> JSONResponse | None:
    """Allow five expensive client operations per rolling minute and device session."""
    if session is None:
        return None
    now = time.monotonic()
    with STATE_LOCK:
        window = CLIENT_REQUESTS[session]
        while window and window[0] <= now - 60:
            window.popleft()
        if len(window) >= 5:
            retry_after = max(1, int(61 - (now - window[0])))
            return failure(
                "RATE_LIMITED", f"Не больше 5 запросов в минуту. Повторите через {retry_after} сек.",
                429, request_id,
                {"retryAfterSeconds": retry_after, "dependency": "client"},
                {"Retry-After": str(retry_after)},
            )
        window.append(now)
    return None

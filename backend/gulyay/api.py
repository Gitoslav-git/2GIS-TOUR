from __future__ import annotations

from uuid import UUID

from fastapi import Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .geo import (DgisGeoProvider, GeoAuthenticationError, GeoInvalidResponse,
                  GeoUnavailable)
from .intent import (IntentAuthenticationError, IntentInvalidResponse,
                     IntentNeedsClarification, IntentUnavailable,
                     OpenAIIntentProvider, interpret)
from .models import City, CreateRoute, QueryPreview, Route
from .route_builder import RouteNotFound, TimeBudgetExceeded, build_route

app = FastAPI(title="Гуляй API", version="0.3.0")
CITIES = (City(cityId="tula", name="Тула"), City(cityId="vladimir", name="Владимир"))
ROUTES: dict[UUID, Route] = {}
IDEMPOTENT_ROUTES: dict[tuple[UUID, UUID], Route] = {}


def failure(code: str, message: str, status: int, request_id: str | None = None,
            details: dict | None = None) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {
        "code": code, "message": message, "details": details or {}, "requestId": request_id,
    }})


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
    return {"status": "ok", "version": "0.3.0"}


@app.get("/v1/cities", response_model=dict[str, list[City]])
def cities() -> dict[str, list[City]]:
    return {"cities": list(CITIES)}


@app.post("/v1/routes/interpret", response_model=QueryPreview)
def preview_route(payload: CreateRoute,
                  x_device_session: UUID | None = Header(default=None),
                  x_request_id: UUID | None = Header(default=None),
                  provider: OpenAIIntentProvider = Depends(get_intent_provider)) -> QueryPreview | JSONResponse:
    request_id = str(x_request_id) if x_request_id else None
    if payload.cityId not in {city.cityId for city in CITIES}:
        return failure("VALIDATION_ERROR", "Выберите доступный город", 400, request_id)
    if payload.deviceSessionId is None or x_device_session != payload.deviceSessionId:
        return failure("UNAUTHORIZED", "Укажите гостевую сессию", 401, request_id)
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
    if payload.cityId not in {city.cityId for city in CITIES}:
        return failure("VALIDATION_ERROR", "Выберите доступный город", 400, request_id)
    if payload.deviceSessionId is None or x_device_session != payload.deviceSessionId:
        return failure("UNAUTHORIZED", "Укажите гостевую сессию", 401, request_id)
    cache_key = (x_device_session, x_request_id) if x_request_id else None
    if cache_key and cache_key in IDEMPOTENT_ROUTES:
        return IDEMPOTENT_ROUTES[cache_key]
    try:
        # Check GEO before consuming a paid LLM call when the server is not configured.
        geo.ensure_configured()
        preview = interpret(payload, intent_provider)
        route = build_route(payload, preview, geo)
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
    except (GeoInvalidResponse, GeoUnavailable):
        return failure("GEO_UNAVAILABLE", "Сервис мест или пеших маршрутов 2ГИС недоступен", 503, request_id)
    except TimeBudgetExceeded as exc:
        details = {"minimumMinutes": exc.minimum_minutes} if exc.minimum_minutes else {}
        return failure("TIME_BUDGET_EXCEEDED", "Точки не помещаются в выбранное время", 422,
                       request_id, details)
    except RouteNotFound:
        return failure("ROUTE_NOT_FOUND", "Не найден маршрут по подходящим открытым местам", 422, request_id)
    ROUTES[route.routeId] = route
    if cache_key:
        IDEMPOTENT_ROUTES[cache_key] = route
    return route

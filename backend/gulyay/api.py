from __future__ import annotations

import json
import os
import hashlib
import math
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response

from .catalog import (CatalogPlaceProvider, PlaceCatalog, bundled_seed_paths)
from .geo import (DgisGeoProvider, GeoAuthenticationError, GeoConstraintNotFound,
                  GeoInvalidResponse, GeoPlaceNotFound, GeoRateLimited,
                  GeoUnavailable)
from .intent import (IntentAuthenticationError, IntentInvalidResponse,
                     IntentNeedsClarification, IntentUnavailable,
                     OpenAIIntentProvider, configured_model, interpret)
from .models import (City, CreateRoute, GuestHistoryItem, InsertSuggestedPlaceRequest,
                     InsertSuggestedPlaceResponse, PartnerOfferResponse, PlaceSummary,
                     QueryPreview, RecommendationDecision, RecommendationSelection,
                     Route, RouteRevision, StartWalk, WalkAction, WalkPosition,
                     WalkProgress, WalkSession, WalkState)
from .partners import (MAX_POSITION_ACCURACY_METERS, MAX_POSITION_AGE_SECONDS,
                       NAME_SEARCH_PILOT, PartnerOfferSelector, PartnerRegistry)
from .planning_debug import planning_log
from .repository import RouteRepository
from .route_builder import (DurationConfirmationRequired, RouteNotFound, TimeBudgetExceeded, build_route,
                            insert_suggested_place, rebuild_route_with_points)
from .walk import (WalkInvalidPosition, WalkInvalidState, apply_action,
                   register_position, session_at, start_walk)
from .version import __version__ as APP_VERSION

app = FastAPI(title="Гуляй API", version=APP_VERSION)
CITIES = (City(cityId="tula", name="Тула"), City(cityId="vladimir", name="Владимир"),
          City(cityId="moscow", name="Москва"),
          City(cityId="borovsk", name="Боровск, Калужская область"))
ROUTE_REPOSITORY = RouteRepository()
PLACE_CATALOG = PlaceCatalog()
for seed_path in bundled_seed_paths():
    PLACE_CATALOG.import_seed(seed_path)
CATALOG_PROVIDER = CatalogPlaceProvider(PLACE_CATALOG)
PARTNER_REGISTRY = PartnerRegistry()
IDEMPOTENT_ROUTES: dict[tuple[UUID, UUID], Route] = {}
IDEMPOTENT_REVISIONS: dict[tuple[UUID, UUID], Route] = {}
RECENT_ROUTES: dict[tuple[UUID, str], tuple[float, Route]] = {}
STATE_LOCK = threading.RLock()
CLIENT_REQUESTS: dict[UUID, deque[float]] = defaultdict(deque)
POSITION_REQUESTS: dict[UUID, deque[float]] = defaultdict(deque)
SOURCE_REQUESTS: dict[str, deque[float]] = defaultdict(deque)
PROVIDER_HEALTH_CACHE: dict[str, tuple[float, str]] = {}
PROVIDER_HEALTH_LOCK = threading.Lock()
SOURCE_RATE_SALT = os.getenv("SOURCE_RATE_SALT") or secrets.token_hex(16)
RECOMMENDATION_SELECTION_TTL_SECONDS = 10 * 60


def failure(code: str, message: str, status: int, request_id: str | None = None,
            details: dict | None = None, headers: dict[str, str] | None = None) -> JSONResponse:
    # Keep legacy call sites internally while exposing one stable 2GIS contract.
    if code == "GEO_UNAVAILABLE":
        if (details or {}).get("reason") == "authentication":
            code, message = "DGIS_AUTH_ERROR", "2GIS API authorization failed"
        else:
            code, message = "DGIS_UNAVAILABLE", "2GIS routing service is temporarily unavailable"
    elif code == "DGIS_RATE_LIMITED":
        code, message = "DGIS_RATE_LIMIT", "2GIS request limit reached"
    return JSONResponse(status_code=status, content={"error": {
        "code": code, "message": message, "details": details or {}, "requestId": request_id,
    }}, headers=headers)


def dgis_failure(exc: Exception, request_id: str | None = None) -> JSONResponse:
    """Stable public contract for real 2GIS-provider failures only."""
    if isinstance(exc, GeoAuthenticationError):
        return failure("DGIS_AUTH_ERROR", "2GIS API authorization failed", 503, request_id)
    if isinstance(exc, GeoRateLimited):
        seconds = exc.retry_after_seconds
        return failure("DGIS_RATE_LIMIT", "2GIS request limit reached", 503, request_id,
                       {"retryAfterSeconds": seconds, "dependency": "2gis"},
                       {"Retry-After": str(seconds)})
    return failure("DGIS_UNAVAILABLE", "2GIS routing service is temporarily unavailable",
                   503, request_id)


def get_intent_provider() -> OpenAIIntentProvider:
    return OpenAIIntentProvider()


def get_geo_provider() -> DgisGeoProvider:
    return DgisGeoProvider()


def get_route_repository() -> RouteRepository:
    return ROUTE_REPOSITORY


def get_catalog_provider() -> CatalogPlaceProvider:
    return CATALOG_PROVIDER


def get_partner_registry() -> PartnerRegistry:
    return PARTNER_REGISTRY


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    return failure("VALIDATION_ERROR", "Проверьте заполненные поля", 400,
                   request.headers.get("X-Request-Id"))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": app.version, "llmModel": configured_model()}


@app.get("/health/providers", response_model=None)
def provider_health(active: bool = False, x_health_token: str | None = Header(default=None),
                    geo: DgisGeoProvider = Depends(get_geo_provider),
                    intent_provider: OpenAIIntentProvider = Depends(get_intent_provider)) -> dict | JSONResponse:
    """Passive by default; active probes are token-gated and TTL-cached."""
    if active:
        token = os.getenv("HEALTH_PROBE_TOKEN", "")
        if not token or x_health_token != token:
            return failure("FORBIDDEN", "Active provider checks are not publicly available", 403)
        states = _active_provider_health(geo, intent_provider)
    else:
        states = {
            "llm": "not_checked" if os.getenv("OPENAI_API_KEY") else "not_configured",
            "dgis_places": "not_checked" if getattr(geo, "places_key", None) else "not_configured",
            "dgis_routing": "not_checked" if getattr(geo, "routing_key", None) else "not_configured",
        }
    return {"status": "ok", "active": active, "providers": states}


def _active_provider_health(geo: DgisGeoProvider, intent_provider: OpenAIIntentProvider) -> dict[str, str]:
    now = time.monotonic()
    with PROVIDER_HEALTH_LOCK:
        cached = {name: state for name, (until, state) in PROVIDER_HEALTH_CACHE.items()
                  if until > now}
        if len(cached) == 3:
            return cached
        checks = {
            "dgis_places": lambda: geo.resolve_city_center("tula"),
            "dgis_routing": lambda: geo.walking_leg((54.193, 37.617), (54.194, 37.618), 0, 1),
            "llm": lambda: intent_provider.extract("Короткая прогулка"),
        }
        states: dict[str, str] = {}
        for name, probe in checks.items():
            try:
                probe()
                state = "ok"
            except (GeoAuthenticationError, IntentAuthenticationError):
                state = "auth_error"
            except GeoRateLimited:
                state = "rate_limited"
            except (GeoInvalidResponse, IntentInvalidResponse):
                state = "invalid_response"
            except (GeoUnavailable, IntentUnavailable):
                state = "not_configured" if ((name == "llm" and not os.getenv("OPENAI_API_KEY"))
                                              or (name == "dgis_places" and not getattr(geo, "places_key", None))
                                              or (name == "dgis_routing" and not getattr(geo, "routing_key", None))) else "unavailable"
            PROVIDER_HEALTH_CACHE[name] = (now + 30, state)
            states[name] = state
        return states


@app.get("/v1/cities", response_model=dict[str, list[City]])
def cities() -> dict[str, list[City]]:
    return {"cities": list(CITIES)}


@app.get("/v1/places", response_model=dict[str, list[PlaceSummary]])
def places(request: Request, cityId: str, q: str = Query(min_length=2, max_length=120),
           x_device_session: UUID | None = Header(default=None),
           x_request_id: UUID | None = Header(default=None),
           geo: DgisGeoProvider = Depends(get_geo_provider)) -> dict | JSONResponse:
    request_id = str(x_request_id) if x_request_id else None
    if x_device_session is None:
        return failure("UNAUTHORIZED", "Укажите гостевую сессию", 401, request_id)
    if cityId not in {city.cityId for city in CITIES} or len(q.strip()) < 2:
        return failure("VALIDATION_ERROR", "Проверьте город и строку поиска", 400, request_id)
    limited = _client_rate_limit(x_device_session, request_id, request)
    if limited:
        return limited
    try:
        candidates = geo.search_candidates(cityId, q.strip())
        return {"items": [PlaceSummary(
            placeId=item.placeId, name=item.name, lat=item.lat, lon=item.lon,
            isFood=item.isFood,
        ) for item in candidates]}
    except (GeoAuthenticationError, GeoRateLimited, GeoInvalidResponse, GeoUnavailable) as exc:
        return dgis_failure(exc, request_id)


@app.post("/v1/routes/interpret", response_model=QueryPreview)
def preview_route(request: Request, payload: CreateRoute,
                  x_device_session: UUID | None = Header(default=None),
                  x_request_id: UUID | None = Header(default=None),
                  provider: OpenAIIntentProvider = Depends(get_intent_provider)) -> QueryPreview | JSONResponse:
    request_id = str(x_request_id) if x_request_id else None
    authorization = _authorize_create(payload, x_device_session, request_id)
    if authorization:
        return authorization
    limited = _client_rate_limit(x_device_session, request_id, request)
    if limited:
        return limited
    try:
        return interpret(payload, provider, request_id or str(uuid4()))
    except IntentNeedsClarification as exc:
        return failure("QUERY_NEEDS_CLARIFICATION", _clarification_message(exc.fields), 422,
                       request_id, {"fields": exc.fields})
    except IntentAuthenticationError:
        return failure("LLM_AUTH_ERROR", "Ключ LLM не принят сервером", 503, request_id)
    except IntentUnavailable:
        return failure("LLM_UNAVAILABLE", "Разбор запроса пока недоступен", 503, request_id)
    except IntentInvalidResponse:
        return failure("LLM_INVALID_RESPONSE", "Не удалось понять пожелания. Попробуйте ещё раз", 502, request_id)


@app.post("/v1/routes", response_model=Route)
def create_route(request: Request, payload: CreateRoute, x_device_session: UUID | None = Header(default=None),
                 x_request_id: UUID | None = Header(default=None),
                 intent_provider: OpenAIIntentProvider = Depends(get_intent_provider),
                 geo: DgisGeoProvider = Depends(get_geo_provider),
                 catalog: CatalogPlaceProvider = Depends(get_catalog_provider),
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
    limited = _client_rate_limit(x_device_session, request_id, request)
    if limited:
        return limited
    route_or_error = _build(payload, intent_provider, geo, request_id, catalog)
    if isinstance(route_or_error, JSONResponse):
        return route_or_error
    route = route_or_error
    repository.save_new(route, x_device_session, payload)
    with STATE_LOCK:
        RECENT_ROUTES[recent_key] = (time.monotonic() + _recent_route_ttl(), route)
        if cache_key:
            IDEMPOTENT_ROUTES[cache_key] = route
    return route


@app.get("/v1/routes/history", response_model=dict[str, list[GuestHistoryItem]])
def guest_route_history(x_device_session: UUID | None = Header(default=None),
                        x_request_id: UUID | None = Header(default=None),
                        repository: RouteRepository = Depends(get_route_repository)) -> dict | JSONResponse:
    request_id = str(x_request_id) if x_request_id else None
    if x_device_session is None:
        return failure("UNAUTHORIZED", "Укажите гостевую сессию", 401, request_id)
    items = []
    for route, updated_at in repository.list_guest_history(x_device_session, limit=3):
        latest_walk = repository.latest_walk_for_route(x_device_session, route.routeId)
        items.append(GuestHistoryItem(
            routeId=route.routeId, routeVersion=route.routeVersion, cityId=route.cityId,
            title=route.points[0].name if route.points else "Маршрут по городу",
            totalMinutes=route.totalMinutes, pointCount=len(route.points), updatedAt=updated_at,
            walkStatus=(latest_walk.session.status if latest_walk else None),
        ))
    return {"items": items}


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


@app.post("/v1/routes/{route_id}/walks", response_model=WalkSession)
def create_walk(route_id: UUID, payload: StartWalk,
                x_device_session: UUID | None = Header(default=None),
                x_request_id: UUID | None = Header(default=None),
                repository: RouteRepository = Depends(get_route_repository)) -> WalkSession | JSONResponse:
    request_id = str(x_request_id) if x_request_id else None
    if x_device_session is None:
        return failure("NOT_FOUND", "Маршрут не найден", 404, request_id)
    with STATE_LOCK:
        route_state = repository.get(route_id, x_device_session)
        if route_state is None:
            return failure("NOT_FOUND", "Маршрут не найден", 404, request_id)
        route = route_state[0]
        if payload.routeVersion != route.routeVersion:
            return failure("VERSION_CONFLICT", "Маршрут уже изменён", 409, request_id,
                           {"currentVersion": route.routeVersion})
        active = repository.find_active_walk(x_device_session)
        if active is not None:
            abandoned = repository.find_abandoned_active_walk(x_device_session)
            if abandoned is not None and abandoned.session.walkId == active.session.walkId:
                abandoned_route = repository.get_version(
                    abandoned.session.routeId, x_device_session, abandoned.session.routeVersion,
                )
                if abandoned_route is not None:
                    # Do not use COMPLETED for inactivity. This uses the same
                    # validated STOP transition as an explicit user action.
                    repository.replace_walk(apply_action(
                        abandoned, abandoned_route, WalkAction(action="STOP"),
                    ), x_device_session)
                    active = None
            if active is not None:
                if (active.session.routeId == route_id
                        and active.session.routeVersion == payload.routeVersion):
                    return session_at(active)
                return failure("ACTIVE_WALK_EXISTS", "Сначала завершите текущую прогулку", 409,
                               request_id, {"walkId": str(active.session.walkId)})
        try:
            state = start_walk(route, payload)
        except WalkInvalidState:
            return failure("VERSION_CONFLICT", "Нельзя начать эту версию маршрута", 409,
                           request_id)
        repository.save_walk(state, x_device_session)
        return session_at(state)


@app.get("/v1/walks/{walk_id}", response_model=WalkSession)
def get_walk(walk_id: UUID, x_device_session: UUID | None = Header(default=None),
             x_request_id: UUID | None = Header(default=None),
             repository: RouteRepository = Depends(get_route_repository)) -> WalkSession | JSONResponse:
    request_id = str(x_request_id) if x_request_id else None
    if x_device_session is None:
        return failure("NOT_FOUND", "Прогулка не найдена", 404, request_id)
    state = repository.get_walk(walk_id, x_device_session)
    if state is None:
        return failure("NOT_FOUND", "Прогулка не найдена", 404, request_id)
    return session_at(state)


def _recommendation_context(
        state: WalkState, route: Route, moment: datetime,
        require_position: bool = True,
) -> tuple[str, set[str]] | None:
    """Cheap persisted checks which must run before any recommendation API call."""
    session = state.session
    order = session.currentPointOrder
    if (session.status != "ACTIVE" or session.phase != "VISITING"
            or order is None or not 1 <= order <= len(route.points)):
        return None
    point = route.points[order - 1]
    if point.pointType != "TOUR":
        return None
    if any(item.pointPlaceId == point.placeId
           for item in state.recommendations.decisions):
        return None
    if point.placeId in state.recommendations.exhaustedPointPlaceIds:
        return None
    allowed = {"COFFEE", "RESTAURANT"} - set(
        state.recommendations.usedCategories)
    if not allowed:
        return None
    if require_position:
        position = state.lastPosition
        measured = position.measuredAt.astimezone(timezone.utc) if position else None
        age = ((moment - measured).total_seconds()
               if measured else MAX_POSITION_AGE_SECONDS + 1)
        if (position is None or position.accuracyMeters > MAX_POSITION_ACCURACY_METERS
                or age < -5 or age > MAX_POSITION_AGE_SECONDS):
            return None
    return point.placeId, allowed


def _accepted_recommendation(state: WalkState, partner_brand_id: str,
                             dgis_place_id: str) -> bool:
    return any(
        item.decision == "ACCEPTED"
        and item.partnerBrandId == partner_brand_id
        and item.dgisPlaceId == dgis_place_id
        for item in state.recommendations.decisions
    )


def _selection_is_current(state: WalkState, selection: RecommendationSelection,
                          moment: datetime) -> bool:
    position = state.lastPosition
    age = (moment - selection.selectedAt.astimezone(timezone.utc)).total_seconds()
    if position is None or age < -5 or age > RECOMMENDATION_SELECTION_TTL_SECONDS:
        return False
    mean_latitude = math.radians((selection.originLat + position.lat) / 2)
    north = (position.lat - selection.originLat) * 111_320
    east = (position.lon - selection.originLon) * 111_320 * math.cos(mean_latitude)
    return math.hypot(north, east) <= 250


@app.get("/v1/walks/{walk_id}/partner-offer", response_model=PartnerOfferResponse)
def get_partner_offer(
        walk_id: UUID,
        x_device_session: UUID | None = Header(default=None),
        repository: RouteRepository = Depends(get_route_repository),
        registry: PartnerRegistry = Depends(get_partner_registry),
        geo: DgisGeoProvider = Depends(get_geo_provider),
) -> PartnerOfferResponse | JSONResponse:
    if x_device_session is None:
        return failure("NOT_FOUND", "Прогулка не найдена", 404)
    state = repository.get_walk(walk_id, x_device_session)
    if state is None:
        return failure("NOT_FOUND", "Прогулка не найдена", 404)
    route = repository.get_version(
        state.session.routeId, x_device_session, state.session.routeVersion,
    )
    if route is None:
        return failure("VERSION_CONFLICT", "Версия маршрута недоступна", 409)
    moment = datetime.now(timezone.utc)
    context = _recommendation_context(state, route, moment)
    if context is None:
        return PartnerOfferResponse(status="NONE", offer=None)
    point_place_id, allowed_categories = context
    selected = state.recommendations.selected
    if selected is not None and selected.pointPlaceId == point_place_id:
        commercial_active = (not selected.offer.isCommercial or any(
            offer.offer_id == selected.offer.offerId
            for offer in registry.eligible_offers(route.cityId, moment)
        ))
        if (selected.offer.category in allowed_categories and commercial_active
                and _selection_is_current(state, selected, moment)):
            return PartnerOfferResponse(status="AVAILABLE", offer=selected.offer)
        # Never rotate to a different venue on the same tourist point.
        return PartnerOfferResponse(status="NONE", offer=None)
    try:
        offer = PartnerOfferSelector(registry, geo).select(
            state, route.cityId, moment,
            excluded_place_ids={point.placeId for point in route.points},
            allowed_categories=allowed_categories,
        )
    except GeoUnavailable:
        # This optional provider failure is explicit in the response but remains
        # a successful walk request: Android hides the card and keeps navigating.
        return PartnerOfferResponse(status="PROVIDER_UNAVAILABLE", offer=None)
    if offer is None:
        with STATE_LOCK:
            latest = repository.get_walk(walk_id, x_device_session)
            latest_route = (repository.get_version(
                latest.session.routeId, x_device_session, latest.session.routeVersion,
            ) if latest is not None else None)
            latest_context = (_recommendation_context(latest, latest_route, moment)
                              if latest is not None and latest_route is not None else None)
            if latest_context is not None and latest_context[0] == point_place_id:
                exhausted = list(dict.fromkeys([
                    *latest.recommendations.exhaustedPointPlaceIds, point_place_id,
                ]))
                recommendations = latest.recommendations.model_copy(update={
                    "exhaustedPointPlaceIds": exhausted, "selected": None,
                })
                repository.replace_walk(latest.model_copy(update={
                    "recommendations": recommendations,
                }), x_device_session)
        return PartnerOfferResponse(status="NONE", offer=None)
    position = state.lastPosition
    assert position is not None
    selection = RecommendationSelection(
        pointPlaceId=point_place_id, selectedAt=moment,
        originLat=position.lat, originLon=position.lon, offer=offer,
    )
    with STATE_LOCK:
        latest = repository.get_walk(walk_id, x_device_session)
        latest_route = (repository.get_version(
            latest.session.routeId, x_device_session, latest.session.routeVersion,
        ) if latest is not None else None)
        latest_context = (_recommendation_context(latest, latest_route, moment)
                          if latest is not None and latest_route is not None else None)
        if latest_context is None or latest_context[0] != point_place_id:
            return PartnerOfferResponse(status="NONE", offer=None)
        existing = latest.recommendations.selected
        if existing is not None and existing.pointPlaceId == point_place_id:
            if (existing.offer.category in latest_context[1]
                    and _selection_is_current(latest, existing, moment)):
                return PartnerOfferResponse(status="AVAILABLE", offer=existing.offer)
            return PartnerOfferResponse(status="NONE", offer=None)
        updated_recommendations = latest.recommendations.model_copy(update={
            "selected": selection,
        })
        if not repository.replace_walk(latest.model_copy(update={
                "recommendations": updated_recommendations,
        }), x_device_session):
            return PartnerOfferResponse(status="NONE", offer=None)
    return PartnerOfferResponse(status="AVAILABLE", offer=offer)


@app.post("/v1/walks/{walk_id}/partner-offer/dismiss",
          response_model=PartnerOfferResponse)
def dismiss_partner_offer(
        walk_id: UUID,
        x_device_session: UUID | None = Header(default=None),
        repository: RouteRepository = Depends(get_route_repository),
) -> PartnerOfferResponse | JSONResponse:
    if x_device_session is None:
        return failure("NOT_FOUND", "Прогулка не найдена", 404)
    with STATE_LOCK:
        state = repository.get_walk(walk_id, x_device_session)
        if state is None:
            return failure("NOT_FOUND", "Прогулка не найдена", 404)
        route = repository.get_version(
            state.session.routeId, x_device_session, state.session.routeVersion,
        )
        if route is None:
            return failure("VERSION_CONFLICT", "Версия маршрута недоступна", 409)
        context = _recommendation_context(
            state, route, datetime.now(timezone.utc), require_position=False,
        )
        selected = state.recommendations.selected
        if context is None or selected is None or selected.pointPlaceId != context[0]:
            return PartnerOfferResponse(status="NONE", offer=None)
        decisions = [*state.recommendations.decisions, RecommendationDecision(
            pointPlaceId=context[0], decision="DISMISSED",
            category=selected.offer.category,
            partnerBrandId=selected.offer.partnerBrandId,
            dgisPlaceId=selected.offer.dgisPlaceId,
            decidedAt=datetime.now(timezone.utc),
        )]
        recommendations = state.recommendations.model_copy(update={
            "decisions": decisions, "selected": None,
        })
        repository.replace_walk(state.model_copy(update={
            "recommendations": recommendations,
        }), x_device_session)
    return PartnerOfferResponse(status="NONE", offer=None)


@app.post("/v1/walks/{walk_id}/insert-suggested-place",
          response_model=InsertSuggestedPlaceResponse)
def insert_walk_suggested_place(
        request: Request,
        walk_id: UUID,
        payload: InsertSuggestedPlaceRequest,
        x_device_session: UUID | None = Header(default=None),
        x_request_id: UUID | None = Header(default=None),
        repository: RouteRepository = Depends(get_route_repository),
        registry: PartnerRegistry = Depends(get_partner_registry),
        geo: DgisGeoProvider = Depends(get_geo_provider),
) -> InsertSuggestedPlaceResponse | JSONResponse:
    request_id = str(x_request_id) if x_request_id else None
    if x_device_session is None:
        return failure("NOT_FOUND", "Прогулка не найдена", 404, request_id)
    limited = _client_rate_limit(x_device_session, request_id, request)
    if limited:
        return limited

    state = repository.get_walk(walk_id, x_device_session)
    if state is None:
        return failure("NOT_FOUND", "Прогулка не найдена", 404, request_id)
    route_state = repository.get(state.session.routeId, x_device_session)
    if route_state is None:
        return failure("NOT_FOUND", "Маршрут не найден", 404, request_id)
    current, source = route_state
    if (_accepted_recommendation(
            state, payload.partnerBrandId, payload.dgisPlaceId)
            and any(point.placeId == payload.dgisPlaceId for point in current.points)):
        return InsertSuggestedPlaceResponse(route=current, walk=session_at(state))
    if (payload.expectedRouteVersion != current.routeVersion
            or state.session.routeVersion != current.routeVersion):
        return failure("VERSION_CONFLICT", "Маршрут уже изменён", 409, request_id,
                       {"currentVersion": current.routeVersion})
    if state.session.status != "ACTIVE" or state.session.phase != "VISITING":
        return failure("WALK_INVALID_STATE", "Добавление доступно только во время посещения",
                       409, request_id)
    position = state.lastPosition
    measured = position.measuredAt.astimezone(timezone.utc) if position else None
    position_age = ((datetime.now(timezone.utc) - measured).total_seconds()
                    if measured else MAX_POSITION_AGE_SECONDS + 1)
    if (position is None or position.accuracyMeters > MAX_POSITION_ACCURACY_METERS
            or position_age < -5 or position_age > MAX_POSITION_AGE_SECONDS):
        return failure("SUGGESTION_EXPIRED", "Нужна свежая точная геопозиция", 409,
                       request_id)
    current_order = state.session.currentPointOrder
    if current_order is None or not 1 <= current_order <= len(current.points):
        return failure("WALK_INVALID_STATE", "Текущая точка прогулки недоступна", 409,
                       request_id)
    point_place_id = current.points[current_order - 1].placeId
    context = _recommendation_context(state, current, datetime.now(timezone.utc))
    if context is None or context[0] != point_place_id:
        return failure("SUGGESTION_NOT_ALLOWED", "На этой точке рекомендации недоступны", 409,
                       request_id)
    if len(current.points) >= 8:
        return failure("POINT_LIMIT_REACHED", "В маршруте может быть не больше восьми точек",
                       409, request_id)
    if any(point.placeId == payload.dgisPlaceId for point in current.points):
        return failure("PLACE_ALREADY_IN_ROUTE", "Это заведение уже есть в маршруте", 409,
                       request_id)

    pilot = {partner_id: (name, segment)
             for partner_id, name, segment in NAME_SEARCH_PILOT}
    brand = pilot.get(payload.partnerBrandId)
    if brand is None:
        active = {offer.partner_brand_id: (offer.search_query, offer.segment)
                  for offer in registry.eligible_offers(
                      current.cityId, datetime.now(timezone.utc))}
        brand = active.get(payload.partnerBrandId)
    if brand is None or current.cityId != "moscow":
        return failure("SUGGESTION_NOT_ALLOWED", "Рекомендация больше недоступна", 409,
                       request_id)
    expected_name, segment = brand
    if segment not in context[1]:
        return failure("SUGGESTION_NOT_ALLOWED", "Эта категория уже использована", 409,
                       request_id)
    selected = state.recommendations.selected
    if (selected is not None and selected.pointPlaceId == point_place_id
            and (selected.offer.partnerBrandId != payload.partnerBrandId
                 or selected.offer.dgisPlaceId != payload.dgisPlaceId
                 or selected.offer.category != segment)):
        return failure("SUGGESTION_EXPIRED", "Предложение больше не актуально", 409,
                       request_id)

    try:
        branch = geo.resolve_suggested_branch(
            current.cityId, payload.dgisPlaceId, expected_name,
        )
        if branch is None:
            return failure("SUGGESTION_NOT_FOUND", "Не удалось подтвердить заведение в 2ГИС",
                           422, request_id)
        replacement = insert_suggested_place(
            current, branch, segment, current_order, geo,
        ).model_copy(update={"routeVersion": current.routeVersion + 1})
    except (GeoAuthenticationError, GeoRateLimited, GeoInvalidResponse, GeoUnavailable) as exc:
        return dgis_failure(exc, request_id)
    except DurationConfirmationRequired as exc:
        return failure(
            "TIME_BUDGET_CONFIRMATION_REQUIRED",
            "После добавления маршрут займёт больше выбранного времени",
            409, request_id,
            {"requestedMinutes": exc.requested_minutes,
             "projectedMinutes": exc.projected_minutes,
             "overrunMinutes": exc.overrun_minutes,
             "durationMode": exc.duration_mode,
             "canOverride": False},
        )
    except RouteNotFound:
        return failure("ROUTE_NOT_FOUND", "Не удалось безопасно добавить заведение в маршрут",
                       422, request_id)

    delta = replacement.totalMinutes - current.totalMinutes
    with STATE_LOCK:
        latest_walk = repository.get_walk(walk_id, x_device_session)
        latest_route = repository.get(current.routeId, x_device_session)
        if (latest_walk is not None and latest_route is not None
                and _accepted_recommendation(
                    latest_walk, payload.partnerBrandId, payload.dgisPlaceId)
                and any(point.placeId == payload.dgisPlaceId
                        for point in latest_route[0].points)):
            return InsertSuggestedPlaceResponse(
                route=latest_route[0], walk=session_at(latest_walk),
            )
        if (latest_walk is None or latest_route is None
                or latest_route[0].routeVersion != current.routeVersion
                or latest_walk.session.routeVersion != current.routeVersion
                or latest_walk.session.status != "ACTIVE"
                or latest_walk.session.phase != "VISITING"
                or latest_walk.session.currentPointOrder != current_order):
            latest_version = latest_route[0].routeVersion if latest_route else current.routeVersion
            return failure("VERSION_CONFLICT", "Маршрут или прогулка уже изменились", 409,
                           request_id, {"currentVersion": latest_version})
        latest_context = _recommendation_context(
            latest_walk, latest_route[0], datetime.now(timezone.utc),
        )
        if latest_context is None or latest_context[0] != point_place_id:
            return failure("SUGGESTION_NOT_ALLOWED", "Рекомендация больше недоступна", 409,
                           request_id)
        latest_selected = latest_walk.recommendations.selected
        if (latest_selected is not None
                and latest_selected.pointPlaceId == point_place_id
                and (latest_selected.offer.partnerBrandId != payload.partnerBrandId
                     or latest_selected.offer.dgisPlaceId != payload.dgisPlaceId
                     or latest_selected.offer.category != segment)):
            return failure("SUGGESTION_EXPIRED", "Предложение больше не актуально", 409,
                           request_id)
        decisions = [*latest_walk.recommendations.decisions, RecommendationDecision(
            pointPlaceId=point_place_id, decision="ACCEPTED", category=segment,
            partnerBrandId=payload.partnerBrandId, dgisPlaceId=payload.dgisPlaceId,
            decidedAt=datetime.now(timezone.utc),
        )]
        categories = [*latest_walk.recommendations.usedCategories, segment]
        recommendations = latest_walk.recommendations.model_copy(update={
            "usedCategories": list(dict.fromkeys(categories)),
            "decisions": decisions, "selected": None,
        })
        updated_session = latest_walk.session.model_copy(update={
            "routeVersion": replacement.routeVersion,
            "estimatedRemainingMinutes": max(
                0, latest_walk.session.estimatedRemainingMinutes + delta,
            ),
        })
        updated_walk = latest_walk.model_copy(update={
            "session": updated_session, "recommendations": recommendations,
        })
        if not repository.replace_route_and_walk(
                replacement, updated_walk, x_device_session, source,
                current.routeVersion):
            return failure("VERSION_CONFLICT", "Маршрут уже изменён", 409, request_id)
    return InsertSuggestedPlaceResponse(
        route=replacement, walk=session_at(updated_walk),
    )


@app.get("/v1/routes/{route_id}/walks/active", response_model=WalkSession)
def get_active_walk(route_id: UUID,
                    x_device_session: UUID | None = Header(default=None),
                    x_request_id: UUID | None = Header(default=None),
                    repository: RouteRepository = Depends(
                        get_route_repository)) -> WalkSession | JSONResponse:
    """Restore a walk after the isolated Android map process was terminated."""
    request_id = str(x_request_id) if x_request_id else None
    if x_device_session is None:
        return failure("NOT_FOUND", "Активная прогулка не найдена", 404, request_id)
    state = repository.find_active_walk(x_device_session)
    if state is None or state.session.routeId != route_id:
        return failure("NOT_FOUND", "Активная прогулка не найдена", 404, request_id)
    return session_at(state)


@app.get("/v1/routes/{route_id}/walks/latest", response_model=WalkSession)
def get_latest_walk_for_route(route_id: UUID,
                              x_device_session: UUID | None = Header(default=None),
                              x_request_id: UUID | None = Header(default=None),
                              repository: RouteRepository = Depends(
                                  get_route_repository)) -> WalkSession | JSONResponse:
    """Return the most recent lifecycle state after the route was confirmed."""
    request_id = str(x_request_id) if x_request_id else None
    if x_device_session is None or repository.get(route_id, x_device_session) is None:
        return failure("NOT_FOUND", "Маршрут не найден", 404, request_id)
    state = repository.latest_walk_for_route(x_device_session, route_id)
    if state is None:
        return failure("NOT_FOUND", "Прогулка не найдена", 404, request_id)
    return session_at(state)


@app.post("/v1/walks/{walk_id}/positions", response_model=WalkProgress)
def add_walk_position(walk_id: UUID, payload: WalkPosition,
                      x_device_session: UUID | None = Header(default=None),
                      x_request_id: UUID | None = Header(default=None),
                      repository: RouteRepository = Depends(get_route_repository)) -> WalkProgress | JSONResponse:
    request_id = str(x_request_id) if x_request_id else None
    if x_device_session is None:
        return failure("NOT_FOUND", "Прогулка не найдена", 404, request_id)
    limited = _position_rate_limit(walk_id, request_id)
    if limited:
        return limited
    with STATE_LOCK:
        state = repository.get_walk(walk_id, x_device_session)
        if state is None:
            return failure("NOT_FOUND", "Прогулка не найдена", 404, request_id)
        route = repository.get_version(
            state.session.routeId, x_device_session, state.session.routeVersion,
        )
        if route is None:
            return failure("VERSION_CONFLICT", "Версия маршрута недоступна", 409, request_id)
        try:
            updated, progress = register_position(state, route, payload)
        except WalkInvalidState:
            return failure("WALK_NOT_ACTIVE", "Прогулка сейчас не активна", 409, request_id)
        except WalkInvalidPosition:
            return failure("VALIDATION_ERROR", "Некорректное время геопозиции", 400,
                           request_id)
        repository.replace_walk(updated, x_device_session)
        return progress


@app.post("/v1/walks/{walk_id}/actions", response_model=WalkSession)
def walk_action(walk_id: UUID, payload: WalkAction,
                x_device_session: UUID | None = Header(default=None),
                x_request_id: UUID | None = Header(default=None),
                repository: RouteRepository = Depends(get_route_repository)) -> WalkSession | JSONResponse:
    request_id = str(x_request_id) if x_request_id else None
    if x_device_session is None:
        return failure("NOT_FOUND", "Прогулка не найдена", 404, request_id)
    with STATE_LOCK:
        state = repository.get_walk(walk_id, x_device_session)
        if state is None:
            return failure("NOT_FOUND", "Прогулка не найдена", 404, request_id)
        route = repository.get_version(
            state.session.routeId, x_device_session, state.session.routeVersion,
        )
        if route is None:
            return failure("VERSION_CONFLICT", "Версия маршрута недоступна", 409, request_id)
        try:
            updated = apply_action(state, route, payload)
        except WalkInvalidState:
            return failure("WALK_INVALID_STATE", "Действие недоступно в текущем состоянии", 409,
                           request_id)
        repository.replace_walk(updated, x_device_session)
        return updated.session


@app.delete("/v1/routes/{route_id}", status_code=204, response_model=None)
def delete_route(route_id: UUID, x_device_session: UUID | None = Header(default=None),
                 x_request_id: UUID | None = Header(default=None),
                 repository: RouteRepository = Depends(get_route_repository)) -> Response | JSONResponse:
    request_id = str(x_request_id) if x_request_id else None
    with STATE_LOCK:
        if x_device_session is None:
            return failure("NOT_FOUND", "Маршрут не найден", 404, request_id)
        active = repository.find_active_walk(x_device_session)
        if active is not None and active.session.routeId == route_id:
            return failure("WALK_ACTIVE", "Сначала завершите или остановите прогулку", 409,
                           request_id)
        if not repository.delete(route_id, x_device_session):
            return failure("NOT_FOUND", "Маршрут не найден", 404, request_id)
        for key, route in list(IDEMPOTENT_ROUTES.items()):
            if key[0] == x_device_session and route.routeId == route_id:
                IDEMPOTENT_ROUTES.pop(key, None)
        for key, route in list(IDEMPOTENT_REVISIONS.items()):
            if key[0] == x_device_session and route.routeId == route_id:
                IDEMPOTENT_REVISIONS.pop(key, None)
        for key, cached in list(RECENT_ROUTES.items()):
            if key[0] == x_device_session and cached[1].routeId == route_id:
                RECENT_ROUTES.pop(key, None)
    return Response(status_code=204)


@app.post("/v1/routes/{route_id}/revisions", response_model=Route)
def revise_route(request: Request, route_id: UUID, revision: RouteRevision,
                 x_device_session: UUID | None = Header(default=None),
                 x_request_id: UUID | None = Header(default=None),
                 intent_provider: OpenAIIntentProvider = Depends(get_intent_provider),
                 geo: DgisGeoProvider = Depends(get_geo_provider),
                 catalog: CatalogPlaceProvider = Depends(get_catalog_provider),
                 repository: RouteRepository = Depends(get_route_repository)) -> Route | JSONResponse:
    request_id = str(x_request_id) if x_request_id else None
    if x_device_session is None:
        return failure("NOT_FOUND", "Маршрут не найден", 404, request_id)
    idempotency_key = (x_device_session, x_request_id) if x_request_id else None
    with STATE_LOCK:
        if idempotency_key and idempotency_key in IDEMPOTENT_REVISIONS:
            return IDEMPOTENT_REVISIONS[idempotency_key]
    limited = _client_rate_limit(x_device_session, request_id, request)
    if limited:
        return limited
    state = repository.get(route_id, x_device_session)
    if state is None:
        return failure("NOT_FOUND", "Маршрут не найден", 404, request_id)
    current, source = state
    if revision.baseVersion != current.routeVersion:
        return failure("VERSION_CONFLICT", "Маршрут уже изменён", 409, request_id,
                       {"currentVersion": current.routeVersion})
    if revision.mode in {"CHANGE_QUERY", "CHAT_REVISION"}:
        if revision.mode == "CHAT_REVISION":
            if revision.message is None or revision.query is not None or revision.pointIds is not None:
                return failure("VALIDATION_ERROR", "Для сообщения чата нужен только текст правки", 400,
                               request_id, {"fields": ["message"]})
            # Keep the route source compact and preserve the previous intent context for
            # the existing structured parser. The model receives no POI/provider facts.
            next_query = source.query + "\nУточнение к текущему маршруту: " + revision.message
        else:
            next_query = revision.query
        if next_query is None or revision.pointIds is not None:
            return failure("VALIDATION_ERROR", "Для изменения маршрута нужен новый текст", 400,
                           request_id, {"fields": ["query"]})
        payload = CreateRoute(
            cityId=source.cityId, query=next_query,
            filters=revision.filters if revision.filters is not None else source.filters,
            startLocation=source.startLocation, deviceSessionId=x_device_session,
        )
        route_or_error = _build(payload, intent_provider, geo, request_id, catalog)
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
            replacement = rebuild_route_with_points(
                current, source, candidates, geo,
                allow_duration_overrun=revision.allowDurationOverrun,
            ).model_copy(
                update={"routeVersion": revision.baseVersion + 1}
            )
        except GeoPlaceNotFound:
            return failure("ROUTE_NOT_FOUND", "Одна из точек не найдена в выбранном городе", 422,
                           request_id)
        except (GeoAuthenticationError, GeoRateLimited, GeoInvalidResponse, GeoUnavailable) as exc:
            return dgis_failure(exc, request_id)
        except DurationConfirmationRequired as exc:
            return failure(
                "TIME_BUDGET_CONFIRMATION_REQUIRED",
                "После изменения маршрут займёт больше выбранного времени",
                409, request_id,
                {
                    "requestedMinutes": exc.requested_minutes,
                    "projectedMinutes": exc.projected_minutes,
                    "overrunMinutes": exc.overrun_minutes,
                    "durationMode": exc.duration_mode,
                    "canOverride": True,
                },
            )
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
    # A paused walk must continue against the accepted route revision rather
    # than the immutable geometry of its previous version. Preserve whether
    # the user paused it manually; the client decides if an automatic editing
    # pause should be resumed after confirmation.
    active_walk = repository.find_active_walk(x_device_session)
    if active_walk is not None and active_walk.session.routeId == route_id:
        current_order = min(
            active_walk.session.currentPointOrder or 1,
            max(1, len(replacement.points)),
        )
        rebased_session = active_walk.session.model_copy(update={
            "routeVersion": replacement.routeVersion,
            "currentPointOrder": current_order,
            "estimatedRemainingMinutes": replacement.totalMinutes,
            "phase": "MOVING",
            "visitStartedAt": None,
            "visitElapsedSeconds": 0,
            "finalPointVisitStartedAt": None,
        })
        rebased_walk = active_walk.model_copy(update={
            "session": rebased_session,
            "proximityStartedAt": None,
            "proximityPointOrder": None,
            "exitStartedAt": None,
            "exitPointOrder": None,
            "visitPausedSeconds": 0,
            "finalPointPausedSeconds": 0,
        })
        repository.replace_walk(rebased_walk, x_device_session)
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
           geo: DgisGeoProvider, request_id: str | None,
           catalog: CatalogPlaceProvider | None = None) -> Route | JSONResponse:
    trace_id = request_id or str(uuid4())
    try:
        # Routing is mandatory for every published walk. Keep a cheap legacy
        # preflight, but do not require a Places key until a Places operation
        # is actually requested by build_route.
        ensure_routing = getattr(geo, "ensure_routing_configured", geo.ensure_configured)
        ensure_routing()
        preview = interpret(payload, intent_provider, trace_id)
        return build_route(payload, preview, geo, trace_id=trace_id, catalog=catalog)
    except IntentNeedsClarification as exc:
        planning_log(trace_id, "planning_error", error="QUERY_NEEDS_CLARIFICATION",
                     fields=exc.fields)
        return failure("QUERY_NEEDS_CLARIFICATION", _clarification_message(exc.fields), 422,
                       request_id, {"fields": exc.fields})
    except IntentAuthenticationError:
        planning_log(trace_id, "planning_error", error="LLM_AUTH_ERROR")
        return failure("LLM_AUTH_ERROR", "Ключ LLM не принят сервером", 503, request_id)
    except IntentUnavailable:
        planning_log(trace_id, "planning_error", error="LLM_UNAVAILABLE")
        return failure("LLM_UNAVAILABLE", "Разбор запроса пока недоступен", 503, request_id)
    except IntentInvalidResponse:
        planning_log(trace_id, "planning_error", error="LLM_INVALID_RESPONSE")
        return failure("LLM_INVALID_RESPONSE", "Не удалось понять пожелания. Попробуйте ещё раз", 502, request_id)
    except (GeoAuthenticationError, GeoRateLimited) as exc:
        planning_log(trace_id, "planning_error", error=type(exc).__name__)
        return dgis_failure(exc, request_id)
    except GeoConstraintNotFound:
        planning_log(trace_id, "planning_error", error="GEO_CONSTRAINT_NOT_FOUND")
        return failure("GEO_CONSTRAINT_NOT_FOUND", "Не удалось найти указанную часть города в 2ГИС", 422,
                       request_id, {"fields": ["locationHint"]})
    except (GeoInvalidResponse, GeoUnavailable) as exc:
        planning_log(trace_id, "planning_error", error=type(exc).__name__)
        return dgis_failure(exc, request_id)
    except TimeBudgetExceeded as exc:
        planning_log(trace_id, "planning_error", error="TIME_BUDGET_EXCEEDED",
                     minimumMinutes=exc.minimum_minutes)
        details = {"minimumMinutes": exc.minimum_minutes} if exc.minimum_minutes else {}
        return failure("TIME_BUDGET_EXCEEDED", "Точки не помещаются в выбранное время", 422,
                       request_id, details)
    except RouteNotFound:
        planning_log(trace_id, "planning_error", error="ROUTE_NOT_FOUND")
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


def _clarification_message(fields: list[str]) -> str:
    if "startLocationHint" in fields:
        return "Уточните точное название или адрес стартовой точки"
    if "cityId" in fields:
        return "Город в тексте не совпадает с выбранным городом"
    if "durationMinutes" in fields:
        return "Уточните длительность прогулки от 30 минут до 12 часов"
    return "Уточните параметры прогулки"


def _source_key(request: Request | None) -> str | None:
    if request is None or request.client is None:
        return None
    peer = request.client.host
    trusted = {item.strip() for item in os.getenv("TRUSTED_PROXY_HOSTS", "").split(",") if item.strip()}
    if peer in trusted:
        forwarded = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        if forwarded:
            peer = forwarded
    return hashlib.blake2b(f"{SOURCE_RATE_SALT}:{peer}".encode(), digest_size=16).hexdigest()


def _prune_rate_state(now: float) -> None:
    for store in (CLIENT_REQUESTS, POSITION_REQUESTS, SOURCE_REQUESTS):
        for key in list(store):
            window = store[key]
            while window and window[0] <= now - 60:
                window.popleft()
            if not window:
                store.pop(key, None)
        while len(store) > 4096:
            store.pop(next(iter(store)), None)


def _client_rate_limit(session: UUID | None, request_id: str | None,
                       request: Request | None = None) -> JSONResponse | None:
    """Allow five expensive client operations per rolling minute and device session."""
    if session is None:
        return None
    now = time.monotonic()
    with STATE_LOCK:
        _prune_rate_state(now)
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
        source = _source_key(request)
        if source is not None:
            source_window = SOURCE_REQUESTS[source]
            if len(source_window) >= 20:
                retry_after = max(1, int(61 - (now - source_window[0])))
                return failure("RATE_LIMITED", "Слишком много тяжёлых запросов с этого источника. Повторите позже.",
                               429, request_id,
                               {"retryAfterSeconds": retry_after, "dependency": "source"},
                               {"Retry-After": str(retry_after)})
            source_window.append(now)
    return None


def _position_rate_limit(walk_id: UUID, request_id: str | None) -> JSONResponse | None:
    """Accept at most two geolocation submissions per rolling minute and walk."""
    now = time.monotonic()
    with STATE_LOCK:
        window = POSITION_REQUESTS[walk_id]
        while window and window[0] <= now - 60:
            window.popleft()
        if len(window) >= 2:
            retry_after = max(1, int(61 - (now - window[0])))
            return failure(
                "RATE_LIMITED",
                f"Геопозиция принимается не чаще двух раз в минуту. Повторите через {retry_after} сек.",
                429, request_id,
                {"retryAfterSeconds": retry_after, "dependency": "geolocation"},
                {"Retry-After": str(retry_after)},
            )
        window.append(now)
    return None

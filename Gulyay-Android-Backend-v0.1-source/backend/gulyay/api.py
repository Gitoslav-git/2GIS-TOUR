from __future__ import annotations

from uuid import UUID

from fastapi import FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .models import City, CreateRoute

app = FastAPI(title="Гуляй API", version="0.1.0")
CITIES = (City(cityId="tula", name="Тула"), City(cityId="vladimir", name="Владимир"))


def failure(code: str, message: str, status: int, request_id: str | None = None) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {
        "code": code, "message": message, "details": {}, "requestId": request_id,
    }})


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    return failure("VALIDATION_ERROR", "Проверьте заполненные поля", 400,
                   request.headers.get("X-Request-Id"))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.1.0"}


@app.get("/v1/cities", response_model=dict[str, list[City]])
def cities() -> dict[str, list[City]]:
    return {"cities": list(CITIES)}


@app.post("/v1/routes")
def create_route(payload: CreateRoute, x_device_session: UUID | None = Header(default=None),
                 x_request_id: UUID | None = Header(default=None)) -> JSONResponse:
    if payload.cityId not in {city.cityId for city in CITIES}:
        return failure("VALIDATION_ERROR", "Выберите доступный город", 400, str(x_request_id) if x_request_id else None)
    if payload.deviceSessionId is None or x_device_session != payload.deviceSessionId:
        return failure("UNAUTHORIZED", "Укажите гостевую сессию", 401, str(x_request_id) if x_request_id else None)
    # 0.1 is a foundation release. No synthetic POI or straight-line routing:
    # this endpoint cannot claim to deliver a 2GIS route until adapters are configured and validated.
    return failure("GEO_UNAVAILABLE", "Построение по данным 2ГИС пока не подключено", 503,
                   str(x_request_id) if x_request_id else None)

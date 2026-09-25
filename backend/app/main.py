import logging
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api.routes import router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db import engine

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger("sapartravel.http")


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("api_started", extra={"event": "system.startup"})
    yield
    engine.dispose()
    logger.info("api_stopped", extra={"event": "system.shutdown"})


app = FastAPI(title=settings.app_name, version="2.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    # Never echo request bodies/passwords in validation responses.
    errors = [{"field": ".".join(str(part) for part in error["loc"]), "message": error["msg"]} for error in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": "Проверьте заполненные поля.", "errors": errors})


@app.exception_handler(SQLAlchemyError)
async def database_error(_: Request, exc: SQLAlchemyError):
    logger.error("database_error", extra={"event": "database.error", "error_type": type(exc).__name__})
    return JSONResponse(status_code=503, content={"detail": "Не удалось обработать запрос. Повторите попытку позже."})


@app.middleware("http")
async def request_logging(request: Request, call_next):
    request_id = str(uuid4())
    started = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    if request.headers.get("Authorization") or "/auth/" in request.url.path:
        response.headers["Cache-Control"] = "no-store"
    logger.info("request_completed", extra={"event": "http.request", "request_id": request_id,
                "duration_ms": duration_ms, "status_code": response.status_code})
    return response


app.include_router(router, prefix=settings.api_prefix)

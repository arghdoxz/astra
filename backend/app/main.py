"""FastAPI entry point (Opus)."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from . import db
from .api.routes import ApiError, router
from .config import VERSION, get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("astra")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.conn()
    db.mark_stale_running()
    yield
    try:
        from .services import http

        await http.aclose()
    except Exception:  # noqa: BLE001
        pass


app = FastAPI(title="ASTRA API", version=VERSION, lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_origin_regex=settings.allowed_origin_regex,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.exception_handler(ApiError)
async def _api_error(_: Request, exc: ApiError):
    body = {"error": {"code": exc.code, "message": exc.message}}
    if exc.detail is not None:
        body["error"]["detail"] = exc.detail
    return JSONResponse(body, status_code=exc.status)


@app.exception_handler(RequestValidationError)
async def _validation(_: Request, exc: RequestValidationError):
    return JSONResponse({"error": {"code": "invalid_request", "message": "Invalid request parameters.",
                                   "detail": exc.errors()}}, status_code=422)


@app.exception_handler(Exception)
async def _internal(_: Request, exc: Exception):
    log.exception("unhandled error")
    return JSONResponse({"error": {"code": "internal_error", "message": "Internal server error."}}, status_code=500)


app.include_router(router)


@app.get("/")
async def root():
    return {"name": "ASTRA API", "version": VERSION, "docs": "/docs", "health": "/api/health"}

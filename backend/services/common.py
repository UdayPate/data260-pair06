"""
Shared setup for the six Lab 2 services: Student, Company, Job, Application, Event, AI Assistant.

All six run the SAME Lab 1 code (the routers, services and models in backend/app). Each one is a
small FastAPI app that mounts only the routers it owns (see services/<name>/main.py), so each
one can be built into its own Docker image, started on its own port and scaled on its own.

Every service gets the same four things from create_service_app():
  * GET /health      a cheap "am I alive?" answer, used by Docker HEALTHCHECK and Kubernetes probes
  * CORS             which website addresses may call it (CORS_ORIGINS, comma separated)
  * an X-P06-Service response header, so you can see which service answered (used in the demo)
  * the clean 500 reply for database errors

The old single app (app/main.py, port 9060) still exists. The tests and local development use it.
"""
import logging
import os
from typing import Iterable

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError

from app.config import FRONTEND_PORT, PAIR_STR, SERVICE_PORTS, UPLOAD_DIR

logger = logging.getLogger("handshake")


def routes_of(router: APIRouter, *paths: str) -> APIRouter:
    """A copy of `router` that keeps ONLY the listed paths (the full path, e.g. "/auth/login").
    Used when one Lab 1 router holds endpoints that belong to two different services."""
    wanted = set(paths)
    picked = APIRouter()
    picked.routes.extend(r for r in router.routes if getattr(r, "path", None) in wanted)
    missing = wanted - {r.path for r in picked.routes}
    if missing:  # a typo here would silently drop an endpoint, so fail loudly at start-up
        raise RuntimeError(f"routes_of: no such path(s) {sorted(missing)}")
    return picked


def cors_origins() -> list:
    """The website origins allowed to call the API. In Docker/Kubernetes set CORS_ORIGINS."""
    configured = os.getenv("CORS_ORIGINS", "")
    if configured.strip():
        return [o.strip() for o in configured.split(",") if o.strip()]
    return [f"http://localhost:{FRONTEND_PORT}", f"http://127.0.0.1:{FRONTEND_PORT}"]


def create_service_app(key: str, description: str, routers: Iterable[APIRouter],
                       serve_profile_pictures: bool = False) -> FastAPI:
    """key = "student", "company", "job", "application", "event" or "assistant"."""
    name = f"p06-{key}"                       # the pair prefix is part of every service name
    app = FastAPI(title=f"{name} (Pair {PAIR_STR})", version="2.0.0", description=description)

    app.add_middleware(
        CORSMiddleware, allow_origins=cors_origins(), allow_credentials=True,
        allow_methods=["*"], allow_headers=["*"],
    )

    @app.middleware("http")
    async def say_who_answered(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-P06-Service"] = name
        return response

    @app.exception_handler(SQLAlchemyError)
    async def database_error_handler(request: Request, exc: SQLAlchemyError):
        logger.exception("Database error on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "A database error occurred"})

    if serve_profile_pictures:
        # Profile pictures are public. Resumes are private and are NOT mounted here.
        pictures = os.path.join(UPLOAD_DIR, "profile_pics")
        os.makedirs(pictures, exist_ok=True)
        app.mount("/media/profile_pics", StaticFiles(directory=pictures), name="profile_pics")

    for router in routers:
        app.include_router(router)

    @app.get("/health", tags=["Health"], summary="Is this service running?")
    def health():
        return {"status": "ok", "service": name, "pair": PAIR_STR, "port": SERVICE_PORTS[key]}

    return app

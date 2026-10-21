from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.api import (
    auth,
    branches,
    catalog,
    classes,
    coach,
    gradings,
    instructors,
    inventory,
    leads,
    members,
    memberships,
    operations,
    payments,
    reports,
    users,
)
from app.core.config import get_settings
from app.core.db import dispose_engine, get_sessionmaker
from app.web import mount_frontend

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
CSRF_HEADER = "x-requested-with"

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await dispose_engine()


def create_app(frontend_dist: Path | None = None) -> FastAPI:
    s = get_settings()
    is_prod = s.environment == "production"
    app = FastAPI(
        title=f"{s.app_name} API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None if is_prod else "/api/docs",
        redoc_url=None,
        openapi_url=None if is_prod else "/api/openapi.json",
    )

    @app.middleware("http")
    async def csrf_and_headers(request: Request, call_next):
        # Cookie-authenticated API: unsafe requests must carry a custom header. Browsers cannot
        # attach it cross-site without a CORS preflight, which only allowed origins pass.
        if request.method in UNSAFE_METHODS and request.url.path.startswith("/api/"):
            if not request.headers.get(CSRF_HEADER):
                return JSONResponse({"detail": "Missing X-Requested-With header"}, status_code=403)
        response = await call_next(request)
        for k, v in SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        if is_prod:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        return response

    @app.exception_handler(IntegrityError)
    async def integrity_error(_: Request, __: IntegrityError) -> JSONResponse:
        # Unique/foreign-key violations; never echo the database message to clients.
        return JSONResponse({"detail": "Conflicts with existing data"}, status_code=409)

    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["Content-Type", "X-Requested-With"],
        expose_headers=["X-Total-Count"],
    )

    api = APIRouter(prefix="/api")
    modules = (
        auth,
        branches,
        users,
        catalog,
        instructors,
        members,
        memberships,
        payments,
        classes,
        coach,
        leads,
        gradings,
        operations,
        inventory,
        reports,
    )
    for module in modules:
        api.include_router(module.router)

    @api.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        async with get_sessionmaker()() as db:
            await db.execute(text("SELECT 1"))
        return {"status": "ok"}

    app.include_router(api)
    # Last, so API routes always win over the frontend's catch-all.
    mount_frontend(app, frontend_dist or s.frontend_dist_path())
    return app


app = create_app()

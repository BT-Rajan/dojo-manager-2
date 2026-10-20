"""Serve the built React app (frontend/dist) from the API process, so the whole system runs
on one port and one origin: session cookies and the CSRF header check work unchanged."""

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

# Vite builds no inline scripts; components set inline style attributes; the favicon is a
# data: URL. Everything else comes from this origin.
CONTENT_SECURITY_POLICY = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data:",
        "font-src 'self' data:",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ]
)


class _HashedAssets(StaticFiles):
    """/assets files have content hashes in their names, so they can be cached forever."""

    async def get_response(self, path: str, scope) -> Response:
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


def mount_frontend(app: FastAPI, dist: Path) -> bool:
    """Serve ``dist`` at ``/`` (after the API routes). Returns False if it is not built."""
    dist = dist.resolve()
    index = dist / "index.html"
    if not index.is_file():
        return False

    if (dist / "assets").is_dir():
        app.mount("/assets", _HashedAssets(directory=dist / "assets"), name="assets")

    def page(path: Path) -> FileResponse:
        response = FileResponse(path)
        response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
        # index.html must be revalidated so a new release is picked up immediately.
        response.headers["Cache-Control"] = "no-cache"
        return response

    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def frontend(path: str, request: Request) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404, "Not Found")  # unknown API routes stay JSON 404s
        if path:
            candidate = (dist / path).resolve()
            # Only real files inside dist; anything else (including ../ tricks) gets the app.
            if candidate.is_file() and candidate.is_relative_to(dist):
                return page(candidate)
        return page(index)  # client-side routes such as /members/12

    return True

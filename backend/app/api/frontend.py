"""Register static assets and the SPA fallback after API and MCP routes."""

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings


def mount_frontend(app: FastAPI) -> None:
    # Serve the built frontend (single-page app) when it exists.
    _dist = settings.frontend_dist
    if _dist.is_dir():
        app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        async def spa(path: str) -> FileResponse:
            if path.startswith("api/"):
                raise HTTPException(404)
            candidate = (_dist / path).resolve()
            if path and candidate.is_file() and candidate.is_relative_to(_dist.resolve()):
                return FileResponse(
                    candidate, headers={"Cache-Control": "no-cache"} if path.startswith("favicon.") else None
                )
            # index.html names the hashed asset files, so it must never be served from a browser cache
            return FileResponse(_dist / "index.html", headers={"Cache-Control": "no-cache"})

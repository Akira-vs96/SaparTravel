"""Serve a built SPA without turning missing API routes into HTML responses."""
import os
from pathlib import Path
import re

from fastapi.responses import FileResponse, JSONResponse
from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles


class FrontendFiles(StaticFiles):
    async def get_response(self, path, scope):
        parts = Path(path).parts
        if parts and (parts[0] == "api" or ".." in parts):
            raise HTTPException(status_code=404)
        try:
            response = await super().get_response(path, scope)
        except HTTPException as error:
            # BrowserRouter needs index.html for page routes, but missing scripts,
            # images and styles must stay 404 (never a misleading HTTP 200 HTML).
            if error.status_code != 404 or (parts and (parts[0] == "assets" or "." in parts[-1])):
                raise
            response = FileResponse(Path(self.directory) / "index.html")
        response.headers["Cache-Control"] = (
            "public, max-age=31536000, immutable"
            if re.search(r"-[A-Za-z0-9_-]{8,}\.[a-z0-9]+$", path) else "no-cache"
        )
        return response


def attach_frontend(app, directory):
    directory = Path(directory)
    if not (directory / "index.html").is_file():
        raise RuntimeError("Build the frontend before starting the public application")

    @app.get("/api/v1/release", include_in_schema=False)
    def release():
        return JSONResponse({"commit": os.environ.get("RENDER_GIT_COMMIT", "local"), "frontend": True},
                            headers={"Cache-Control": "no-store"})

    app.mount("/", FrontendFiles(directory=directory), name="frontend")


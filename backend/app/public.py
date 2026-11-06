"""Same-origin frontend and API entry point for the single Free web service."""
import os

from app.main import app
from app.web import attach_frontend

attach_frontend(app, os.environ.get("FRONTEND_DIST", "/app/web"))


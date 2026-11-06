from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.web import attach_frontend


@pytest.fixture
def public_client(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text('<html><div id="root">SaparTravel</div></html>')
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "index-12345678.js").write_text("console.log('loaded')")
    app = FastAPI()

    @app.get("/api/v1/health")
    def health():
        return {"status": "ok"}

    monkeypatch.setenv("RENDER_GIT_COMMIT", "a" * 40)
    attach_frontend(app, tmp_path)
    with TestClient(app) as client:
        yield client


@pytest.mark.parametrize("path", ["/", "/forgot-password", "/bookings/123", "/profile/"])
def test_spa_navigation_survives_refresh(public_client, path):
    response = public_client.get(path)
    assert response.status_code == 200
    assert 'id="root"' in response.text
    assert response.headers["cache-control"] == "no-cache"


@pytest.mark.parametrize("path", ["/api", "/api/v1/no-such-endpoint", "/assets/missing.js", "/missing.png"])
def test_missing_api_and_assets_are_not_spa_html(public_client, path):
    response = public_client.get(path)
    assert response.status_code == 404
    assert 'id="root"' not in response.text


def test_assets_and_exact_release_proof(public_client):
    assert public_client.get("/api/v1/health").json() == {"status": "ok"}
    assert public_client.get("/api/v1/release").json() == {"commit": "a" * 40, "frontend": True}
    assert "/api/v1/release" not in public_client.get("/openapi.json").json()["paths"]
    asset = public_client.get("/assets/index-12345678.js")
    assert "immutable" in asset.headers["cache-control"]
    assert "console.log" in asset.text


def test_public_start_requires_built_frontend(tmp_path):
    with pytest.raises(RuntimeError, match="Build the frontend"):
        attach_frontend(FastAPI(), tmp_path)


def test_worker_exit_stops_the_api_sibling(monkeypatch):
    import subprocess
    import sys
    from app.public_start import supervise

    launched = []
    real_popen = subprocess.Popen

    def track(command):
        process = real_popen(command)
        launched.append(process)
        return process

    monkeypatch.setattr(subprocess, "Popen", track)
    code = supervise([[sys.executable, "-c", "import sys; sys.exit(7)"],
                      [sys.executable, "-c", "import time; time.sleep(60)"]])
    assert code == 7
    assert len(launched) == 2
    assert all(child.poll() is not None for child in launched)

"""One acceptance-only SLI-A observation. No registration or payment requests.

Run as a process once per minute from an external host. Browser mode needs Playwright.
The safety manifest must be deployed separately on an isolated acceptance host.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import signal
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

SCENARIO_VERSION = "sli-a-v2"
STEPS = ("isolation", "web", "catalog", "tour", "login", "create", "cancel")
HTTP_LIMIT = 2.0
SCENARIO_LIMIT = 10.0
MAX_BODY = 2_000_000


class ProbeFailure(Exception):
    """Only fixed, non-sensitive error codes may be persisted."""


def identifier(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", value):
        raise ValueError("invalid identifier")
    return value


def base_url(value: str) -> str:
    parsed = urlsplit(value)
    if (parsed.scheme not in ("http", "https") or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in ("", "/")):
        raise ValueError("expected HTTP(S) origin without credentials, path or query")
    return value.rstrip("/")


@dataclass(frozen=True)
class Config:
    point: str
    deployment_id: str
    origin: str
    tour_slug: str
    departure_id: str
    scope: str = "acceptance-only"
    browser: bool = False

    def __post_init__(self):
        for value in (self.point, self.deployment_id, self.tour_slug, self.departure_id):
            identifier(value)
        base_url(self.origin)
        if self.scope not in {"acceptance-only", "operational"}:
            raise ValueError("unsupported monitoring scope")
        if type(self.browser) is not bool:
            raise ValueError("browser must be boolean")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@contextmanager
def hard_timeout(seconds: float):
    """Bound the complete response, including a slow trickle, on POSIX main thread."""
    def expired(signum, frame):
        raise ProbeFailure("timeout")

    previous_handler = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


def request(method: str, url: str, payload: dict | None, token: str | None,
            timeout: float) -> tuple[int, str, bytes]:
    headers = {"Accept": "application/json, text/html", "User-Agent": SCENARIO_VERSION}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    req = Request(url, data=json.dumps(payload).encode() if payload is not None else None,
                  headers=headers, method=method)
    try:
        with hard_timeout(timeout):
            with build_opener(NoRedirect).open(req, timeout=timeout) as response:
                body = response.read(MAX_BODY + 1)
                if len(body) > MAX_BODY:
                    raise ProbeFailure("body_too_large")
                return response.status, response.headers.get("Content-Type", ""), body
    except HTTPError as error:
        # Do not read, log or return server error text or redirect URLs.
        status = error.code
        error.close()
        return status, "", b""
    except (URLError, OSError):
        raise ProbeFailure("network_error") from None


@contextmanager
def prepared_browser():
    """Prepare the measurement instrument before timing the user scenario."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise ProbeFailure("browser_unavailable") from None
    playwright = browser = None
    try:
        try:
            playwright = sync_playwright().start()
            browser = playwright.chromium.launch(headless=True, timeout=5000)
            page = browser.new_page()
        except Exception:
            raise ProbeFailure("browser_error") from None
        yield page
    finally:
        # Cleanup must never repeat a scenario which may already have created a booking.
        for close in (browser.close if browser else None, playwright.stop if playwright else None):
            if close:
                try:
                    close()
                except Exception:
                    pass


def browser_request(url: str, timeout: float, *, page=None) -> tuple[int, str, bytes]:
    """Time navigation and React rendering; tool startup/teardown is outside HTTP time."""
    if page is None:
        with prepared_browser() as prepared:
            return browser_request(url, timeout, page=prepared)
    started = time.monotonic()
    failed = []
    origin = urlsplit(url).netloc

    def remaining():
        seconds = timeout - (time.monotonic() - started)
        if seconds <= 0:
            raise ProbeFailure("browser_timeout")
        return seconds * 1000

    try:
        page.on("pageerror", lambda error: failed.append("javascript_error"))

        def check(response):
            parsed = urlsplit(response.url)
            if parsed.netloc == origin and parsed.path.startswith(("/assets/", "/api/")):
                if response.status >= 400:
                    failed.append("resource_error")

        page.on("response", check)
        response = page.goto(url, wait_until="domcontentloaded", timeout=remaining())
        page.locator("#root main").wait_for(state="visible", timeout=remaining())
        # Wait for the catalog content rather than accepting the React loading shell.
        page.locator("#root .tour-card").first.wait_for(state="visible", timeout=remaining())
        if failed or response is None or response.request.redirected_from is not None:
            raise ProbeFailure("browser_content_error")
        return response.status, "text/html", page.content().encode()
    except ProbeFailure:
        raise
    except Exception:
        # Browser exceptions can include URLs/tokens; only a fixed code enters evidence.
        raise ProbeFailure("browser_error") from None


def run_probe(config: Config, email: str, password: str, *, transport=request,
              clock=time.monotonic, now=None) -> dict:
    if transport is request and (config.browser or config.scope == "operational"):
        try:
            with prepared_browser() as page:
                return _run_probe(config, email, password, transport=transport, clock=clock, now=now,
                                  browser_page=page)
        except ProbeFailure as error:
            return _run_probe(config, email, password, transport=transport, clock=clock, now=now,
                              browser_failure=str(error))
    return _run_probe(config, email, password, transport=transport, clock=clock, now=now)


def _run_probe(config: Config, email: str, password: str, *, transport=request,
               clock=time.monotonic, now=None, browser_page=None, browser_failure=None) -> dict:
    started = clock()
    result = {"timestamp_utc": (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(),
              "point": config.point, "deployment_id": config.deployment_id,
              "scope": config.scope, "scenario_version": SCENARIO_VERSION,
              "success": False, "steps": [], "duration_ms": 0.0}
    token = None
    booking_id = None

    def step(name, method, path, expected, validate, payload=None, authenticated=False):
        step_started = clock()
        entry = {"name": name, "success": False, "duration_ms": 0.0, "status_code": None}
        result["steps"].append(entry)
        try:
            remaining = SCENARIO_LIMIT - (step_started - started)
            if remaining <= 0:
                raise ProbeFailure("scenario_timeout")
            if name == "web" and transport is request and (config.browser or config.scope == "operational"):
                if browser_failure:
                    raise ProbeFailure(browser_failure)
                status, content_type, body = browser_request(config.origin + path, min(HTTP_LIMIT, remaining),
                                                          page=browser_page)
            else:
                status, content_type, body = transport(method, config.origin + path, payload,
                                                      token if authenticated else None,
                                                      min(HTTP_LIMIT, remaining))
            entry["status_code"] = status
            if status != expected:
                raise ProbeFailure("unexpected_status")
            if name == "web":
                data = body.decode("utf-8")
                if "text/html" not in content_type:
                    raise ProbeFailure("unexpected_content")
            else:
                if "application/json" not in content_type:
                    raise ProbeFailure("unexpected_content")
                data = json.loads(body)
            if not validate(data):
                raise ProbeFailure("unexpected_content")
            elapsed = clock() - step_started
            if elapsed > HTTP_LIMIT:
                raise ProbeFailure("http_timeout")
            if clock() - started > SCENARIO_LIMIT:
                raise ProbeFailure("scenario_timeout")
            entry["success"] = True
            return data
        except ProbeFailure as error:
            entry["error"] = str(error)
            raise
        except (ValueError, TypeError, KeyError, AttributeError):
            entry["error"] = "unexpected_content"
            raise ProbeFailure("unexpected_content") from None
        finally:
            entry["duration_ms"] = round((clock() - step_started) * 1000, 3)

    try:
        if not email or not password:
            raise ProbeFailure("missing_credentials")
        manifest = {"scope": config.scope, "deployment_id": config.deployment_id,
                    "origin": config.origin, "tour_slug": config.tour_slug,
                    "departure_id": config.departure_id, "isolated_database": config.scope == "acceptance-only"}
        if config.scope == "operational":
            manifest.update(synthetic_fixture=True, exclude_from_analytics=True)
        step("isolation", "GET", "/.well-known/sapartravel-monitoring.json", 200, lambda data: data == manifest)
        step("web", "GET", "/", 200,
             lambda html: "SaparTravel" in html and 'id="root"' in html
             and 'type="module"' in html)
        step("catalog", "GET", "/api/v1/catalog?page_size=100", 200,
             lambda data: isinstance(data["items"], list) and data["total"] >= 1
             and len(data["items"]) > 0 and all("slug" in item for item in data["items"]))
        step("tour", "GET", "/api/v1/experiences/" + quote(config.tour_slug, safe=""), 200,
             lambda data: data["slug"] == config.tour_slug
             and any(item["id"] == config.departure_id and item["status"] == "scheduled"
                     and item["available_seats"] >= 1 for item in data["departures"]))
        login = step("login", "POST", "/api/v1/auth/login", 200,
                     lambda data: isinstance(data["access_token"], str) and bool(data["access_token"])
                     and data["token_type"] == "bearer" and data["user"]["role"] == "traveler"
                     and data["user"]["email"].casefold() == email.casefold(),
                     {"email": email, "password": password})
        token = login["access_token"]
        booking = step("create", "POST", "/api/v1/bookings", 201,
                       lambda data: isinstance(data["id"], str) and bool(data["id"])
                       and data["departure_id"] == config.departure_id
                       and data["status"] == "pending" and data["travelers_count"] == 1,
                       {"departure_id": config.departure_id, "travelers_count": 1,
                        "contact_name": "SLI acceptance probe", "contact_email": email,
                        "notes": "SLI-A isolated acceptance fixture", "accept_cancellation_policy": True}, True)
        booking_id = booking["id"]
        step("cancel", "POST", "/api/v1/bookings/" + quote(booking_id, safe="") + "/cancel", 200,
             lambda data: data["id"] == booking_id and data["status"] == "cancelled",
             {"reason": "SLI-A isolated acceptance fixture"}, True)
        result["success"] = clock() - started <= SCENARIO_LIMIT
    except ProbeFailure:
        pass
    finally:
        result["duration_ms"] = round((clock() - started) * 1000, 3)
        if len(result["steps"]) < len(STEPS):
            completed = {entry["name"] for entry in result["steps"]}
            for name in STEPS:
                if name not in completed:
                    result["steps"].append({"name": name, "success": False, "duration_ms": 0.0,
                                            "status_code": None, "error": "not_run"})
    # A timed-out POST might already have committed. Never retry create. The isolated
    # acceptance operator must inspect/reconcile pending reservations after a failure.
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        config = Config(**json.loads(args.config.read_text()))
        result = run_probe(config, os.environ.get("SLI_EMAIL", ""), os.environ.get("SLI_PASSWORD", ""))
        # O_APPEND prevents truncating existing evidence; credentials and bodies never persist.
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a") as stream:
            stream.write(json.dumps(result, ensure_ascii=False, allow_nan=False) + "\n")
        return 0 if result["success"] else 1
    except (OSError, ValueError, TypeError):
        print("Invalid configuration or evidence output; no details logged.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

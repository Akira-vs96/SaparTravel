"""External HTTP acceptance probe for SLI-L; no application imports or DB access."""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import math
from pathlib import Path
import platform
import sys
import time
from urllib.parse import urlsplit

import httpx

TOURS = 500
PAGE_SIZE = 12
PAGES = math.ceil(TOURS / PAGE_SIZE)


@dataclass(frozen=True)
class Profile:
    rps: int = 20
    duration_seconds: float = 600
    warmup_seconds: float = 120
    timeout_seconds: float = 5
    max_in_flight: int = 100
    threshold_ms: float = 500

    def __post_init__(self):
        if self.rps < 1 or self.max_in_flight < 1:
            raise ValueError("RPS and max_in_flight must be positive")
        if not all(math.isfinite(x) for x in (
            self.duration_seconds, self.warmup_seconds, self.timeout_seconds, self.threshold_ms,
        )) or min(self.duration_seconds, self.timeout_seconds, self.threshold_ms) <= 0 or self.warmup_seconds < 0:
            raise ValueError("Durations and threshold must be finite and positive; warmup may be zero")

    @property
    def acceptance_profile(self) -> bool:
        return (self.rps, self.duration_seconds, self.warmup_seconds, self.threshold_ms) == (20, 600, 120, 500)


@dataclass(frozen=True)
class Outcome:
    index: int
    latency_ms: float | None
    scheduling_delay_ms: float
    error: str | None = None
    status_code: int | None = None


def planned_count(seconds: float, rps: int) -> int:
    """Slots are [0, duration), independent of response completion times."""
    return math.ceil(Decimal(str(seconds)) * rps)


def slot_offset(index: int, rps: int) -> float:
    return index / rps


def request_params(index: int) -> dict:
    return {"page": index % PAGES + 1, "page_size": PAGE_SIZE, "lang": ("ru", "kk", "en")[index % 3]}


def valid_catalog(body: object, page: int) -> bool:
    if not isinstance(body, dict):
        return False
    if any(body.get(key) != expected for key, expected in (
        ("total", TOURS), ("page", page), ("page_size", PAGE_SIZE), ("pages", PAGES),
    )):
        return False
    items = body.get("items")
    expected_count = min(PAGE_SIZE, max(0, TOURS - (page - 1) * PAGE_SIZE))
    if not isinstance(items, list) or len(items) != expected_count:
        return False
    ids = set()
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"]:
            return False
        if item["id"] in ids:
            return False
        ids.add(item["id"])
        if not isinstance(item.get("slug"), str) or not item["slug"].startswith("catalog-load-"):
            return False
        if item.get("currency") != "KZT" or not isinstance(item.get("title"), str) or not item["title"]:
            return False
        try:
            price = Decimal(str(item.get("price_from")))
            if not price.is_finite() or price <= 0:
                return False
        except InvalidOperation:
            return False
    return True


def percentile95(values: list[float]) -> float | None:
    """Nearest rank: at least 95% of the observed values are <= this value."""
    return sorted(values)[math.ceil(len(values) * 0.95) - 1] if values else None


def summarize(outcomes: list[Outcome], planned: int, duration: float, threshold_ms: float) -> dict:
    indexes = [item.index for item in outcomes]
    duplicates = len(indexes) - len(set(indexes))
    observed = len({index for index in indexes if 0 <= index < planned})
    missing = planned - observed
    invalid_indexes = sum(not 0 <= index < planned for index in indexes)
    errors = Counter(item.error for item in outcomes if item.error)
    latencies = [item.latency_ms for item in outcomes if item.latency_ms is not None]
    executed = len(latencies)
    p95 = percentile95(latencies)
    passed = (
        planned > 0 and observed == planned and not duplicates and not invalid_indexes and not errors
        and executed == planned and p95 is not None and p95 <= threshold_ms
    )
    return {
        "planned": planned, "executed": executed, "successful": sum(item.error is None for item in outcomes),
        "missing": missing, "duplicates": duplicates, "invalid_indexes": invalid_indexes,
        "dropped": errors.get("scheduling_late", 0) + errors.get("concurrency_limit", 0),
        "errors": dict(sorted(errors.items())),
        "error_percent": round(100 * (sum(errors.values()) + missing) / planned, 6) if planned else None,
        "timeouts": errors.get("timeout", 0), "dispatched_rps": executed / duration if duration else 0,
        "p95_ms": p95, "max_ms": max(latencies) if latencies else None,
        "max_scheduling_delay_ms": max((item.scheduling_delay_ms for item in outcomes), default=0),
        "status_codes": dict(sorted(Counter(str(item.status_code) for item in outcomes if item.status_code is not None).items())),
        "passed": passed,
    }


async def measure_request(client: httpx.AsyncClient, endpoint: str, index: int, delay_ms: float) -> Outcome:
    started = time.perf_counter()
    try:
        params = request_params(index)
        response = await client.get(endpoint, params=params)
        elapsed = (time.perf_counter() - started) * 1000
        error = None
        if response.status_code != 200:
            error = "http_status"
        else:
            try:
                if not valid_catalog(response.json(), params["page"]):
                    error = "invalid_content"
            except (ValueError, TypeError):
                error = "invalid_json"
        return Outcome(index, elapsed, delay_ms, error, response.status_code)
    except httpx.TimeoutException:
        return Outcome(index, (time.perf_counter() - started) * 1000, delay_ms, "timeout")
    except httpx.RequestError:
        return Outcome(index, (time.perf_counter() - started) * 1000, delay_ms, "transport_error")


async def run_phase(client: httpx.AsyncClient, endpoint: str, profile: Profile, duration: float) -> list[Outcome]:
    """Open loop: overdue or saturated slots fail; never lower the offered load."""
    outcomes: list[Outcome] = []
    in_flight: set[asyncio.Task] = set()
    loop = asyncio.get_running_loop()
    started = loop.time()

    async def perform(index: int, delay_ms: float):
        outcomes.append(await measure_request(client, endpoint, index, delay_ms))

    for index in range(planned_count(duration, profile.rps)):
        target = started + slot_offset(index, profile.rps)
        remaining = target - loop.time()
        if remaining > 0:
            await asyncio.sleep(remaining)
        delay = max(0, loop.time() - target)
        if delay >= 1 / profile.rps:
            outcomes.append(Outcome(index, None, delay * 1000, "scheduling_late"))
        elif len(in_flight) >= profile.max_in_flight:
            outcomes.append(Outcome(index, None, delay * 1000, "concurrency_limit"))
        else:
            task = asyncio.create_task(perform(index, delay * 1000))
            in_flight.add(task)
            task.add_done_callback(in_flight.discard)
    # Keep the full warmup/measurement window, including its final partial interval.
    remaining = started + duration - loop.time()
    if remaining > 0:
        await asyncio.sleep(remaining)
    if in_flight:
        await asyncio.gather(*in_flight)
    return outcomes


async def preflight(client: httpx.AsyncClient, endpoint: str) -> None:
    seen_ids, seen_slugs = set(), set()
    for page in range(1, PAGES + 1):
        response = await client.get(endpoint, params={"page": page, "page_size": PAGE_SIZE, "lang": "ru"})
        if response.status_code != 200 or not valid_catalog(response.json(), page):
            raise ValueError("Preflight requires a valid 500-tour prepared catalog on every page")
        for item in response.json()["items"]:
            seen_ids.add(item["id"])
            seen_slugs.add(item["slug"])
    if len(seen_ids) != TOURS or seen_slugs != {f"catalog-load-{index:04d}" for index in range(TOURS)}:
        raise ValueError("Preflight found duplicated, missing or unexpected fixture tours")


async def run(endpoint: str, profile: Profile, stand: dict) -> dict:
    report = {
        "schema_version": 1, "scenario": "SLI-L", "endpoint": endpoint,
        "started_at_utc": datetime.now(timezone.utc).isoformat(), "profile": asdict(profile),
        "acceptance_profile": profile.acceptance_profile, "stand": stand,
        "client": {"python": platform.python_version(), "platform": platform.platform(), "httpx": httpx.__version__},
        "latency_definition": "HTTP send through complete response body; nearest-rank p95; warmup excluded",
        "schedule_lateness_limit_ms": 1000 / profile.rps,
        "passed": False, "accepted": False,
    }
    limits = httpx.Limits(max_connections=profile.max_in_flight, max_keepalive_connections=profile.max_in_flight)
    # Explicit network transport; ASGI/TestClient transport is never used. No env proxies.
    async with httpx.AsyncClient(timeout=profile.timeout_seconds, limits=limits, trust_env=False, follow_redirects=False) as client:
        try:
            await preflight(client, endpoint)
        except (ValueError, httpx.RequestError):
            report["failure"] = "preflight_failed"
            report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
            return report
        print(f"Warmup: {profile.warmup_seconds:g}s at {profile.rps} RPS", file=sys.stderr, flush=True)
        warm = await run_phase(client, endpoint, profile, profile.warmup_seconds)
        report["warmup"] = summarize(warm, planned_count(profile.warmup_seconds, profile.rps), profile.warmup_seconds, profile.threshold_ms)
        print(f"Measurement: {profile.duration_seconds:g}s at {profile.rps} RPS", file=sys.stderr, flush=True)
        samples = await run_phase(client, endpoint, profile, profile.duration_seconds)
        report["measurement"] = summarize(samples, planned_count(profile.duration_seconds, profile.rps), profile.duration_seconds, profile.threshold_ms)
    # Warmup latency is excluded from the SLI; warmup errors or missed load still invalidate the run.
    warm_ok = not warm or (not report["warmup"]["errors"] and not report["warmup"]["missing"]
                          and report["warmup"]["executed"] == report["warmup"]["planned"])
    report["passed"] = bool(report["measurement"]["passed"] and warm_ok)
    report["accepted"] = report["passed"] and profile.acceptance_profile
    report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:18000")
    parser.add_argument("--stand-config", type=Path, required=True, help="JSON object describing the measured API/DB/client resources; no secrets")
    parser.add_argument("--output", type=Path, default=Path("test-results/catalog-load.json"))
    parser.add_argument("--rps", type=int, default=20)
    parser.add_argument("--duration", type=float, default=600)
    parser.add_argument("--warmup", type=float, default=120)
    parser.add_argument("--timeout", type=float, default=5)
    parser.add_argument("--max-in-flight", type=int, default=100)
    args = parser.parse_args()
    try:
        profile = Profile(args.rps, args.duration, args.warmup, args.timeout, args.max_in_flight)
        parsed = urlsplit(args.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("base-url must be an HTTP(S) origin without credentials, query or fragment")
        if parsed.path not in {"", "/"}:
            raise ValueError("base-url must not contain a path")
        stand = json.loads(args.stand_config.read_text(encoding="utf-8"))
        if not isinstance(stand, dict) or not stand:
            raise ValueError("stand-config must be a non-empty JSON object")
        report = asyncio.run(run(args.base_url.rstrip("/") + "/api/v1/catalog", profile, stand))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"passed": report["passed"], "accepted": report["accepted"], "report": str(args.output)}))
        return 0 if report["passed"] else 1
    except (ValueError, OSError) as error:
        print(f"Invalid load configuration: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

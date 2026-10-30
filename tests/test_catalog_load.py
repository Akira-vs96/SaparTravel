"""Planning, HTTP validation and failure accounting without an application DB."""
import asyncio
from dataclasses import replace
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, patch

import httpx


def load_script(name):
    path = Path(__file__).resolve().parents[1] / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


load = load_script("catalog_load")
prepare = load_script("prepare_catalog_load")


def response_body(page=1):
    first = (page - 1) * load.PAGE_SIZE
    return {"page": page, "pages": load.PAGES, "page_size": load.PAGE_SIZE, "total": 500,
            "items": [{"id": f"tour-{index}", "slug": f"catalog-load-{index:04d}",
                       "currency": "KZT", "title": f"Tour {index}", "price_from": "50000.00"}
                      for index in range(first, min(500, first + load.PAGE_SIZE))]}


class ScheduleTests(unittest.TestCase):
    def test_acceptance_profile_has_12000_measurements_and_2400_warmup_slots(self):
        profile = load.Profile()
        self.assertEqual(load.planned_count(profile.duration_seconds, profile.rps), 12000)
        self.assertEqual(load.planned_count(profile.warmup_seconds, profile.rps), 2400)
        self.assertEqual(load.slot_offset(11999, 20), 599.95)
        self.assertTrue(profile.acceptance_profile)
        self.assertFalse(replace(profile, duration_seconds=1).acceptance_profile)

    def test_fractional_window_does_not_lose_last_slot_or_accumulate_rounding(self):
        self.assertEqual(load.planned_count(0.15, 20), 3)
        self.assertEqual(load.planned_count(0.151, 20), 4)
        self.assertEqual(load.planned_count(0, 20), 0)
        self.assertEqual(load.slot_offset(10000, 20), 500)

    def test_invalid_profiles_are_rejected(self):
        for values in ({"rps": 0}, {"duration_seconds": 0}, {"warmup_seconds": -1},
                       {"duration_seconds": float("inf")}, {"timeout_seconds": float("nan")},
                       {"max_in_flight": 0}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                load.Profile(**values)


class AccountingTests(unittest.TestCase):
    def test_nearest_rank_boundary_accepts_95_percent_at_threshold(self):
        outcomes = [load.Outcome(i, 500 if i < 95 else 900, 0) for i in range(100)]
        report = load.summarize(outcomes, 100, 5, 500)
        self.assertTrue(report["passed"])
        self.assertEqual(report["p95_ms"], 500)
        outcomes[94] = load.Outcome(94, 501, 0)
        self.assertFalse(load.summarize(outcomes, 100, 5, 500)["passed"])

    def test_low_latency_cannot_hide_missing_failed_or_dropped_requests(self):
        good = [load.Outcome(i, 1, 0) for i in range(20)]
        cases = [good[:-1]]
        for reason in ("timeout", "transport_error", "http_status", "invalid_content", "invalid_json"):
            cases.append(good[:-1] + [load.Outcome(19, 1, 0, reason)])
        for reason in ("scheduling_late", "concurrency_limit"):
            cases.append(good[:-1] + [load.Outcome(19, None, 51, reason)])
        cases.extend([good[:-1] + [good[0]], good + [load.Outcome(20, 1, 0)], []])
        for outcomes in cases:
            with self.subTest(outcomes=outcomes):
                self.assertFalse(load.summarize(outcomes, 20, 1, 500)["passed"])
        report = load.summarize(good[:-1], 20, 1, 500)
        self.assertEqual((report["missing"], report["error_percent"]), (1, 5))

    def test_timeout_is_executed_and_counted_as_error(self):
        report = load.summarize([load.Outcome(0, 5001, 0, "timeout")], 1, 1, 500)
        self.assertEqual((report["executed"], report["timeouts"], report["error_percent"]), (1, 1, 100))


class ContentTests(unittest.TestCase):
    def test_first_and_last_page_validate(self):
        self.assertTrue(load.valid_catalog(response_body(), 1))
        self.assertTrue(load.valid_catalog(response_body(42), 42))
        self.assertEqual(len(response_body(42)["items"]), 8)

    def test_200_with_incorrect_content_fails(self):
        for change in ({"total": 24}, {"items": []}, {"pages": 1}, {"page": 2}):
            with self.subTest(change=change):
                self.assertFalse(load.valid_catalog({**response_body(), **change}, 1))
        for change in ({"currency": "USD"}, {"price_from": "NaN"}, {"slug": "working-tour"}, {"title": ""}):
            body = response_body()
            body["items"][0].update(change)
            self.assertFalse(load.valid_catalog(body, 1))


class DatabaseGuardTests(unittest.TestCase):
    def test_implicit_or_non_test_database_and_redirect_options_are_rejected(self):
        for url in (None, "sqlite:///catalog_test", "postgresql://localhost/sapartravel",
                    "postgresql://localhost/test?service=production", "postgresql://localhost/sapar_test?dbname=production"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                prepare.test_database_url(url)
        self.assertEqual(prepare.test_database_url("postgresql://localhost/catalog_test"),
                         "postgresql+psycopg://localhost/catalog_test")

    def test_fixture_is_500_distinct_tours_and_preserves_source(self):
        source = {"destinations": [{"slug": "almaty"}], "experiences": [
            {"slug": "source", "title": "Tour", "title_en": "Trip", "title_kk": "Саяхат", "price_from": 50000},
        ]}
        payload = prepare.build_payload(source)
        self.assertEqual(len(payload["experiences"]), 500)
        self.assertEqual(len({item["slug"] for item in payload["experiences"]}), 500)
        self.assertTrue(all(len(item["departures"]) == 3 for item in payload["experiences"]))
        self.assertEqual(source["experiences"][0]["slug"], "source")
        self.assertNotIn("departures", source["experiences"][0])


class AsyncProbeTests(unittest.IsolatedAsyncioTestCase):
    async def test_short_successful_run_never_claims_acceptance(self):
        profile = load.Profile(duration_seconds=1, warmup_seconds=0)
        measured = [load.Outcome(index, 1, 0) for index in range(20)]
        with patch.object(load, "preflight", AsyncMock()), patch.object(load, "run_phase", AsyncMock(side_effect=[[], measured])):
            report = await load.run("http://test/catalog", profile, {"description": "unit test"})
        self.assertTrue(report["passed"])
        self.assertFalse(report["acceptance_profile"])
        self.assertFalse(report["accepted"])

    async def test_warmup_errors_fail_an_otherwise_successful_measurement(self):
        profile = load.Profile(duration_seconds=1, warmup_seconds=1)
        measured = [load.Outcome(index, 1, 0) for index in range(20)]
        warmup = measured[:-1] + [load.Outcome(19, 5001, 0, "timeout")]
        with patch.object(load, "preflight", AsyncMock()), patch.object(load, "run_phase", AsyncMock(side_effect=[warmup, measured])):
            report = await load.run("http://test/catalog", profile, {"description": "unit test"})
        self.assertTrue(report["measurement"]["passed"])
        self.assertFalse(report["passed"])
        self.assertFalse(report["accepted"])

    async def test_bad_status_content_and_timeout_are_reported(self):
        responses = [httpx.Response(503), httpx.Response(200, json={"items": []}),
                     httpx.Response(200, text="<html>error</html>")]
        for response, reason in zip(responses, ("http_status", "invalid_content", "invalid_json")):
            with self.subTest(reason=reason):
                async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: response)) as client:
                    result = await load.measure_request(client, "http://test/catalog", 0, 0)
                    self.assertEqual(result.error, reason)

        def timeout(request):
            raise httpx.ReadTimeout("test timeout")

        async with httpx.AsyncClient(transport=httpx.MockTransport(timeout)) as client:
            result = await load.measure_request(client, "http://test/catalog", 0, 0)
            self.assertEqual(result.error, "timeout")

    async def test_preflight_detects_cross_page_duplicates(self):
        def handler(request):
            page = int(request.url.params["page"])
            body = response_body(page)
            if page == 42:
                body["items"][0]["id"] = "tour-0"
            return httpx.Response(200, json=body)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaises(ValueError):
                await load.preflight(client, "http://test/catalog")

    async def test_saturated_client_drops_slots_instead_of_serializing_load(self):
        async def slow(client, endpoint, index, delay):
            await asyncio.sleep(0.15)
            return load.Outcome(index, 150, delay)

        profile = load.Profile(rps=50, duration_seconds=0.1, warmup_seconds=0, max_in_flight=1)
        with patch.object(load, "measure_request", slow):
            results = await load.run_phase(None, "http://test/catalog", profile, 0.1)
        report = load.summarize(results, 5, 0.1, 500)
        self.assertEqual(report["planned"], 5)
        self.assertEqual(report["executed"], 1)
        self.assertEqual(report["dropped"], 4)
        self.assertFalse(report["passed"])

    async def test_delayed_scheduler_does_not_burst_overdue_requests(self):
        async def blocks_loop(client, endpoint, index, delay):
            # Simulates a stalled client event loop, independently of service latency.
            load.time.sleep(0.06)
            return load.Outcome(index, 1, delay)

        profile = load.Profile(rps=100, duration_seconds=0.05, warmup_seconds=0)
        with patch.object(load, "measure_request", blocks_loop):
            results = await load.run_phase(None, "http://test/catalog", profile, 0.05)
        report = load.summarize(results, 5, 0.05, 500)
        self.assertEqual(report["errors"]["scheduling_late"], 4)
        self.assertFalse(report["passed"])


if __name__ == "__main__":
    unittest.main()

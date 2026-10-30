"""SLI-A behavior checks without production credentials or business database access."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request

from scripts.availability_probe import Config, NoRedirect, ProbeFailure, request, run_probe
from scripts.availability_report import aggregate, month_window


CONFIG = Config("point-a", "acceptance-1", "https://acceptance.invalid", "sli-tour", "departure-1")
EMAIL = "sli@example.invalid"
PASSWORD = "never-persist-this-password"
POINTS = ["point-a", "point-b", "point-c"]
NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)


class FakeTransport:
    def __init__(self, *, fail=None, invalid=None, durations=None):
        self.calls = []
        self.elapsed = 0.0
        self.fail = fail
        self.invalid = invalid
        self.durations = durations or {}

    def clock(self):
        return self.elapsed

    def __call__(self, method, url, payload, token, timeout):
        index = len(self.calls)
        name = ("isolation", "web", "catalog", "tour", "login", "create", "cancel")[index]
        self.calls.append((method, url, payload, token, timeout))
        self.elapsed += self.durations.get(name, 0.1)
        if self.fail == name:
            raise ProbeFailure("network_error")
        responses = {
            "isolation": {"scope": "acceptance-only", "deployment_id": "acceptance-1",
                          "origin": CONFIG.origin, "tour_slug": CONFIG.tour_slug,
                          "departure_id": CONFIG.departure_id, "isolated_database": True},
            "web": '<html><title>SaparTravel</title><div id="root"></div><script type="module"></script></html>',
            "catalog": {"items": [{"slug": "sli-tour"}], "total": 1},
            "tour": {"slug": "sli-tour", "departures": [{"id": "departure-1", "status": "scheduled", "available_seats": 3}]},
            "login": {"access_token": "never-persist-this-token", "token_type": "bearer", "user": {"email": EMAIL, "role": "traveler"}},
            "create": {"id": "booking-1", "status": "pending", "departure_id": "departure-1", "travelers_count": 1},
            "cancel": {"id": "booking-1", "status": "cancelled"},
        }
        data = {} if self.invalid == name else responses[name]
        body = data.encode() if isinstance(data, str) else json.dumps(data).encode()
        return 201 if name == "create" else 200, "text/html" if name == "web" else "application/json", body


def observation(point="point-a", timestamp="2026-09-30T19:00:01+00:00"):
    transport = FakeTransport()
    record = run_probe(CONFIG, EMAIL, PASSWORD, transport=transport, clock=transport.clock)
    record["point"] = point
    record["timestamp_utc"] = timestamp
    return record


class ProbeTests(unittest.TestCase):
    def test_real_contract_and_credentials_never_persist(self):
        fake = FakeTransport()
        result = run_probe(CONFIG, EMAIL, PASSWORD, transport=fake, clock=fake.clock)
        self.assertTrue(result["success"])
        self.assertEqual(fake.calls[-1][1], CONFIG.origin + "/api/v1/bookings/booking-1/cancel")
        self.assertEqual(fake.calls[-2][2]["departure_id"], CONFIG.departure_id)
        self.assertTrue(all(call[3] is None for call in fake.calls[:5]))
        serialized = json.dumps(result)
        for sensitive in (EMAIL, PASSWORD, "never-persist-this-token", "booking-1"):
            self.assertNotIn(sensitive, serialized)
        self.assertEqual(result["duration_ms"], 700.0)
        self.assertEqual(len(result["steps"]), 7)

    def test_missing_safety_manifest_stops_before_login_or_write(self):
        fake = FakeTransport(invalid="isolation")
        result = run_probe(CONFIG, EMAIL, PASSWORD, transport=fake, clock=fake.clock)
        self.assertFalse(result["success"])
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(result["steps"][0]["error"], "unexpected_content")

    def test_status_200_with_invalid_content_is_failure_at_each_stage(self):
        for name in ("catalog", "tour", "login", "create", "cancel"):
            with self.subTest(name=name):
                fake = FakeTransport(invalid=name)
                result = run_probe(CONFIG, EMAIL, PASSWORD, transport=fake, clock=fake.clock)
                self.assertFalse(result["success"])
                self.assertEqual(next(step for step in result["steps"] if step["name"] == name)["error"], "unexpected_content")

    def test_missing_credentials_make_no_requests(self):
        fake = FakeTransport()
        result = run_probe(CONFIG, "", "", transport=fake, clock=fake.clock)
        self.assertFalse(result["success"])
        self.assertEqual(fake.calls, [])

    def test_request_limit_is_enforced_even_with_success_response(self):
        fake = FakeTransport(durations={"catalog": 2.001})
        result = run_probe(CONFIG, EMAIL, PASSWORD, transport=fake, clock=fake.clock)
        self.assertFalse(result["success"])
        self.assertEqual(result["steps"][2]["error"], "http_timeout")

    def test_remaining_total_deadline_is_passed_to_last_request(self):
        fake = FakeTransport(durations={name: 1.5 for name in ("isolation", "web", "catalog", "tour", "login", "create", "cancel")})
        result = run_probe(CONFIG, EMAIL, PASSWORD, transport=fake, clock=fake.clock)
        self.assertFalse(result["success"])
        self.assertAlmostEqual(fake.calls[-1][-1], 1.0)
        self.assertEqual(result["steps"][-1]["error"], "scenario_timeout")

    def test_unsafe_origin_or_identifiers_are_rejected(self):
        for origin in ("https://user:password@example.invalid", "https://example.invalid/path", "https://example.invalid?secret=value"):
            with self.assertRaises(ValueError):
                Config("point", "deployment", origin, "tour", "departure")


class ReportTests(unittest.TestCase):
    def report(self, records, month="2026-10"):
        return aggregate(records, month=month, points=POINTS, deployment_id="acceptance-1", now=NOW)

    def test_almaty_month_boundaries_and_leap_year(self):
        start, end = month_window("2026-10")
        self.assertEqual(start.isoformat(), "2026-09-30T19:00:00+00:00")
        self.assertEqual(end.isoformat(), "2026-10-31T19:00:00+00:00")
        start, end = month_window("2028-02")
        self.assertEqual((end - start).days, 29)

    def test_two_out_of_three_and_missing_minutes_fail(self):
        report = self.report([observation(), observation("point-b")])
        self.assertEqual(report["successful_minutes"], 1)
        self.assertEqual(report["total_minutes"], 31 * 24 * 60)
        self.assertEqual(report["missing_point_observations"], 31 * 24 * 60 * 3 - 2)
        self.assertFalse(report["slo_met"])

    def test_one_success_never_substitutes_for_three_points(self):
        report = self.report([observation()])
        self.assertEqual(report["successful_minutes"], 0)
        self.assertEqual(report["availability_percent"], 0.0)

    def test_empty_data_is_unknown_and_all_minutes_failed(self):
        report = self.report([])
        self.assertEqual(report["status"], "no_data")
        self.assertIsNone(report["availability_percent"])
        self.assertIsNone(report["slo_met"])
        self.assertEqual(report["failed_minutes"], report["total_minutes"])

    def test_duplicates_cannot_be_cherry_picked(self):
        records = [observation(), observation(), observation("point-b")]
        report = self.report(records)
        self.assertEqual(report["successful_minutes"], 0)
        self.assertEqual(report["duplicate_point_minutes"], 1)

    def test_success_flag_does_not_override_bad_steps_or_time(self):
        for field, value in (("duration_ms", 10001), ("steps", [])):
            record = observation()
            record[field] = value
            self.assertEqual(self.report([record, observation("point-b")])["successful_minutes"], 0)
        record = observation()
        record["steps"][0]["duration_ms"] = float("nan")
        self.assertEqual(self.report([record, observation("point-b")])["successful_minutes"], 0)

    def test_other_configurations_and_invalid_time_are_explicitly_ignored(self):
        record = observation()
        wrong = deepcopy(record)
        wrong["scenario_version"] = "other-v1"
        naive = deepcopy(record)
        naive["timestamp_utc"] = "2026-10-01T00:00:00"
        report = self.report([wrong, naive, observation(timestamp="2026-10-31T19:00:00+00:00"), None])
        self.assertEqual(report["status"], "no_data")
        self.assertEqual(sum(report["ignored_records"].values()), 4)

    def test_partial_month_or_wrong_number_of_points_rejected(self):
        with self.assertRaises(ValueError):
            aggregate([], month="2026-11", points=POINTS, deployment_id="acceptance-1", now=NOW)
        with self.assertRaises(ValueError):
            aggregate([], month="2026-10", points=["point-a"] * 3, deployment_id="acceptance-1", now=NOW)


class CommandTests(unittest.TestCase):
    def test_probe_cli_records_missing_credentials_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config.json").write_text(json.dumps(CONFIG.__dict__))
            import os
            environment = {**os.environ, "SLI_EMAIL": "", "SLI_PASSWORD": ""}
            completed = subprocess.run([sys.executable, "-m", "scripts.availability_probe",
                                        "--config", str(root / "config.json"),
                                        "--output", str(root / "evidence.jsonl")],
                                       env=environment, capture_output=True, text=True, timeout=5)
            self.assertEqual(completed.returncode, 1, completed.stderr)
            result = json.loads((root / "evidence.jsonl").read_text())
            self.assertFalse(result["success"])
            self.assertTrue(all(step["error"] == "not_run" for step in result["steps"]))
            self.assertEqual((root / "evidence.jsonl").stat().st_mode & 0o777, 0o600)

    def test_report_cli_reveals_corrupt_lines_and_no_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "empty.jsonl").write_text("broken json line\n")
            completed = subprocess.run([sys.executable, "-m", "scripts.availability_report",
                                        "--input", str(root / "empty.jsonl"),
                                        "--month", "2026-09", "--points", *POINTS,
                                        "--deployment-id", "acceptance-1",
                                        "--output", str(root / "report.json")],
                                       capture_output=True, text=True, timeout=5)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads((root / "report.json").read_text())
            self.assertEqual(result["status"], "no_data")
            self.assertIsNone(result["availability_percent"])
            self.assertEqual(result["ignored_records"], {"invalid_record": 1})


@unittest.skipUnless(hasattr(signal, "setitimer"), "requires POSIX hard deadlines")
class HTTPTransportTests(unittest.TestCase):
    def test_redirect_is_rejected_without_following(self):
        handler = NoRedirect()
        self.assertIsNone(handler.redirect_request(Request(CONFIG.origin), None, 302, "Found", {}, "https://another.invalid"))
        with patch("scripts.availability_probe.build_opener") as opener:
            opener.return_value.open.side_effect = HTTPError(CONFIG.origin, 302, "Found", {}, None)
            self.assertEqual(request("GET", CONFIG.origin, None, None, 1)[0], 302)
            self.assertEqual(opener.return_value.open.call_count, 1)

    def test_whole_response_deadline_interrupts_blocking_body_read(self):
        def slow_read(maximum):
            for _ in range(20):
                time.sleep(.02)
            return b"{}"

        with patch("scripts.availability_probe.build_opener") as opener:
            response = opener.return_value.open.return_value.__enter__.return_value
            response.read.side_effect = slow_read
            started = time.monotonic()
            with self.assertRaisesRegex(ProbeFailure, "timeout"):
                request("GET", CONFIG.origin, None, None, .08)
            self.assertLess(time.monotonic() - started, .3)


if __name__ == "__main__":
    unittest.main()

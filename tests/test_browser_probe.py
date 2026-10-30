"""Actual Chromium checks: an HTTP 200 shell cannot hide broken JavaScript."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
from threading import Thread
import time
import unittest

from scripts.availability_probe import ProbeFailure, browser_request


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.server.mode == "slow_http":
            time.sleep(2.2)
        if self.path.startswith("/assets/"):
            self.send_response(404)
            self.end_headers()
            return
        if self.server.mode == "healthy":
            body = '<div id="root"></div><script type="module">document.getElementById("root").innerHTML=\'<main><article class="tour-card">Loaded from JavaScript</article></main>\';</script>'
        elif self.server.mode == "resource_error":
            body = '<div id="root"><main><article class="tour-card">shell</article></main></div><script type="module" src="/assets/broken.js"></script>'
        else:
            body = '<div id="root"></div><script type="module">throw new Error("broken application");</script>'
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(("<!doctype html><title>SaparTravel</title>" + body).encode())


@unittest.skipUnless(importlib.util.find_spec("playwright"), "Chromium checks run in the browser and service-acceptance CI jobs")
class BrowserProbeTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.mode = "healthy"
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_javascript_must_render_the_catalog(self):
        status, _, html = browser_request(self.url, 2)
        self.assertEqual(status, 200)
        self.assertIn(b"Loaded from JavaScript", html)
        self.server.mode = "javascript_error"
        with self.assertRaises(ProbeFailure):
            browser_request(self.url, 2)

    def test_a_failed_first_party_script_is_not_a_successful_html_200(self):
        self.server.mode = "resource_error"
        with self.assertRaises(ProbeFailure):
            browser_request(self.url, 2)

    def test_slow_http_still_fails_the_two_second_limit(self):
        self.server.mode = "slow_http"
        with self.assertRaises(ProbeFailure):
            browser_request(self.url, 2)


if __name__ == "__main__":
    unittest.main()

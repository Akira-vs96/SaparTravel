"""Regression for a successful HTTP response containing null or a broken proxy HTML body."""
import argparse
from playwright.sync_api import expect, sync_playwright


def run(base_url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for body, content_type in (("null", "application/json"), ("<h1>Proxy page</h1>", "text/html")):
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))

            def respond(route):
                if "/experiences" in route.request.url:
                    route.fulfill(status=200, content_type=content_type, body=body)
                else:
                    route.fulfill(status=200, content_type="application/json", body='{"items":[]}')

            page.route("**/api/v1/**", respond)
            page.goto(base_url.rstrip("/") + "/explore")
            expect(page.get_by_role("alert").first).to_be_visible(timeout=5000)
            assert not errors, "Malformed HTTP 200 caused a JavaScript crash"
            page.close()
        browser.close()
    print("PASS: null JSON and proxy HTML produce a recoverable error without a JavaScript crash")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:18442")
    run(parser.parse_args().base_url)

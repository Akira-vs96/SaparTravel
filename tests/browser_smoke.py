"""End-to-end checks against a running, disposable SaparTravel demo environment.

Creates a test traveler, changes favorites and creates/cancels a booking.
Optional E2E_ADMIN_EMAIL/E2E_ADMIN_PASSWORD enable the administrator checks.
Run: python tests/browser_smoke.py --base-url http://127.0.0.1:5173
"""

import argparse
import os
from pathlib import Path
import re
import secrets
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright


def run(base_url: str) -> None:
    expect.set_options(timeout=15000)
    artifacts = Path("test-results")
    artifacts.mkdir(exist_ok=True)
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        context.add_init_script("if (!localStorage.getItem('sapar-language')) localStorage.setItem('sapar-language', 'en');")
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.set_default_timeout(15000)

        catalog = context.request.get(f"{base_url}/api/v1/experiences?lang=en&page_size=100")
        assert catalog.ok, f"Catalog API unavailable: {catalog.status}"
        items = catalog.json()["items"]
        assert len(items) >= 18, "Load the demonstration catalog before the browser check."
        trip = items[0]
        detail = context.request.get(f"{base_url}/api/v1/experiences/{trip['slug']}?lang=en").json()
        assert detail["departures"], "Seed a future departure before this check."

        page.goto(base_url, wait_until="networkidle")
        expect(page.get_by_role("heading", level=1)).to_be_visible()
        page.screenshot(path=str(artifacts / "home-desktop.png"), full_page=True)
        language = page.get_by_label("Language / Тіл / Язык")
        for lang in ("ru", "kk", "en"):
            language.select_option(lang)
            expect(page.locator("html")).to_have_attribute("lang", lang)

        page.goto(f"{base_url}/explore")
        expect(page.locator(".tour-card").first).to_be_visible()
        page.get_by_role("combobox", name="Continent", exact=True).select_option("Oceania")
        expect(page).to_have_url(re.compile("continent=Oceania"))
        expect(page.locator(".tour-card").first).to_be_visible()

        email = f"browser-{uuid4().hex[:12]}@example.com"
        page.goto(f"{base_url}/register")
        page.get_by_label("Name", exact=True).fill("Browser Traveler")
        page.get_by_label("Email address", exact=True).fill(email)
        page.get_by_label("Password", exact=False).fill(secrets.token_urlsafe(24))
        page.get_by_role("button", name="Create account", exact=True).click()
        expect(page).to_have_url(re.compile("/account$"))
        page.reload()
        expect(page.get_by_label("Name", exact=True)).to_have_value("Browser Traveler")
        page.get_by_label("Name", exact=True).fill("Browser Traveler Updated")
        page.get_by_role("button", name="Save changes", exact=True).click()
        expect(page.get_by_text("Your profile is updated", exact=True)).to_be_visible()

        page.goto(f"{base_url}/trips/{trip['slug']}")
        expect(page.get_by_role("heading", name=trip["title"], exact=True)).to_be_visible()
        page.get_by_role("button", name="Save trip", exact=True).click()
        expect(page.get_by_role("button", name="Remove saved trip", exact=True)).to_be_visible()
        page.goto(f"{base_url}/favorites")
        expect(page.locator(".tour-card")).to_have_count(1)
        page.reload()
        expect(page.locator(".tour-card")).to_have_count(1)
        page.get_by_role("button", name="Remove saved trip", exact=True).click()
        expect(page.get_by_text("Your wish list is waiting", exact=True)).to_be_visible()

        page.goto(f"{base_url}/trips/{trip['slug']}")
        page.get_by_label("Travelers", exact=True).fill("2")
        page.get_by_role("button", name="Request booking", exact=True).click()
        dialog = page.get_by_role("dialog")
        expect(dialog).to_be_visible()
        name = dialog.get_by_label("Contact name", exact=True)
        name.fill("")
        name.press_sequentially("Browser Travel Guest", delay=10)
        expect(name).to_have_value("Browser Travel Guest")
        dialog.get_by_role("button", name="Send booking request", exact=True).click()
        expect(dialog.get_by_role("heading", name="Your request is on its way!", exact=True)).to_be_visible()
        reference = dialog.locator(".reference-box strong").inner_text()
        dialog.get_by_role("link", name="My bookings", exact=True).click()
        card = page.locator(".booking-card").filter(has_text=reference)
        expect(card.get_by_text("Awaiting confirmation", exact=True)).to_be_visible()
        card.get_by_role("button", name="Cancel booking", exact=True).click()
        page.get_by_role("dialog").get_by_role("button", name="Cancel booking", exact=True).click()
        expect(card.get_by_text("Cancelled", exact=True)).to_be_visible()
        print("PASS: registration, persistent session, profile, favorites, booking and cancellation")

        if os.environ.get("E2E_ADMIN_EMAIL") and os.environ.get("E2E_ADMIN_PASSWORD"):
            page.get_by_role("button", name="Log out", exact=True).click()
            page.goto(f"{base_url}/login")
            page.get_by_label("Email address", exact=True).fill(os.environ["E2E_ADMIN_EMAIL"])
            page.get_by_label("Password", exact=False).fill(os.environ["E2E_ADMIN_PASSWORD"])
            page.get_by_role("button", name="Log in", exact=True).click()
            expect(page).to_have_url(re.compile("/account$"))
            page.goto(f"{base_url}/manage")
            expect(page.get_by_role("heading", name="Service workspace", exact=True)).to_be_visible()
            expect(page.locator(".manage-tour-card").first).to_be_visible()
            page.get_by_role("button", name="Users", exact=True).click()
            row = page.get_by_role("row").filter(has_text=email)
            row.get_by_role("combobox").select_option("vendor")
            row.get_by_role("button", name="Save changes", exact=True).click()
            expect(row.get_by_role("button", name="Save changes", exact=True)).to_be_disabled()
            print("PASS: administrator workspace and assigning a host role")

        page.route(
            "**/api/v1/bookings*",
            lambda route: route.fulfill(status=401, content_type="application/json", body='{"detail":"Session expired"}'),
        )
        page.goto(f"{base_url}/bookings")
        expect(page).to_have_url(re.compile("/login\\?next="))
        expect(page.get_by_role("heading", name="Welcome back", exact=True)).to_be_visible()
        assert page.evaluate("localStorage.getItem('sapar-token')") is None
        page.unroute("**/api/v1/bookings*")
        print("PASS: expired sessions return the traveler to login")

        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(base_url)
        page.get_by_role("button", name="Open menu", exact=True).click()
        expect(page.locator("#mobile-nav")).to_be_visible()
        page.get_by_role("button", name="Close", exact=True).click()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Mobile page overflows horizontally"
        page.screenshot(path=str(artifacts / "home-mobile.png"), full_page=True)

        page.route("**/api/v1/experiences*", lambda route: route.abort())
        page.goto(f"{base_url}/explore")
        expect(page.get_by_role("alert").first).to_be_visible()
        expect(page.locator(".tour-card")).to_have_count(0)
        print("PASS: three languages, continent filtering, mobile navigation and API error state")
        assert not errors, "JavaScript errors: " + "; ".join(errors)
        browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5173")
    run(parser.parse_args().base_url.rstrip("/"))

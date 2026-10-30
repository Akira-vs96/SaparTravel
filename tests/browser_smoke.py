"""End-to-end checks against a running, disposable SaparTravel demo environment.

Creates a test traveler, changes favorites and creates/cancels a booking.
Optional E2E_ADMIN_EMAIL/E2E_ADMIN_PASSWORD enable the administrator checks.
Run: python tests/browser_smoke.py --base-url http://127.0.0.1:5173
"""

import argparse
from datetime import date
from decimal import Decimal
import os
from pathlib import Path
import re
import secrets
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright


def refund_response_replay(page, context, base_url, trip):
    """A lost HTTP response must not duplicate an administrator's partial refund."""
    token = page.evaluate("localStorage.getItem('sapar-token')")
    auth = {"Authorization": "Bearer " + token}
    departure = next(item for item in trip["departures"] if item["available_seats"] > 0)
    created = context.request.post(f"{base_url}/api/v1/bookings", headers=auth, data={
        "departure_id": departure["id"], "travelers_count": 1,
        "contact_name": "Refund Replay Guest", "contact_email": "refund-replay@example.com"})
    assert created.status == 201, "Refund replay booking fixture failed"
    booking = created.json()
    paid = context.request.post(f"{base_url}/api/v1/bookings/{booking['id']}/payments",
        headers={**auth, "Idempotency-Key": str(uuid4())}, data={
            "card_number": "4242424242424242", "holder_name": "DEMO TRAVELER",
            "expiry_month": 12, "expiry_year": date.today().year + 2, "cvc": "123"})
    assert paid.ok and paid.json()["status"] == "succeeded", "Refund replay payment fixture failed"
    page.goto(f"{base_url}/manage")
    page.locator(".manage-toolbar .tabs").get_by_role("button", name="Refunds", exact=True).click()
    page.get_by_role("button", name="Create refund", exact=True).click()
    dialog = page.get_by_role("dialog")
    dialog.get_by_role("combobox").first.select_option(booking["id"])
    dialog.locator("input[type=number]").fill("1000.00")
    dialog.get_by_label("Reason", exact=True).fill("Transport response replay")
    keys = []
    pattern = f"**/api/v1/manage/bookings/{booking['id']}/refunds"
    def lose_first_response(route):
        keys.append(route.request.headers.get("idempotency-key"))
        if len(keys) == 1:
            result = route.fetch()
            assert result.status == 201, "Initial refund did not persist"
            route.abort()
        else:
            route.continue_()
    page.route(pattern, lose_first_response)
    dialog.locator("button.primary").click()
    expect(dialog.get_by_role("alert")).to_be_visible()
    dialog.locator("button.primary").click()
    expect(dialog).not_to_be_visible()
    page.unroute(pattern)
    assert len(keys) == 2 and keys[0] and keys[0] == keys[1], "Refund retry changed idempotency key"
    records = context.request.get(f"{base_url}/api/v1/manage/refunds", headers=auth).json()["items"]
    own = [item for item in records if item["booking_id"] == booking["id"]]
    assert len(own) == 1 and own[0]["amount"] == "1000.00", "Refund response replay duplicated money"
    context.request.post(f"{base_url}/api/v1/bookings/{booking['id']}/cancel", headers=auth)
    print("PASS: lost refund response reuses one operation; no duplicate partial refund")


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
        page.get_by_label("Password", exact=True).fill(secrets.token_urlsafe(24))
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
        page.locator(".booking-panel button.primary").click()
        expect(page).to_have_url(re.compile("/checkout/"))
        page.get_by_label("Traveler 2", exact=True).fill("Second Travel Guest")
        page.get_by_label("Contact name", exact=True).fill("Browser Travel Guest")
        if page.locator(".service-option input").count():
            page.locator(".service-option input").first.check()
        page.get_by_label("Promo code", exact=False).fill("SAPAR10")
        page.locator(".checkbox-label input").check()
        page.get_by_role("button", name="Calculate total", exact=True).click()
        expect(page.get_by_role("button", name="Reserve and continue to payment", exact=True)).to_be_visible()
        expect(page.locator(".checkout-summary").get_by_text("Discount", exact=True)).to_be_visible()
        page.get_by_role("button", name="Reserve and continue to payment", exact=True).click()
        expect(page).to_have_url(re.compile("/bookings/[a-f0-9-]+"))
        booking_id = page.url.split("/bookings/")[1].split("?")[0]
        reference = page.locator(".detail-summary h2").inner_text()
        expect(page.locator(".payment-form")).to_be_visible()
        page.get_by_label("Autofill a test card").select_option("demo_success")
        page.get_by_label("Year", exact=True).fill(str(date.today().year - 1))
        page.locator(".payment-form button.primary").click()
        expect(page.locator(".payment-form [role=alert]")).to_be_visible()
        expect(page.get_by_label("Cardholder name", exact=True)).to_have_value("DEMO TRAVELER")
        page.get_by_label("Autofill a test card").select_option("demo_insufficient")
        page.locator(".payment-form button.primary").click()
        expect(page.locator(".payment-status.failed")).to_be_visible()
        page.get_by_label("Autofill a test card").select_option("demo_3ds")
        page.locator(".payment-form button.primary").click()
        expect(page.locator(".secure-panel")).to_be_visible()
        page.locator(".secure-panel button.primary").click()
        expect(page.locator(".confirmation-banner")).to_be_visible()
        page.reload()
        expect(page.locator(".confirmation-banner")).to_be_visible()
        with page.expect_download() as confirmation:
            page.locator(".document-actions button").nth(0).click()
        assert "Booking confirmation" in Path(confirmation.value.path()).read_text()
        with page.expect_download() as calendar:
            page.locator(".document-actions button").nth(1).click()
        assert "BEGIN:VCALENDAR" in Path(calendar.value.path()).read_text()
        page.screenshot(path=str(artifacts / "booking-confirmed-desktop.png"), full_page=True)
        page.locator(".detail-summary .danger-text").click()
        page.get_by_role("dialog").get_by_role("button", name="Cancel booking", exact=True).click()
        expect(page.locator(".booking-detail .status-badge.cancelled")).to_be_visible()
        token = page.evaluate("localStorage.getItem('sapar-token')")
        result = context.request.get(f"{base_url}/api/v1/bookings/{booking_id}", headers={"Authorization": "Bearer " + token}).json()
        assert result["status"] == "cancelled"
        assert result["currency"] == "KZT" and Decimal(result["discount_amount"]) > 0
        assert Decimal(result["paid_amount"]) == Decimal(result["refunded_amount"])
        assert result["refunds"] and all(item["status"] == "succeeded" for item in result["refunds"])
        page.goto(f"{base_url}/bookings")
        card = page.locator(".booking-card").filter(has_text=reference)
        expect(card.get_by_text("Cancelled", exact=True)).to_be_visible()
        print("PASS: registration, persistent profile/favorites, participant/service/promo quote in KZT, expired card, bank decline, 3DS payment, confirmation/ICS, cancellation and full refund")

        if os.environ.get("E2E_ADMIN_EMAIL") and os.environ.get("E2E_ADMIN_PASSWORD"):
            page.get_by_role("button", name="Log out", exact=True).click()
            page.goto(f"{base_url}/login")
            page.get_by_label("Email address", exact=True).fill(os.environ["E2E_ADMIN_EMAIL"])
            page.get_by_label("Password", exact=True).fill(os.environ["E2E_ADMIN_PASSWORD"])
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
            refund_response_replay(page, context, base_url, detail)

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

"""Browser regressions for manager refund quotes, category-scoped promos and human support reactions."""
import argparse
from datetime import datetime, timedelta
import os
import json
from pathlib import Path
import secrets
from zoneinfo import ZoneInfo

from playwright.sync_api import expect, sync_playwright


def run(origin):
    expect.set_options(timeout=15000)
    suffix = secrets.token_hex(4)
    artifacts = Path("test-results")
    artifacts.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})

        def api(path, *, method="GET", body=None, token=None, expected=200, key=None):
            headers = {"Authorization": "Bearer " + token} if token else {}
            if key:
                headers["Idempotency-Key"] = key
            response = context.request.fetch(origin + "/api/v1" + path, method=method, data=body, headers=headers)
            assert response.status == expected, (path, response.status)
            return response.json()

        admin = api("/auth/login", method="POST", body={"email": os.environ["E2E_ADMIN_EMAIL"], "password": os.environ["E2E_ADMIN_PASSWORD"]})
        token = admin["access_token"]
        context.add_init_script("localStorage.setItem('sapar-language','en');localStorage.setItem('sapar-token'," + json.dumps(token) + ");")
        category = "Wellness" + suffix
        api("/admin/categories", method="POST", token=token, expected=201,
            body={"code": category, "name_ru": "Оздоровление " + suffix, "name_en": "Wellness " + suffix, "name_kk": "Сауықтыру " + suffix})
        page = context.new_page()
        page.set_default_timeout(15000)
        page.goto(origin + "/manage")
        page.get_by_role("button", name="Promo codes", exact=True).click()
        page.get_by_role("button", name="Create promo code", exact=True).click()
        dialog = page.get_by_role("dialog")
        assert "$" not in dialog.inner_text(), "New promo prices must be labelled in KZT"
        code = "WELLNESS" + suffix.upper()
        dialog.get_by_label("Promo code", exact=True).fill(code)
        dialog.get_by_role("combobox", name="Experience", exact=True).select_option(category)
        dialog.get_by_role("button", name="Save changes", exact=True).click()
        expect(dialog).not_to_be_visible()
        assert any(item["code"] == code and item["category"] == category for item in api("/manage/promocodes", token=token)["items"])
        print("PASS: newly created category can be selected and saved in the promo code editor")

        now = datetime.now(ZoneInfo("Asia/Almaty"))
        destination = api("/destinations")["items"][0]
        tour = api("/manage/experiences", method="POST", token=token, expected=201, body={
            "title": "Проверка возврата " + suffix, "title_en": "Refund regression " + suffix,
            "description": "Проверка отмены организатором и согласованного возврата.", "destination_id": destination["id"],
            "category": "Nature", "duration_days": 1, "price_from": "100000.00", "image_url": destination["image_url"],
            "is_published": True, "itinerary": [{"day": 1, "title": "Поездка", "description": "Один день в поездке."}],
            "cancellation_rules": [{"days_before": 0, "refund_percent": 50}]})
        departure = api("/manage/experiences/" + tour["id"] + "/departures", method="POST", token=token, expected=201,
                        body={"start_date": (now.date() + timedelta(days=3)).isoformat(), "capacity": 2, "price": "100000.00"})
        traveler = api("/auth/register", method="POST", expected=201, body={"name": "Service Traveler", "email": "service-" + suffix + "@example.com", "password": secrets.token_urlsafe(24)})
        traveler_token = traveler["access_token"]
        booking = api("/bookings", method="POST", token=traveler_token, expected=201, body={
            "departure_id": departure["id"], "travelers_count": 1, "contact_name": "Service Traveler", "contact_email": "service-" + suffix + "@example.com"})
        api("/bookings/" + booking["id"] + "/payments", method="POST", token=traveler_token, key="service-payment-" + suffix,
            body={"card_number": "4242424242424242", "holder_name": "DEMO TRAVELER", "expiry_month": now.month, "expiry_year": now.year + 1, "cvc": "123"})
        page.goto(origin + "/manage/bookings/" + booking["id"])
        page.locator(".detail-summary .danger-text").click()
        dialog = page.get_by_role("dialog")
        expect(dialog.locator("p.info-note").filter(has_text="Estimated refund")).to_contain_text("100,000")
        expect(dialog.get_by_role("button", name="Cancel booking", exact=True)).to_be_disabled()
        dialog.get_by_label("Reason", exact=True).fill("Organizer cannot run this departure")
        dialog.get_by_role("button", name="Cancel booking", exact=True).click()
        expect(dialog).not_to_be_visible()
        assert api("/bookings/" + booking["id"], token=traveler_token)["refunded_amount"] == "100000.00"
        print("PASS: organizer refund preview and actual operation both return 100000 KZT under a 50% traveler policy")

        ticket = api("/support/tickets", method="POST", token=traveler_token, expected=201, body={
            "subject": "Service response " + suffix, "body": "Please confirm the next step for this incident.", "priority": "P1"})
        page.goto(origin + "/support/" + ticket["id"])
        page.get_by_role("combobox", name="Priority", exact=True).select_option("P2")
        expect(page.get_by_role("combobox", name="Priority", exact=True)).to_have_value("P2")
        page.get_by_label("Message", exact=True).fill("P2 confirmed. We are checking the incident and will update the request.")
        expect(page.get_by_role("checkbox")).to_be_checked()
        page.get_by_role("button", name="Send message", exact=True).click()
        expect(page.get_by_text("First staff response", exact=False)).to_be_visible()
        final = api("/support/tickets/" + ticket["id"], token=traveler_token)
        assert final["first_response_at"] and final["priority"] == "P2" and final["response_working_minutes"] is not None
        page.set_viewport_size({"width": 360, "height": 900})
        assert page.evaluate("document.documentElement.scrollWidth") == 360
        page.screenshot(path=str(artifacts / "service-support-mobile.png"), full_page=True)
        print("PASS: staff priority verification, explicit acknowledgement, immutable first response and mobile support")
        browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5173")
    run(parser.parse_args().base_url.rstrip("/"))

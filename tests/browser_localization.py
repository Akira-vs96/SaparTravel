"""Real checkout, payment errors, documents and cancellation in ru/kk/en.

Run only on a disposable private demonstration environment. Labels are loaded
from the repository's translation module; assertions exercise real HTTP state
changes and rendered UI at 360, 768 and 1440px. Credentials, full test card
numbers and CVC values are never printed or written to browser storage.

E2E_ADMIN_EMAIL=... E2E_ADMIN_PASSWORD=... python tests/browser_localization.py \
    --base-url http://127.0.0.1:5181 --api-url http://127.0.0.1:8011
"""
import argparse
from datetime import date, timedelta
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
from urllib.parse import urlsplit
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright

KEYS = (
    "name", "email", "password", "register", "participant", "contactName", "contactEmail", "notes",
    "acceptPolicy", "reviewOrder", "quoteReady", "reserveAndPay", "checkout", "testInstruments", "cardNumber",
    "cardCvc", "holderName", "expiryMonth", "paymentFailed", "insufficient_funds", "secureConfirm", "close",
    "paymentSuccess", "downloadConfirmation", "addCalendar", "cancelBooking", "cancelled", "succeeded", "validationError", "invalid_expiry_month",
)


def labels():
    source = Path(__file__).resolve().parents[1] / "frontend/src/i18n.js"
    program = """import {pathToFileURL} from 'node:url';
    const module = await import(pathToFileURL(process.argv[1]));
    const keys = JSON.parse(process.argv[2]);
    process.stdout.write(JSON.stringify(Object.fromEntries(['ru','kk','en'].map(lang =>
      [lang,Object.fromEntries(keys.map(key => [key,module.translate(lang,key)]))]))));"""
    result = subprocess.run(["node", "--input-type=module", "-e", program, str(source), json.dumps(KEYS)],
                            capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


class SafeFailure(AssertionError):
    pass


def response_for(path, method):
    return lambda response: urlsplit(response.url).path == "/api/v1" + path and response.request.method == method


def api(context, api_url, path, *, token=None, method="GET", body=None, expected=200):
    response = context.request.fetch(api_url + path, method=method,
                                     headers={"Authorization": "Bearer " + token} if token else {}, data=body)
    if response.status != expected:
        raise SafeFailure(f"{method} {path.split('?')[0]} returned HTTP {response.status}, expected {expected}")
    return None if expected == 204 else response.json()


def no_overflow(page, lang, stage):
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), f"{lang} {stage} overflows horizontally"


def capture(page, path):
    page.evaluate("window.scrollTo({top:0,left:0,behavior:'instant'})")
    page.screenshot(path=str(path), full_page=True,
                    mask=[page.locator(".payment-form input")], mask_color="#153f37")


def private_payment_storage(page, pans, cvc):
    stored = page.evaluate("JSON.stringify({local:{...localStorage},session:{...sessionStorage}})")
    compact = stored.replace(" ", "")
    assert all(pan not in compact for pan in pans), "A full test PAN was persisted to browser storage"
    assert '"' + cvc + '"' not in stored, "A test CVC was persisted to browser storage"
    for key in ("card_number", "cvc", "holder_name", "expiry_month", "expiry_year"):
        assert json.dumps(key) not in stored and json.dumps(key).replace('"', '\\"') not in stored, "Sensitive payment form fields were persisted to browser storage"


def create_fixture(context, api_url, admin_token, suffix, lang):
    destinations = api(context, api_url, "/destinations?lang=" + lang)["items"]
    destination = next((item for item in destinations if item["slug"] == "kazakhstan"), destinations[0])
    day = [{"day": 1, "title": "День на природе", "description": "Встреча с гидом и прогулка по живописному маршруту."}]
    titles = {"ru": "Поездка по Казахстану " + suffix, "kk": "Қазақстанға саяхат " + suffix, "en": "Kazakhstan journey " + suffix}
    descriptions = {"ru": "Небольшая поездка с местным гидом для проверки бронирования на двух языках.",
                    "kk": "Екі қатысушыға арналған жергілікті гидпен шағын сапар және табиғатта серуен.",
                    "en": "A small journey with a local guide and a scenic walk for two travelers."}
    service_names = {"ru": "Трансфер к маршруту", "kk": "Бағытқа трансфер", "en": "Route transfer"}
    body = {"title": titles["ru"], "title_kk": titles["kk"], "title_en": titles["en"],
            "description": descriptions["ru"], "description_kk": descriptions["kk"], "description_en": descriptions["en"],
            "destination_id": destination["id"], "category": "Nature", "duration_days": 1,
            "price_from": "25000.00", "image_url": destination["image_url"], "publication_status": "published",
            "min_participants": 1, "max_participants": 2, "itinerary": day,
            "itinerary_kk": [{"day": 1, "title": "Табиғат күні", "description": "Гидпен кездесу және әсем бағытта серуен."}],
            "itinerary_en": [{"day": 1, "title": "Nature day", "description": "Meet the guide and walk through the scenic route."}],
            "included": ["Гид"], "included_kk": ["Гид"], "included_en": ["Guide"],
            "services": [{"name": service_names["ru"], "name_kk": service_names["kk"], "name_en": service_names["en"],
                          "price": "5000.00", "per_person": True}],
            "cancellation_rules": [{"days_before": 7, "refund_percent": 100}, {"days_before": 0, "refund_percent": 50}]}
    tour = api(context, api_url, "/manage/experiences", method="POST", token=admin_token, body=body, expected=201)
    start = (date.today() + timedelta(days=45)).isoformat()
    departure = api(context, api_url, f"/manage/experiences/{tour['id']}/departures", token=admin_token, method="POST",
                    body={"start_date": start, "capacity": 2, "price": "25000.00"}, expected=201)
    return tour, departure, titles, service_names


def run(base_url, api_url):
    admin_email, admin_password = os.environ.get("E2E_ADMIN_EMAIL"), os.environ.get("E2E_ADMIN_PASSWORD")
    if not admin_email or not admin_password:
        raise SystemExit("Set E2E_ADMIN_EMAIL and E2E_ADMIN_PASSWORD for a disposable private demo environment.")
    text = labels()
    artifacts = Path("test-results")
    artifacts.mkdir(exist_ok=True)
    expect.set_options(timeout=25000)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        setup = browser.new_context()
        admin_token = api(setup, api_url, "/auth/login", method="POST", body={"email": admin_email, "password": admin_password})["access_token"]
        for lang, width in (("ru", 360), ("kk", 768), ("en", 1440)):
            context = browser.new_context(viewport={"width": width, "height": 1000})
            context.add_init_script(f"if (!localStorage.getItem('sapar-language')) localStorage.setItem('sapar-language', '{lang}');")
            page = context.new_page()
            page.set_default_timeout(25000)
            errors = []
            page.on("pageerror", lambda error: errors.append(type(error).__name__))
            suffix = lang + "-" + uuid4().hex[:8]
            email = "locale-" + suffix + "@example.com"
            password = secrets.token_urlsafe(24)
            words = text[lang]
            stage = "fixture setup"
            try:
                tour, departure, titles, service_names = create_fixture(setup, api_url, admin_token, suffix, lang)
                stage = "localized traveler registration"
                page.goto(base_url + "/register")
                expect(page.locator("html")).to_have_attribute("lang", lang)
                page.get_by_label(words["name"], exact=True).fill("Locale Traveler " + suffix)
                page.get_by_label(words["email"], exact=True).fill(email)
                page.get_by_label(words["password"], exact=False).fill(password)
                page.get_by_role("button", name=words["register"], exact=True).click()
                expect(page).to_have_url(re.compile(r"/account$"))
                token = page.evaluate("localStorage.getItem('sapar-token')")

                stage = "checkout and preserving its draft across language switches"
                page.goto(base_url + f"/checkout/{tour['slug']}?departure={departure['id']}&travelers=2")
                expect(page.get_by_role("heading", name=words["checkout"], exact=True)).to_be_visible()
                first, second = "Locale First " + suffix, "Locale Second " + suffix
                contact_name, notes = "Contact " + suffix, "Please meet both travelers at the entrance."
                page.get_by_label(words["participant"] + " 1", exact=True).fill(first)
                page.get_by_label(words["participant"] + " 2", exact=True).fill(second)
                page.get_by_label(words["contactName"], exact=True).fill(contact_name)
                page.get_by_label(words["notes"], exact=False).fill(notes)
                page.locator(".service-option input").check()
                page.get_by_label(words["acceptPolicy"], exact=True).check()
                other_lang = {"ru": "kk", "kk": "en", "en": "ru"}[lang]
                switcher = page.get_by_label("Language / Тіл / Язык", exact=True)
                switcher.select_option(other_lang)
                expect(page.locator("html")).to_have_attribute("lang", other_lang)
                expect(page.get_by_label(text[other_lang]["participant"] + " 2", exact=True)).to_have_value(second)
                expect(page.get_by_label(text[other_lang]["contactName"], exact=True)).to_have_value(contact_name)
                expect(page.locator(".service-option input")).to_be_checked()
                expect(page.get_by_label(text[other_lang]["acceptPolicy"], exact=True)).to_be_checked()
                switcher.select_option(lang)
                expect(page.get_by_label(words["participant"] + " 1", exact=True)).to_have_value(first)
                expect(page.get_by_label(words["notes"], exact=False)).to_have_value(notes)
                page.reload()
                expect(page.get_by_label(words["participant"] + " 2", exact=True)).to_have_value(second)
                expect(page.locator(".service-option input")).to_be_checked()
                no_overflow(page, lang, "checkout")
                capture(page, artifacts / f"localization-{lang}-{width}-checkout.png")
                with page.expect_response(response_for("/bookings/quote", "POST")) as quoted:
                    page.get_by_role("button", name=words["reviewOrder"], exact=True).click()
                assert quoted.value.status == 200
                quote = quoted.value.json()
                assert quote["currency"] == "KZT" and Decimal(quote["total_amount"]) == Decimal("60000")
                expect(page.get_by_role("status").filter(has_text=words["quoteReady"])).to_be_visible()
                with page.expect_response(response_for("/bookings", "POST")) as reserved:
                    page.get_by_role("button", name=words["reserveAndPay"], exact=True).click()
                assert reserved.value.status == 201
                booking = reserved.value.json()
                booking_id = booking["id"]
                assert Decimal(booking["total_amount"]) == Decimal("60000") and booking["travelers_count"] == 2
                assert [person["name"] for person in booking["participants"]] == [first, second]
                assert any(item["kind"] == "service" and Decimal(item["total_amount"]) == Decimal("10000") for item in booking["items"])
                expect(page).to_have_url(re.compile(r"/bookings/" + booking_id))
                expect(page.locator(".payment-form")).to_be_visible()
                assert api(context, api_url, f"/experiences/{tour['slug']}?lang={lang}")["departures"][0]["available_seats"] == 0

                stage = "localized payment validation and insufficient funds"
                instruments = api(context, api_url, "/payments/test-instruments", token=token)["items"]
                pans = [item["card_number"] for item in instruments]
                cvc = "731"
                selector = page.get_by_role("combobox", name=words["testInstruments"], exact=False)
                selector.select_option("demo_insufficient")
                page.get_by_label(words["cardCvc"], exact=True).fill(cvc)
                page.get_by_label(words["expiryMonth"], exact=True).fill("13")
                stage = "invalid month request and HTTP 422"
                with page.expect_response(response_for(f"/bookings/{booking_id}/payments", "POST")) as invalid:
                    page.locator(".payment-form button.primary").click()
                assert invalid.value.status == 422
                stage = "localized validation error rendering"
                expect(page.locator(".payment-form [role=alert]")).to_contain_text(words["invalid_expiry_month"])
                expect(page.get_by_label(words["holderName"], exact=True)).to_have_value("DEMO TRAVELER")
                stage = "payment form fields remain out of browser storage"
                private_payment_storage(page, pans, cvc)
                selector.select_option("demo_insufficient")
                page.get_by_label(words["cardCvc"], exact=True).fill(cvc)
                stage = "insufficient funds request"
                with page.expect_response(response_for(f"/bookings/{booking_id}/payments", "POST")) as declined:
                    page.locator(".payment-form button.primary").click()
                assert declined.value.status == 200 and declined.value.json()["status"] == "failed"
                assert declined.value.json()["error_code"] == "insufficient_funds"
                stage = "localized insufficient funds failure rendering"
                expect(page.locator(".payment-status.failed")).to_contain_text(words["paymentFailed"])
                expect(page.locator(".payment-status.failed")).to_contain_text(words["insufficient_funds"])
                no_overflow(page, lang, "payment error")
                capture(page, artifacts / f"localization-{lang}-{width}-payment-error.png")
                private_payment_storage(page, pans, cvc)

                stage = "3-D Secure cancellation and permitted successful retry"
                selector.select_option("demo_3ds")
                page.get_by_label(words["cardCvc"], exact=True).fill(cvc)
                with page.expect_response(response_for(f"/bookings/{booking_id}/payments", "POST")) as action:
                    page.locator(".payment-form button.primary").click()
                action_body = action.value.json()
                assert action_body["status"] == "requires_action"
                expect(page.locator(".secure-panel")).to_contain_text(words["secureConfirm"])
                private_payment_storage(page, pans, cvc)
                with page.expect_response(response_for(f"/payments/{action_body['id']}/confirm", "POST")) as closed:
                    page.locator(".secure-panel").get_by_role("button", name=words["close"], exact=True).click()
                assert closed.value.json()["status"] == "cancelled"
                expect(page.locator(".payment-status.failed")).to_be_visible()
                expect(page.locator(".payment-form")).to_be_visible()
                selector.select_option("demo_success")
                page.get_by_label(words["cardCvc"], exact=True).fill(cvc)
                with page.expect_response(response_for(f"/bookings/{booking_id}/payments", "POST")) as success:
                    page.locator(".payment-form button.primary").click()
                assert success.value.json()["status"] == "succeeded"
                expect(page.locator(".confirmation-banner")).to_contain_text(words["paymentSuccess"])
                page.reload()
                expect(page.locator(".confirmation-banner")).to_contain_text(words["paymentSuccess"])
                paid = api(context, api_url, f"/bookings/{booking_id}?lang={lang}", token=token)
                assert paid["status"] == "confirmed" and Decimal(paid["paid_amount"]) == Decimal("60000")
                assert [attempt["status"] for attempt in paid["payments"]] == ["failed", "cancelled", "succeeded"]
                private_payment_storage(page, pans, cvc)
                no_overflow(page, lang, "confirmed booking")
                capture(page, artifacts / f"localization-{lang}-{width}-confirmed.png")

                stage = "localized confirmation document and calendar export"
                with page.expect_download() as confirmation:
                    page.get_by_role("button", name=words["downloadConfirmation"], exact=True).click()
                html = Path(confirmation.value.path()).read_text()
                assert f'<html lang="{lang}">' in html and titles[lang] in html
                assert "60000" in html.replace(" ", "")
                with page.expect_download() as calendar:
                    page.get_by_role("button", name=words["addCalendar"], exact=True).click()
                ics = Path(calendar.value.path()).read_text()
                unfolded = ics.replace("\n ", "")
                assert "BEGIN:VCALENDAR" in ics and f"UID:{booking_id}@sapartravel.demo" in ics
                assert "SUMMARY:" + titles[lang] in unfolded
                assert "DTSTART;VALUE=DATE:" + departure["start_date"].replace("-", "") in ics

                stage = "localized cancellation and full refund"
                page.locator(".detail-summary").get_by_role("button", name=words["cancelBooking"], exact=True).click()
                dialog = page.get_by_role("dialog")
                expect(dialog).to_be_visible()
                with page.expect_response(response_for(f"/bookings/{booking_id}/cancel", "POST")) as cancelled:
                    dialog.get_by_role("button", name=words["cancelBooking"], exact=True).click()
                assert cancelled.value.status == 200
                expect(page.locator(".booking-detail .status-badge.cancelled")).to_have_text(words["cancelled"])
                final = api(context, api_url, f"/bookings/{booking_id}?lang={lang}", token=token)
                assert final["status"] == "cancelled"
                assert Decimal(final["paid_amount"]) == Decimal(final["refunded_amount"]) == Decimal("60000")
                assert final["refunds"] and all(refund["status"] == "succeeded" for refund in final["refunds"])
                assert api(context, api_url, f"/experiences/{tour['slug']}?lang={lang}")["departures"][0]["available_seats"] == 2
                expect(page.locator(".transaction-row .status-badge.succeeded").first).to_have_text(words["succeeded"])
                no_overflow(page, lang, "cancelled booking")
                capture(page, artifacts / f"localization-{lang}-{width}-cancelled.png")
                private_payment_storage(page, pans, cvc)
                assert not errors, "A JavaScript page error occurred"
                print(f"PASS: {lang} at {width}px — UI registration, preserved checkout, participant/service quote, localized payment errors, 3DS cancellation/retry, payment, localized HTML/ICS, full refund and released seats")
            except Exception as error:
                if stage != "localized traveler registration":
                    capture(page, artifacts / f"localization-{lang}-failure.png")
                # Do not print Playwright call logs: registration and payment
                # locators can include secret form values in those logs.
                if isinstance(error, SafeFailure):
                    raise AssertionError(f"Localization E2E {lang}: {error}") from None
                raise AssertionError(f"Localization E2E failed: {lang} at {width}px, stage: {stage}") from None
            finally:
                context.close()
        setup.close()
        browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5181")
    parser.add_argument("--api-url", help="API origin or /api/v1 prefix; defaults to BASE_URL/api/v1")
    args = parser.parse_args()
    api_url = (args.api_url or args.base_url.rstrip("/") + "/api/v1").rstrip("/")
    if not urlsplit(api_url).path:
        api_url += "/api/v1"
    run(args.base_url.rstrip("/"), api_url)

"""Engagement E2E on a disposable running SaparTravel demonstration environment.

Uses actual UI forms for account recovery, support, notifications, saved searches
and comparison. API setup creates an isolated supplier, tour and booking; the
private administrator mailbox is filtered to the newly registered traveler only.
Passwords, bearer tokens and reset links are never printed or written as artifacts.

E2E_ADMIN_EMAIL=... E2E_ADMIN_PASSWORD=... python tests/browser_engagement.py \
    --base-url http://127.0.0.1:5181 --api-url http://127.0.0.1:8011/api/v1
"""
import argparse
from datetime import date, timedelta
import os
from pathlib import Path
import re
import secrets
from urllib.parse import urlsplit
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright


class SafeCheckError(AssertionError):
    """Failure detail containing no request body or secrets."""


def response_for(path, method):
    return lambda response: urlsplit(response.url).path == f"/api/v1{path}" and response.request.method == method


def api(context, api_url, path, *, method="GET", token=None, body=None, expected=200):
    response = context.request.fetch(api_url + path, method=method,
                                     headers={"Authorization": "Bearer " + token} if token else {},
                                     data=body)
    if response.status != expected:
        raise SafeCheckError(f"API setup/check {method} {path.split('?')[0]} returned HTTP {response.status}, expected {expected}")
    return None if response.status == 204 else response.json()


def login(page, base_url, email, password):
    page.goto(base_url + "/login")
    page.get_by_label("Email address", exact=True).fill(email)
    page.get_by_label("Password", exact=False).fill(password)
    page.get_by_role("button", name="Log in", exact=True).click()
    expect(page).to_have_url(re.compile(r"/account$"))


def run(base_url, api_url):
    admin_email = os.environ.get("E2E_ADMIN_EMAIL")
    admin_password = os.environ.get("E2E_ADMIN_PASSWORD")
    if not admin_email or not admin_password:
        raise SystemExit("Set E2E_ADMIN_EMAIL and E2E_ADMIN_PASSWORD for a private disposable demo environment.")
    expect.set_options(timeout=20000)
    artifacts = Path("test-results")
    artifacts.mkdir(exist_ok=True)
    suffix = uuid4().hex[:10]
    traveler_email = f"engagement-{suffix}@example.com"
    traveler_password = secrets.token_urlsafe(24)
    replacement_password = secrets.token_urlsafe(24)
    vendor_email = f"engagement-host-{suffix}@example.com"
    vendor_password = secrets.token_urlsafe(24)
    errors = []
    private_values = [admin_password, traveler_password, replacement_password, vendor_password]
    def capture_error(error):
        message = str(error).splitlines()[0]
        for value in private_values:
            if value:
                message = message.replace(value, "[redacted]")
        message = re.sub(r"https?://\S+", "[URL redacted]", message)
        message = re.sub(r"[A-Za-z0-9_-]{20,}(?:\.[A-Za-z0-9_-]+)*", "[value redacted]", message)
        errors.append(message)
    step = "initialization"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        traveler_context = browser.new_context(viewport={"width": 1440, "height": 1000})
        vendor_context = browser.new_context(viewport={"width": 1440, "height": 1000})
        for context in (traveler_context, vendor_context):
            context.add_init_script("if (!localStorage.getItem('sapar-language')) localStorage.setItem('sapar-language', 'en');")
        traveler = traveler_context.new_page()
        vendor = vendor_context.new_page()
        for page in (traveler, vendor):
            page.set_default_timeout(20000)
            page.on("pageerror", capture_error)
        try:
            step = "traveler registration"
            admin = api(traveler_context, api_url, "/auth/login", method="POST", body={"email": admin_email, "password": admin_password})
            admin_token = admin["access_token"]
            private_values.append(admin_token)
            traveler.goto(base_url + "/register")
            traveler.get_by_label("Name", exact=True).fill("Engagement Traveler " + suffix)
            traveler.get_by_label("Email address", exact=True).fill(traveler_email)
            traveler.get_by_label("Password", exact=False).fill(traveler_password)
            traveler.get_by_role("button", name="Create account", exact=True).click()
            expect(traveler).to_have_url(re.compile(r"/account$"))
            old_token = traveler.evaluate("localStorage.getItem('sapar-token')")
            with traveler.expect_response(response_for("/auth/logout", "POST")) as logout_response:
                traveler.locator(".account-nav").get_by_role("button", name="Log out", exact=True).click()
            assert logout_response.value.status == 204
            api(traveler_context, api_url, "/auth/me", token=old_token, expected=401)

            step = "one-use recovery through the private mailbox"
            traveler.goto(base_url + "/reset-password")
            traveler.get_by_label("Email address", exact=True).fill(traveler_email)
            with traveler.expect_response(response_for("/auth/forgot-password", "POST")) as requested:
                traveler.get_by_role("button", name="Send reset link", exact=True).click()
            assert requested.value.status == 200
            expect(traveler.get_by_role("status")).to_contain_text("If the account exists")
            mailbox = api(traveler_context, api_url, f"/admin/demo-mailbox?recipient={traveler_email}", token=admin_token)
            assert len(mailbox["items"]) == 1 and mailbox["items"][0]["recipient"] == traveler_email
            match = re.search(r"token=([A-Za-z0-9_-]+)", mailbox["items"][0]["body"])
            assert match, "The private delivery adapter did not persist a recovery link"
            recovery_token = match.group(1)
            private_values.append(recovery_token)
            # The reset URL is kept in memory only. Failures are re-raised with a
            # step name below; Playwright call logs must never print this token.
            reset_link = re.search(r"https?://[^\s]+", mailbox["items"][0]["body"]).group(0)
            assert urlsplit(reset_link).path == "/reset-password", "Unexpected recovery route"
            traveler.goto(reset_link)
            traveler.get_by_label("New password", exact=False).fill(replacement_password)
            with traveler.expect_response(response_for("/auth/reset-password", "POST")) as reset:
                traveler.get_by_role("button", name="Change password", exact=True).click()
            assert reset.value.status == 200
            expect(traveler.get_by_role("status")).to_have_text("Password reset. Sign in using your new password.")
            api(traveler_context, api_url, "/auth/reset-password", method="POST", body={"token": recovery_token, "new_password": secrets.token_urlsafe(24)}, expected=422)
            recovery_token = None
            api(traveler_context, api_url, "/auth/login", method="POST", body={"email": traveler_email, "password": traveler_password}, expected=401)
            login(traveler, base_url, traveler_email, replacement_password)
            traveler_token = traveler.evaluate("localStorage.getItem('sapar-token')")
            private_values.append(traveler_token)
            print("PASS: UI registration, persisted logout, private reset delivery, password reset and one-use rejection")

            step = "isolated supplier and owned booking setup"
            host = api(traveler_context, api_url, "/auth/register", method="POST", expected=201,
                       body={"name": "Engagement Host " + suffix, "email": vendor_email, "password": vendor_password})
            api(traveler_context, api_url, "/admin/users/" + host["user"]["id"], method="PATCH", token=admin_token, body={"role": "vendor"})
            vendor_token = host["access_token"]
            private_values.append(vendor_token)
            destination = api(traveler_context, api_url, "/destinations?lang=en")["items"][0]
            itinerary = [{"day": 1, "title": "Local walk", "description": "A guided walk with the local host."}]
            tour = api(traveler_context, api_url, "/manage/experiences", method="POST", expected=201, token=vendor_token,
                       body={"title": "Маршрут проверки " + suffix, "title_en": "Engagement journey " + suffix,
                             "title_kk": "Сынақ бағыты " + suffix, "description": "Содержательный маршрут для проверки обращения к собственному организатору.",
                             "description_en": "A detailed route for checking a conversation with the correct travel host.",
                             "description_kk": "Жеке ұйымдастырушымен хат алмасуды тексеруге арналған толық бағыт.",
                             "destination_id": destination["id"], "category": "Nature", "duration_days": 1,
                             "price_from": 25000, "image_url": destination["image_url"], "is_published": True,
                             "itinerary": itinerary, "itinerary_en": itinerary, "itinerary_kk": itinerary,
                             "included": ["Гид"], "included_en": ["Guide"], "included_kk": ["Гид"]})
            departure = api(traveler_context, api_url, f"/manage/experiences/{tour['id']}/departures", method="POST", expected=201, token=vendor_token,
                            body={"start_date": (date.today() + timedelta(days=45)).isoformat(), "capacity": 5, "price": 25000})
            booking = api(traveler_context, api_url, "/bookings", method="POST", expected=201, token=traveler_token,
                          body={"departure_id": departure["id"], "travelers_count": 1, "contact_name": "Engagement Traveler",
                                "contact_email": traveler_email, "participants": [{"name": "Engagement Traveler"}], "accept_cancellation_policy": True})

            step = "support create, owned supplier reply and customer notification"
            subject = "Route question " + suffix
            traveler.goto(base_url + "/support?booking=" + booking["id"])
            dialog = traveler.get_by_role("dialog")
            expect(dialog).to_be_visible()
            dialog.get_by_label("Subject", exact=True).fill(subject)
            dialog.get_by_label("Message", exact=True).fill("Please confirm our meeting place with the guide.")
            with traveler.expect_response(response_for("/support/tickets", "POST")) as created:
                dialog.get_by_role("button", name="Send message", exact=True).click()
            assert created.value.status == 201
            ticket_id = created.value.json()["id"]
            expect(traveler).to_have_url(re.compile(r"/support/" + ticket_id + r"$"))
            expect(traveler.get_by_role("heading", name=subject, exact=True)).to_be_visible()
            login(vendor, base_url, vendor_email, vendor_password)
            vendor.goto(base_url + "/support")
            vendor.get_by_role("link").filter(has=vendor.get_by_role("heading", name=subject, exact=True)).click()
            vendor.get_by_label("Message", exact=True).fill("The guide will meet you at the main entrance at 09:00.")
            with vendor.expect_response(response_for(f"/support/tickets/{ticket_id}/messages", "POST")) as replied:
                vendor.get_by_role("button", name="Send message", exact=True).click()
            assert replied.value.status == 201
            vendor.get_by_role("button", name="In progress", exact=True).click()
            expect(vendor.locator(".status-badge").filter(has_text="In progress")).to_be_visible()
            vendor.get_by_role("button", name="Resolved", exact=True).click()
            expect(vendor.locator(".status-badge").filter(has_text="Resolved")).to_be_visible()
            traveler.reload()
            expect(traveler.get_by_text("The guide will meet you at the main entrance at 09:00.", exact=True)).to_be_visible()
            traveler.get_by_role("button", name="Reopen request", exact=True).click()
            expect(traveler.locator(".status-badge").filter(has_text="Open")).to_be_visible()
            traveler.screenshot(path=str(artifacts / "engagement-support-desktop.png"), full_page=True)
            # A second supplier cannot see or answer this conversation by direct API request.
            foreign = api(traveler_context, api_url, "/auth/register", method="POST", expected=201,
                          body={"name": "Other Host " + suffix, "email": f"other-host-{suffix}@example.com", "password": secrets.token_urlsafe(24)})
            api(traveler_context, api_url, "/admin/users/" + foreign["user"]["id"], method="PATCH", token=admin_token, body={"role": "vendor"})
            api(traveler_context, api_url, f"/support/tickets/{ticket_id}", token=foreign["access_token"], expected=404)
            api(traveler_context, api_url, f"/support/tickets/{ticket_id}/messages", method="POST", token=foreign["access_token"], body={"body": "Unauthorized reply"}, expected=404)
            traveler.goto(base_url + "/notifications")
            expect(traveler.locator(".notification-card.unread").first).to_be_visible()
            language = traveler.get_by_label("Language / Тіл / Язык", exact=True)
            for lang, translated_title in (("kk", "Қолдау өтініші жаңартылды"), ("ru", "Обновление обращения"), ("en", "Support request updated")):
                language.select_option(lang)
                expect(traveler.locator("html")).to_have_attribute("lang", lang)
                expect(traveler.get_by_role("heading", name=translated_title, exact=True).first).to_be_visible()
            with traveler.expect_response(response_for("/notifications/read-all", "POST")) as read:
                traveler.get_by_role("button", name="Mark all as read", exact=True).click()
            assert read.value.status == 204
            expect(traveler.locator(".notification-card.unread")).to_have_count(0)
            assert api(traveler_context, api_url, "/notifications", token=traveler_token)["unread_count"] == 0
            print("PASS: support UI create/reply/status, supplier isolation and persistent notification reads")

            step = "saved search URL restoration and comparison limit"
            traveler.goto(base_url + "/explore?category=Nature&max_price=500000&travelers=1&sort=price_asc")
            expect(traveler.locator(".tour-card").first).to_be_visible()
            traveler.get_by_role("button", name="Save search", exact=True).click()
            dialog = traveler.get_by_role("dialog")
            search_name = "Mountain budget " + suffix
            dialog.get_by_label("Search name", exact=True).fill(search_name)
            with traveler.expect_response(response_for("/saved-searches", "POST")) as saved:
                dialog.get_by_role("button", name="Save changes", exact=True).click()
            assert saved.value.status == 201
            traveler.goto(base_url + "/saved-searches")
            search_card = traveler.locator(".saved-search").filter(has_text=search_name)
            expect(search_card).to_be_visible()
            traveler.reload()
            search_card.get_by_role("link", name="Search", exact=False).click()
            expect(traveler).to_have_url(re.compile("category=Nature"))
            expect(traveler).to_have_url(re.compile("travelers=1"))
            expect(traveler.get_by_role("combobox", name="Sort", exact=False)).to_have_value("price_asc")
            traveler.goto(base_url + "/explore")
            expect(traveler.locator(".tour-card").nth(3)).to_be_visible()
            for index in range(4):
                traveler.locator(".tour-card").nth(index).get_by_role("button", name="Compare trip", exact=True).click()
            assert len(traveler.evaluate("JSON.parse(localStorage.getItem('sapar-compare'))")) == 3
            expect(traveler.get_by_role("status")).to_contain_text("You can compare up to three trips")
            traveler.goto(base_url + "/compare")
            expect(traveler.locator(".compare-column")).to_have_count(3)
            expect(traveler.locator(".compare-column dl")).to_have_count(3)
            traveler.reload()
            expect(traveler.locator(".compare-column")).to_have_count(3)
            expect(traveler.locator(".compare-column dl")).to_have_count(3)
            traveler.locator(".compare-column").first.get_by_role("button", name="Remove", exact=True).click()
            expect(traveler.locator(".compare-column")).to_have_count(2)
            expect(traveler.locator(".compare-column dl")).to_have_count(2)
            for index in range(2):
                traveler.locator(".compare-column").nth(index).scroll_into_view_if_needed()
            traveler.evaluate("scrollTo(0, 0)")
            for width in (360, 768, 1440):
                traveler.set_viewport_size({"width": width, "height": 960})
                assert traveler.evaluate("document.documentElement.scrollWidth <= innerWidth"), f"Comparison overflows at {width}px"
                traveler.screenshot(path=str(artifacts / f"engagement-compare-{width}.png"), full_page=True)
            traveler.goto(base_url + "/saved-searches")
            traveler.get_by_role("button", name="Remove: " + search_name, exact=True).click()
            expect(traveler.get_by_role("heading", name=search_name, exact=True)).to_have_count(0)
            assert all(item["name"] != search_name for item in api(traveler_context, api_url, "/saved-searches", token=traveler_token)["items"])
            step = "JavaScript error verification"
            if errors:
                raise SafeCheckError("JavaScript page errors: " + "; ".join(errors))
            print("PASS: saved search persistence and restoration, comparison limit, removal and 360/768/1440px layouts")
        except Exception as error:
            if isinstance(error, SafeCheckError):
                raise AssertionError(str(error)) from None
            if "recovery" not in step:
                traveler.screenshot(path=str(artifacts / "engagement-failure.png"), full_page=True)
            # Do not interpolate the underlying Playwright exception: its call log
            # may contain a private reset URL or submitted credentials.
            raise AssertionError("Engagement E2E failed at step: " + step) from None
        finally:
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

"""Browser coverage for destination and multilingual trip management.

Run against a disposable, running environment:
    E2E_ADMIN_EMAIL=... E2E_ADMIN_PASSWORD=... \\
        python tests/browser_management.py --base-url http://127.0.0.1:4173

Creates a unique destination, a multilingual administrator trip and a promoted
host account with its own draft trip. Both trips remain unpublished. Credentials are read from environment variables, never logged.
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


IMAGE_URL = (
    "https://images.unsplash.com/photo-1464822759023-fed622ff2c3b"
    "?auto=format&fit=crop&w=800&q=80"
)
LANGUAGE_NAMES = {"ru": "Russian", "kk": "Kazakh", "en": "English"}


def response_for(path: str, method: str):
    return lambda response: (
        urlsplit(response.url).path == f"/api/v1{path}"
        and response.request.method == method
    )


def save_dialog(page, dialog, path: str, method: str) -> dict:
    with page.expect_response(response_for(path, method)) as result:
        dialog.get_by_role("button", name="Save changes", exact=True).click()
    response = result.value
    assert response.ok, f"Saving {path} returned HTTP {response.status}"
    expect(dialog).not_to_be_visible()
    return response.json()


def set_translation(dialog, lang: str, values: dict, *, destination=False):
    dialog.get_by_role("button", name=LANGUAGE_NAMES[lang], exact=True).click()
    title_label = "Title" if destination else f"Title ({LANGUAGE_NAMES[lang]})"
    title = dialog.get_by_label(title_label, exact=True)
    title.fill("")
    # Real keystrokes catch dialogs that incorrectly reopen on every change.
    title.press_sequentially(values["title"], delay=2)
    expect(title).to_have_value(values["title"])
    expect(title).to_be_focused()
    dialog.get_by_role("textbox", name="Description", exact=True).first.fill(values["description"])
    if destination:
        dialog.get_by_label("Country", exact=True).fill(values["country"])
        return
    dialog.get_by_label("Tags, separated by commas", exact=True).fill(values["tag"])
    dialog.get_by_role("textbox", name="What’s included", exact=False).fill(values["included"])
    dialog.get_by_role("textbox", name="Not included", exact=False).fill(values["excluded"])
    for index, day in enumerate(values["itinerary"]):
        dialog.get_by_role("button", name="Add a day", exact=True).click()
        row = dialog.locator(".itinerary-edit-day").nth(index)
        expect(row.get_by_label("Day", exact=True)).to_have_value(str(index + 1))
        row.get_by_label("Title", exact=True).fill(day["title"])
        row.get_by_role("textbox", name="Description", exact=True).fill(day["description"])



def check_host_workflow(browser, admin_page, base_url: str, destination_id: str, suffix: str, errors: list) -> None:
    """A newly promoted traveler can create a draft in their own host workspace."""
    host_context = browser.new_context(viewport={"width": 1440, "height": 1000})
    host_context.add_init_script("localStorage.setItem('sapar-language', 'en');")
    host = host_context.new_page()
    host.set_default_timeout(20000)
    host.on("pageerror", lambda error: errors.append(str(error)))
    email = f"management-host-{suffix}@example.com"
    title = f"Маршрут организатора {suffix}"
    try:
        host.goto(f"{base_url}/register")
        host.get_by_label("Name", exact=True).fill(f"Browser Host {suffix}")
        host.get_by_label("Email address", exact=True).fill(email)
        host.get_by_label("Password", exact=False).fill(secrets.token_urlsafe(24))
        host.get_by_role("button", name="Create account", exact=True).click()
        expect(host).to_have_url(re.compile("/account$"))
        admin_page.goto(f"{base_url}/manage")
        admin_page.get_by_role("button", name="Users", exact=True).click()
        row = admin_page.get_by_role("row").filter(has_text=email)
        row.get_by_role("combobox").select_option("vendor")
        row.get_by_role("button", name="Save changes", exact=True).click()
        expect(row.get_by_role("button", name="Save changes", exact=True)).to_be_disabled()
        host.reload()
        expect(host.get_by_text("Host", exact=True)).to_be_visible()
        host.goto(f"{base_url}/manage")
        expect(host.get_by_role("heading", name="Host workspace", exact=True)).to_be_visible()
        expect(host.locator(".manage-tour-card")).to_have_count(0)
        host.get_by_role("button", name="Create a trip", exact=True).click()
        dialog = host.get_by_role("dialog")
        dialog.get_by_label("Title (Russian)", exact=True).fill(title)
        dialog.get_by_role("textbox", name="Description", exact=True).fill(
            "Проверка создания собственного маршрута в кабинете нового организатора."
        )
        dialog.get_by_role("combobox", name="Destination", exact=True).select_option(destination_id)
        dialog.get_by_label("Image URL", exact=True).fill(IMAGE_URL)
        save_dialog(host, dialog, "/manage/experiences", "POST")
        card = host.locator(".manage-tour-card").filter(has_text=title)
        expect(card.get_by_text("Draft", exact=True)).to_be_visible()
        host.reload()
        expect(host.locator(".manage-tour-card")).to_have_count(1)
        expect(card.get_by_text("Draft", exact=True)).to_be_visible()
        print("PASS: traveler promoted through UI can create and retain a private host trip")
    except Exception:
        host.screenshot(path="test-results/management-host-failure.png", full_page=True)
        raise
    finally:
        host_context.close()


def run(base_url: str) -> None:
    email = os.environ.get("E2E_ADMIN_EMAIL")
    password = os.environ.get("E2E_ADMIN_PASSWORD")
    if not email or not password:
        raise SystemExit("Set E2E_ADMIN_EMAIL and E2E_ADMIN_PASSWORD before running.")
    expect.set_options(timeout=15000)
    artifacts = Path("test-results")
    artifacts.mkdir(exist_ok=True)
    suffix = uuid4().hex[:10]
    destination_slug = f"e2e-island-{suffix}"
    destination_values = {
        "ru": {
            "title": f"Тестовый остров {suffix}",
            "country": "Тестовая страна",
            "description": "Демонстрационный остров для проверки управления туристическими направлениями.",
        },
        "kk": {
            "title": f"Сынақ аралы {suffix}",
            "country": "Сынақ елі",
            "description": "Туристік бағыттарды басқаруды тексеруге арналған демонстрациялық арал.",
        },
        "en": {
            "title": f"Browser Island {suffix}",
            "country": "Example Country",
            "description": "A demonstration island for exercising destination management in the browser.",
        },
    }
    tour_values = {
        "ru": {
            "title": f"Путешествие по острову {suffix}",
            "description": "Два дня по тропам демонстрационного острова с местным гидом и прогулкой у моря.",
            "tag": "остров, прогулка",
            "included": "Местный гид\nТрансфер",
            "excluded": "Авиабилеты",
            "itinerary": [
                {"title": "Знакомство с островом", "description": "Встречаем группу и гуляем по островным тропам."},
                {"title": "Побережье и возвращение", "description": "Завершаем путешествие прогулкой вдоль моря."},
            ],
        },
        "kk": {
            "title": f"Аралға саяхат {suffix}",
            "description": "Жергілікті гидпен демонстрациялық арал соқпақтарында екі күн және теңіз жағасында серуен.",
            "tag": "арал, серуен",
            "included": "Жергілікті гид\nТрансфер",
            "excluded": "Әуе билеттері",
            "itinerary": [
                {"title": "Аралмен танысу", "description": "Топпен кездесіп, арал соқпақтарында серуендейміз."},
                {"title": "Жағалау және оралу", "description": "Саяхатты теңіз жағасындағы серуенмен аяқтаймыз."},
            ],
        },
        "en": {
            "title": f"Island Discovery {suffix}",
            "description": "Two days on the trails of a demonstration island with a local guide and a seaside walk.",
            "tag": "island, walking",
            "included": "Local guide\nTransfer",
            "excluded": "Flights",
            "itinerary": [
                {"title": "Meet the island", "description": "Meet the group and explore the island trails together."},
                {"title": "Coast and return", "description": "Finish the journey with a walk along the coast."},
            ],
        },
    }
    errors = []
    created_tour_id = None
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        context.add_init_script(
            "if (!localStorage.getItem('sapar-language')) "
            "localStorage.setItem('sapar-language', 'en');"
        )
        page = context.new_page()
        page.set_default_timeout(20000)
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            page.goto(f"{base_url}/login")
            page.get_by_label("Email address", exact=True).fill(email)
            page.get_by_label("Password", exact=False).fill(password)
            page.get_by_role("button", name="Log in", exact=True).click()
            expect(page).to_have_url(re.compile("/account$"))
            page.goto(f"{base_url}/manage")
            expect(page.get_by_role("heading", name="Service workspace", exact=True)).to_be_visible()

            page.get_by_role("button", name="Destinations", exact=True).click()
            page.get_by_role("button", name="New destination", exact=True).click()
            dialog = page.get_by_role("dialog")
            for lang, values in destination_values.items():
                set_translation(dialog, lang, values, destination=True)
            dialog.get_by_label("Catalog address", exact=False).fill(destination_slug)
            dialog.get_by_role("combobox", name="Continent", exact=True).select_option("Oceania")
            dialog.get_by_label("Image URL", exact=True).fill(IMAGE_URL)
            destination = save_dialog(page, dialog, "/manage/destinations", "POST")
            destination_card = page.locator(".manage-destination-card").filter(
                has_text=destination_values["en"]["title"]
            )
            expect(destination_card).to_be_visible()
            destination_card.get_by_role("button", name="Edit", exact=True).click()
            for lang, values in destination_values.items():
                dialog.get_by_role("button", name=LANGUAGE_NAMES[lang], exact=True).click()
                expect(dialog.get_by_label("Title", exact=True)).to_have_value(values["title"])
                expect(dialog.get_by_label("Country", exact=True)).to_have_value(values["country"])
                expect(dialog.get_by_role("textbox", name="Description", exact=True)).to_have_value(values["description"])
            dialog.get_by_role("button", name="Cancel", exact=True).click()
            print("PASS: destination creation and persistent RU/KK/EN translations")

            page.get_by_role("button", name="All trips", exact=True).click()
            page.get_by_role("button", name="Create a trip", exact=True).click()
            dialog.get_by_label("Duration in days", exact=True).fill("2")
            for lang, values in tour_values.items():
                set_translation(dialog, lang, values)
            dialog.get_by_role("combobox", name="Destination", exact=True).select_option(destination["id"])
            dialog.get_by_role("combobox", name="Experience", exact=True).select_option("Nature")
            dialog.get_by_label("Price, USD", exact=True).fill("315.50")
            dialog.get_by_label("Image URL", exact=True).fill(IMAGE_URL)
            expect(dialog.get_by_label("Publish", exact=True)).not_to_be_checked()
            tour = save_dialog(page, dialog, "/manage/experiences", "POST")
            created_tour_id = tour["id"]
            tour_title_ru = tour_values["ru"]["title"]
            card = page.locator(".manage-tour-card").filter(has_text=tour_title_ru)
            expect(card.get_by_text("Draft", exact=True)).to_be_visible()

            card.get_by_role("button", name="Departures", exact=True).click()
            departure_date = (date.today() + timedelta(days=120)).isoformat()
            dialog.get_by_label("Start date", exact=True).fill(departure_date)
            dialog.get_by_label("Number of places", exact=True).fill("8")
            dialog.get_by_label("Price, USD", exact=True).fill("315.50")
            with page.expect_response(response_for(f"/manage/experiences/{tour['id']}/departures", "POST")) as result:
                dialog.get_by_role("button", name="Add a departure", exact=True).click()
            assert result.value.ok, "Creating a departure failed"
            expect(dialog.locator(".departure-list > div")).to_have_count(1)
            dialog.get_by_role("button", name="Close", exact=True).click()
            with page.expect_response(response_for(f"/manage/experiences/{tour['id']}", "PATCH")) as result:
                card.get_by_role("button", name="Publish", exact=True).click()
            assert result.value.ok, "Publishing the trip failed"
            expect(card.get_by_text("Published", exact=True)).to_be_visible()
            card.get_by_role("link", name="View trip", exact=True).click()
            expect(page).to_have_url(re.compile(r"/trips/"))
            trip_url = page.url
            for lang, values in tour_values.items():
                page.get_by_role("combobox", name="Language / Тіл / Язык", exact=True).select_option(lang)
                expect(page.get_by_role("heading", level=1)).to_have_text(values["title"])
                for day in values["itinerary"]:
                    expect(page.get_by_role("heading", name=day["title"], exact=True)).to_be_visible()
                    expect(page.get_by_text(day["description"], exact=True)).to_be_visible()
                expect(page.get_by_text(values["included"].splitlines()[0], exact=True)).to_be_visible()
                expect(page.get_by_text(values["excluded"], exact=True)).to_be_visible()
                expect(page.locator(".booking-panel select option")).to_have_count(1)
            page.get_by_role("combobox", name="Language / Тіл / Язык", exact=True).select_option("en")
            expect(page.locator(".booking-price strong")).to_have_text(re.compile(r"^\$315\.50?$"))
            print("PASS: structured multilingual itinerary, departure, publishing and public details")

            page.goto(f"{base_url}/manage")
            card.get_by_role("button", name="Edit", exact=True).click()
            for lang, values in tour_values.items():
                dialog.get_by_role("button", name=LANGUAGE_NAMES[lang], exact=True).click()
                expect(dialog.get_by_label(f"Title ({LANGUAGE_NAMES[lang]})", exact=True)).to_have_value(values["title"])
                expect(dialog.locator(".itinerary-edit-day")).to_have_count(2)
                expect(dialog.locator(".itinerary-edit-day").nth(1).get_by_label("Title", exact=True)).to_have_value(values["itinerary"][1]["title"])
            expect(dialog.get_by_label("Duration in days", exact=True)).to_be_disabled()
            dialog.get_by_role("button", name="Russian", exact=True).click()
            edited_title = f"{tour_title_ru} — обновлено"
            dialog.get_by_label("Title (Russian)", exact=True).fill(edited_title)
            save_dialog(page, dialog, f"/manage/experiences/{tour['id']}", "PATCH")
            card = page.locator(".manage-tour-card").filter(has_text=edited_title)
            expect(card).to_be_visible()
            with page.expect_response(response_for(f"/manage/experiences/{tour['id']}", "PATCH")) as result:
                card.get_by_role("button", name="Unpublish", exact=True).click()
            assert result.value.ok, "Unpublishing the trip failed"
            expect(card.get_by_text("Draft", exact=True)).to_be_visible()
            expect(card.get_by_role("link", name="View trip", exact=True)).to_have_count(0)
            card.scroll_into_view_if_needed()
            page.screenshot(path=str(artifacts / "management.png"), full_page=True)
            hidden = context.request.get(f"{base_url}/api/v1/experiences/{tour['slug']}?lang=en")
            assert hidden.status == 404, "Unpublished trip is still available publicly"
            page.goto(trip_url)
            expect(page.get_by_role("alert")).to_be_visible()
            expect(page.locator(".booking-panel")).to_have_count(0)
            print("PASS: translations survive editing; trip is unpublished and inaccessible publicly")
            check_host_workflow(browser, page, base_url, destination["id"], suffix, errors)
            assert not errors, "JavaScript errors: " + "; ".join(errors)
        except Exception:
            if errors:
                print("JavaScript errors: " + "; ".join(errors))
            page.screenshot(path=str(artifacts / "management-failure.png"), full_page=True)
            raise
        finally:
            # Leave created offers private even when an assertion interrupts the flow.
            # The success path separately verifies unpublishing through the UI.
            if created_tour_id:
                try:
                    token = page.evaluate("localStorage.getItem('sapar-token')")
                    if token:
                        context.request.patch(
                            f"{base_url}/api/v1/manage/experiences/{created_tour_id}",
                            headers={"Authorization": f"Bearer {token}"},
                            data={"is_published": False},
                        )
                except Exception:
                    pass
            browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:4173")
    run(parser.parse_args().base_url.rstrip("/"))

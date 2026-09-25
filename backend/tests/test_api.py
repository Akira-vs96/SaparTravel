from datetime import date, timedelta

import pytest
from sqlalchemy import func, select

from app.domain.models import Booking, BookingStatusHistory, Departure, Experience, Favorite, User
from app.core.security import password_hash
from tests.conftest import headers

API = "/api/v1"


def booking_body(catalog, count=2):
    return {"departure_id": catalog["departure"].id, "travelers_count": count,
            "contact_name": "Travel Guest", "contact_email": "guest@example.com", "notes": "Vegetarian meals"}


def tour_body(catalog):
    return {"title": "Новый маршрут по горам", "title_en": "A new mountain trip", "title_kk": "Жаңа тау бағыты",
            "description": "Подробное описание нового туристического маршрута.",
            "destination_id": catalog["destination"].id, "category": "Adventure", "duration_days": 2,
            "price_from": 190, "image_url": "https://example.com/new.jpg", "is_published": False,
            "itinerary": [{"day": 1, "title": "Встреча", "description": "Встреча группы в аэропорту"}]}


def test_health_and_authentication(client, db):
    assert client.get(f"{API}/health").json()["database"] == "ok"
    payload = {"name": "Ada Lovelace", "email": "Ada@example.com", "password": "Strong-password-2026"}
    response = client.post(f"{API}/auth/register", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["user"]["role"] == "traveler"
    assert body["user"]["email"] == "ada@example.com"
    assert "password_hash" not in body["user"]
    saved = db.scalar(select(User).where(User.email == "ada@example.com"))
    assert saved.password_hash != payload["password"]
    assert password_hash.verify(payload["password"], saved.password_hash)
    token = {"Authorization": "Bearer " + body["access_token"]}
    assert client.get(f"{API}/auth/me", headers=token).json()["name"] == "Ada Lovelace"
    assert client.patch(f"{API}/auth/me", headers=token, json={"name": "Ada Updated"}).status_code == 200
    assert client.post(f"{API}/auth/register", json=payload).status_code == 409
    assert client.post(f"{API}/auth/login", json={"email": payload["email"], "password": payload["password"]}).status_code == 200
    assert client.post(f"{API}/auth/login", json={"email": payload["email"], "password": "incorrect"}).status_code == 401
    assert client.get(f"{API}/auth/me", headers={"Authorization": "Bearer invalid"}).status_code == 401
    assert client.get(f"{API}/bookings").status_code == 401


def test_registration_cannot_inject_role_or_leak_password(client):
    payload = {"name": "New Traveler", "email": "new@example.com", "password": "Do-not-reflect-this-secret", "role": "admin"}
    response = client.post(f"{API}/auth/register", json=payload)
    assert response.status_code == 422
    assert payload["password"] not in response.text
    assert client.post(f"{API}/auth/register", json={**payload, "role": None}).status_code == 422


def test_catalog_translation_filters_sort_and_pagination(client, catalog, db):
    for lang, title in [("ru", "Горные тропы"), ("en", "Mountain trails"), ("kk", "Тау соқпақтары")]:
        result = client.get(f"{API}/experiences", params={"lang": lang}).json()
        assert result["items"][0]["title"] == title
        assert result["total"] == 1
        assert result["pages"] == 1
    assert client.get(f"{API}/experiences?q=Kazakhstan").json()["total"] == 1
    assert client.get(f"{API}/experiences?q=соқпақ").json()["total"] == 1
    assert client.get(f"{API}/experiences?q=Горы").json()["total"] == 1
    assert client.get(f"{API}/experiences?q=Таулар").json()["total"] == 1
    assert client.get(f"{API}/experiences?q=%25").json()["total"] == 0
    for query in ["category=Beach", "continent=Europe", "destination=rome", "min_price=251", "max_price=249", "duration_max=2"]:
        assert client.get(f"{API}/experiences?{query}").json()["total"] == 0
    assert client.get(f"{API}/experiences?min_price=100&max_price=1").status_code == 422
    assert client.get(f"{API}/experiences?page_size=101").status_code == 422
    assert client.get(f"{API}/experiences?lang=fr").status_code == 422
    another = Experience(slug="city", title="Городская прогулка", description="Подробное описание городской прогулки.",
                         destination_id=catalog["destination"].id, vendor_id=catalog["vendor"].id, category="City",
                         duration_days=1, price_from=90, image_url="https://example.com/city.jpg")
    db.add(another)
    db.commit()
    result = client.get(f"{API}/experiences?sort=price_asc&page_size=1").json()
    assert result["items"][0]["price_from"] == 90
    assert result["total"] == 2 and result["pages"] == 2
    assert client.get(f"{API}/experiences?sort=price_desc").json()["items"][0]["price_from"] == 250
    destinations = client.get(f"{API}/destinations?lang=kk").json()["items"]
    assert destinations[0]["country"] == "Қазақстан"
    assert destinations[0]["tour_count"] == 2
    detail = client.get(f"{API}/experiences/mountain-trails?lang=en").json()
    assert detail["departures"][0]["available_seats"] == 4
    assert detail["included"] == ["Guide"]


def test_favorites_persist_are_private_and_idempotent(client, catalog, db):
    auth = headers(catalog["traveler"])
    path = f"{API}/favorites/{catalog['tour'].id}"
    assert client.put(path, headers=auth).status_code == 204
    assert client.put(path, headers=auth).status_code == 204
    assert db.scalar(select(func.count()).select_from(Favorite)) == 1
    assert len(client.get(f"{API}/favorites", headers=auth).json()["items"]) == 1
    assert client.get(f"{API}/favorites", headers=headers(catalog["other"])).json()["items"] == []
    assert client.delete(path, headers=auth).status_code == 204
    assert client.delete(path, headers=auth).status_code == 204
    assert client.get(f"{API}/favorites", headers=auth).json()["items"] == []


def test_booking_price_seats_ownership_cancellation_and_history(client, catalog, db):
    auth = headers(catalog["traveler"])
    response = client.post(f"{API}/bookings", headers=auth, json=booking_body(catalog, 3))
    assert response.status_code == 201
    booking = response.json()
    assert booking["total_amount"] == 826.5
    assert booking["payment_status"] == "pay_on_confirmation"
    assert booking["status"] == "pending"
    assert client.get(f"{API}/experiences/mountain-trails").json()["departures"][0]["available_seats"] == 1
    assert client.post(f"{API}/bookings", headers=auth, json=booking_body(catalog, 2)).status_code == 409
    assert client.get(f"{API}/bookings", headers=headers(catalog["other"])).json()["items"] == []
    cancel_path = f"{API}/bookings/{booking['id']}/cancel"
    assert client.post(cancel_path, headers=headers(catalog["other"])).status_code == 404
    assert client.post(cancel_path, headers=auth).json()["status"] == "cancelled"
    assert client.post(cancel_path, headers=auth).status_code == 200
    assert client.get(f"{API}/experiences/mountain-trails").json()["departures"][0]["available_seats"] == 4
    assert db.scalar(select(func.count()).select_from(BookingStatusHistory)) == 2


def test_booking_validates_dates_quantity_and_rejects_client_total(client, catalog, db):
    auth = headers(catalog["traveler"])
    for count in [0, -1, 21, 1.5, True]:
        assert client.post(f"{API}/bookings", headers=auth, json=booking_body(catalog, count)).status_code == 422
    assert client.post(f"{API}/bookings", headers=auth, json={**booking_body(catalog), "total_amount": 1}).status_code == 422
    catalog["departure"].start_date = date.today()
    db.commit()
    assert client.post(f"{API}/bookings", headers=auth, json=booking_body(catalog)).status_code == 409


def test_booking_snapshot_survives_catalog_changes(client, catalog, db):
    auth = headers(catalog["traveler"])
    booked = client.post(f"{API}/bookings?lang=en", headers=auth, json=booking_body(catalog)).json()
    catalog["tour"].title_en = "Changed later"
    catalog["tour"].price_from = 999
    db.commit()
    stored = client.get(f"{API}/bookings?lang=en", headers=auth).json()["items"][0]
    assert stored["experience"]["title"] == "Mountain trails"
    assert stored["total_amount"] == booked["total_amount"]


def test_vendor_crud_permissions_and_localized_management(client, catalog, db):
    vendor = headers(catalog["vendor"])
    assert client.get(f"{API}/manage/experiences", headers=headers(catalog["traveler"])).status_code == 403
    created = client.post(f"{API}/manage/experiences", headers=vendor, json=tour_body(catalog))
    assert created.status_code == 201, created.text
    tour = created.json()
    assert client.get(f"{API}/experiences/{tour['slug']}").status_code == 404
    path = f"{API}/manage/experiences/{tour['id']}"
    assert client.patch(path, headers=headers(catalog["other_vendor"]), json={"title": "Чужое изменение"}).status_code == 404
    assert client.patch(path, headers=vendor, json={"title": None}).status_code == 422
    assert client.patch(path, headers=vendor, json={"is_published": True}).status_code == 200
    assert client.get(f"{API}/experiences/{tour['slug']}").status_code == 200
    details = client.get(f"{API}/manage/experiences?lang=en", headers=vendor).json()["items"]
    managed = next(item for item in details if item["id"] == tour["id"])
    assert managed["title"] == tour_body(catalog)["title"]
    assert managed["title_kk"] == tour_body(catalog)["title_kk"]
    assert managed["destination_id"] == catalog["destination"].id
    departure = {"start_date": str(date.today() + timedelta(days=30)), "capacity": 8, "price": 205.25}
    result = client.post(path + "/departures", headers=vendor, json=departure)
    assert result.status_code == 201
    assert result.json()["end_date"] == str(date.today() + timedelta(days=31))
    assert client.post(path + "/departures", headers=vendor, json=departure).status_code == 409
    assert client.patch(path, headers=vendor, json={"duration_days": 5}).status_code == 409
    assert client.post(path + "/departures", headers=vendor, json={**departure, "start_date": str(date.today())}).status_code == 422
    assert client.post(f"{API}/manage/experiences", headers=vendor,
                       json={**tour_body(catalog), "itinerary": [{"day": 3, "title": "Bad", "description": "Outside duration"}]}).status_code == 422


def test_manage_bookings_scope_and_state_machine(client, catalog):
    booked = client.post(f"{API}/bookings", headers=headers(catalog["traveler"]), json=booking_body(catalog)).json()
    path = f"{API}/manage/bookings/{booked['id']}"
    assert client.get(f"{API}/manage/bookings", headers=headers(catalog["other_vendor"])).json()["items"] == []
    assert client.patch(path, headers=headers(catalog["other_vendor"]), json={"status": "confirmed"}).status_code == 404
    vendor = headers(catalog["vendor"])
    assert client.patch(path, headers=vendor, json={"status": "completed"}).status_code == 409
    assert client.patch(path, headers=vendor, json={"status": "confirmed"}).json()["status"] == "confirmed"
    assert client.patch(path, headers=vendor, json={"status": "completed"}).status_code == 409
    assert client.patch(path, headers=vendor, json={"status": "cancelled"}).status_code == 200
    assert client.patch(path, headers=vendor, json={"status": "confirmed"}).status_code == 409


def test_admin_role_updates_and_last_admin_protection(client, catalog):
    admin = headers(catalog["admin"])
    assert client.get(f"{API}/admin/users", headers=headers(catalog["vendor"])).status_code == 403
    assert client.patch(f"{API}/admin/users/{catalog['admin'].id}", headers=admin, json={"role": "traveler"}).status_code == 409
    target = f"{API}/admin/users/{catalog['traveler'].id}"
    assert client.patch(target, headers=admin, json={"role": "vendor"}).json()["role"] == "vendor"
    # The token contains identity only; changed roles take effect immediately.
    assert client.get(f"{API}/manage/experiences", headers=headers(catalog["traveler"])).status_code == 200
    assert client.patch(target, headers=admin, json={"role": "admin"}).status_code == 200
    assert client.patch(f"{API}/admin/users/{catalog['admin'].id}", headers=admin, json={"role": "traveler"}).status_code == 200
    assert client.get(f"{API}/admin/users", headers=admin).status_code == 403


def test_admin_can_expand_destinations(client, catalog):
    payload = {"slug": "rome", "name": "Рим", "name_en": "Rome", "name_kk": "Рим", "country": "Италия",
               "country_en": "Italy", "country_kk": "Италия", "continent": "Europe",
               "description": "История, архитектура и итальянская кухня в Риме.", "image_url": "https://example.com/rome.jpg"}
    assert client.post(f"{API}/manage/destinations", headers=headers(catalog["vendor"]), json=payload).status_code == 403
    response = client.post(f"{API}/manage/destinations", headers=headers(catalog["admin"]), json=payload)
    assert response.status_code == 201
    assert client.post(f"{API}/manage/destinations", headers=headers(catalog["admin"]), json=payload).status_code == 409
    assert client.patch(f"{API}/manage/destinations/{response.json()['id']}", headers=headers(catalog["admin"]),
                        json={"name_kk": "Рим қаласы"}).status_code == 200
    assert len(client.get(f"{API}/destinations").json()["items"]) == 2


def test_unpublished_tours_cannot_be_booked_or_favorited(client, catalog, db):
    catalog["tour"].is_published = False
    db.commit()
    auth = headers(catalog["traveler"])
    assert client.get(f"{API}/experiences").json()["total"] == 0
    assert client.post(f"{API}/bookings", headers=auth, json=booking_body(catalog)).status_code == 404
    assert client.put(f"{API}/favorites/{catalog['tour'].id}", headers=auth).status_code == 404


def test_completed_trip_is_terminal_and_cannot_be_cancelled(client, catalog, db):
    traveler = headers(catalog["traveler"])
    booking = client.post(f"{API}/bookings", headers=traveler, json=booking_body(catalog)).json()
    path = f"{API}/manage/bookings/{booking['id']}"
    vendor = headers(catalog["vendor"])
    assert client.patch(path, headers=vendor, json={"status": "confirmed"}).status_code == 200
    stored = db.get(Booking, booking["id"])
    stored.start_date = date.today() - timedelta(days=3)
    stored.end_date = date.today() - timedelta(days=1)
    db.commit()
    assert client.patch(path, headers=vendor, json={"status": "completed"}).json()["status"] == "completed"
    assert client.patch(path, headers=vendor, json={"status": "cancelled"}).status_code == 409
    assert client.post(f"{API}/bookings/{booking['id']}/cancel", headers=traveler).status_code == 409


def test_inactive_account_cannot_authenticate(client, catalog, db):
    token = headers(catalog["traveler"])
    catalog["traveler"].is_active = False
    db.commit()
    assert client.get(f"{API}/auth/me", headers=token).status_code == 401
    assert client.post(f"{API}/auth/login", json={"email": "traveler@example.com", "password": "Correct-password-2026"}).status_code == 401

"""Behavioral checks for credential revocation, owned support and verified reviews."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from hashlib import sha256
import re

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.domain.engagement import DemoEmail, PasswordReset, Review, SupportMessage, SupportTicket
from app.domain.models import Booking, Experience, User, utc_now
from app.services.engagement_service import emit_event
from tests.conftest import headers

API = "/api/v1"


def make_booking(db, catalog, status="completed"):
    booking = Booking(reference="SAP-ENGAGEMENT-TEST", user_id=catalog["traveler"].id,
                      departure_id=catalog["departure"].id, status=status, travelers_count=1,
                      total_amount=100000, subtotal_amount=100000, discount_amount=0, currency="KZT", contact_name="Test Traveler", contact_email="traveler@example.com",
                      notes="", experience_snapshot={"ru": {"title": "Test trip"}},
                      start_date=date.today() - timedelta(days=5), end_date=date.today() - timedelta(days=2))
    db.add(booking)
    db.commit()
    return booking


def reset_token(client, db, email):
    response = client.post(f"{API}/auth/forgot-password", json={"email": email})
    assert response.status_code == 200
    email_message = db.scalar(select(DemoEmail).where(DemoEmail.recipient == email).order_by(DemoEmail.created_at.desc()))
    return re.search(r"token=([A-Za-z0-9_-]+)", email_message.body).group(1)


def test_logout_and_password_change_revoke_access(client, catalog):
    traveler = headers(catalog["traveler"])
    assert client.get(f"{API}/auth/me", headers=traveler).status_code == 200
    assert client.post(f"{API}/auth/logout", headers=traveler).status_code == 204
    assert client.get(f"{API}/auth/me", headers=traveler).status_code == 401
    first = client.post(f"{API}/auth/login", json={"email": "traveler@example.com", "password": "Correct-password-2026"}).json()
    second = client.post(f"{API}/auth/login", json={"email": "traveler@example.com", "password": "Correct-password-2026"}).json()
    auth = {"Authorization": "Bearer " + first["access_token"]}
    assert client.post(f"{API}/auth/change-password", headers=auth,
                       json={"current_password": "incorrect", "new_password": "Replacement-2026-password"}).status_code == 422
    changed = client.post(f"{API}/auth/change-password", headers=auth,
                          json={"current_password": "Correct-password-2026", "new_password": "Replacement-2026-password"})
    assert changed.status_code == 200
    assert client.get(f"{API}/auth/me", headers=auth).status_code == 401
    assert client.get(f"{API}/auth/me", headers={"Authorization": "Bearer " + second["access_token"]}).status_code == 401
    assert client.get(f"{API}/auth/me", headers={"Authorization": "Bearer " + changed.json()["access_token"]}).status_code == 200
    assert client.post(f"{API}/auth/login", json={"email": "traveler@example.com", "password": "Correct-password-2026"}).status_code == 401


def test_password_reset_is_private_one_use_expires_and_revokes_sessions(client, catalog, db, monkeypatch):
    original_auth = headers(catalog["traveler"])
    known = client.post(f"{API}/auth/forgot-password", json={"email": "traveler@example.com"})
    unknown = client.post(f"{API}/auth/forgot-password", json={"email": "nobody@example.com"})
    assert known.json() == unknown.json()
    assert client.get(f"{API}/admin/demo-mailbox", headers=original_auth).status_code == 403
    assert client.get(f"{API}/admin/demo-mailbox", headers=headers(catalog["admin"])).status_code == 404
    monkeypatch.setattr(get_settings(), "demo_mailbox_enabled", True)
    mailbox = client.get(f"{API}/admin/demo-mailbox?recipient=traveler@example.com", headers=headers(catalog["admin"]))
    assert mailbox.status_code == 200
    assert len(mailbox.json()["items"]) == 1
    token = re.search(r"token=([A-Za-z0-9_-]+)", mailbox.json()["items"][0]["body"]).group(1)
    reset = db.scalar(select(PasswordReset).where(PasswordReset.token_hash == sha256(token.encode()).hexdigest()))
    assert reset.token_hash != token
    reset.expires_at = utc_now() - timedelta(seconds=1)
    db.commit()
    body = {"token": token, "new_password": "New-password-for-reset-2026"}
    assert client.post(f"{API}/auth/reset-password", json=body).status_code == 422
    token = reset_token(client, db, "traveler@example.com")
    body["token"] = token
    assert client.post(f"{API}/auth/reset-password", json=body).status_code == 200
    assert client.post(f"{API}/auth/reset-password", json=body).status_code == 422
    assert client.get(f"{API}/auth/me", headers=original_auth).status_code == 401
    assert client.post(f"{API}/auth/login", json={"email": "traveler@example.com", "password": body["new_password"]}).status_code == 200


def test_notifications_and_saved_searches_are_owned_persisted_resources(client, catalog, db):
    traveler = headers(catalog["traveler"])
    other = headers(catalog["other"])
    notification = emit_event(db, catalog["traveler"].id, "booking.created", "Бронь", "Создана бронь",
                              title_en="Booking", body_en="Booking created", title_kk="Бронь", body_kk="Бронь жасалды")
    db.commit()
    listing = client.get(f"{API}/notifications?lang=en", headers=traveler).json()
    assert listing["unread_count"] == 1 and listing["items"][0]["title"] == "Booking"
    assert client.post(f"{API}/notifications/{notification.id}/read", headers=other).status_code == 404
    assert client.post(f"{API}/notifications/{notification.id}/read", headers=traveler).json()["is_read"] is True
    assert client.get(f"{API}/notifications", headers=traveler).json()["unread_count"] == 0
    created = client.post(f"{API}/saved-searches", headers=traveler,
                          json={"name": "Almaty under budget", "filters": {"destination": "almaty", "max_price": "150000", "sort": "price_asc"}})
    assert created.status_code == 201
    search = created.json()
    assert client.get(f"{API}/saved-searches", headers=traveler).json()["items"][0]["filters"] == search["filters"]
    assert client.get(f"{API}/saved-searches", headers=other).json()["items"] == []
    assert client.delete(f"{API}/saved-searches/{search['id']}", headers=other).status_code == 404
    assert client.delete(f"{API}/saved-searches/{search['id']}", headers=traveler).status_code == 204
    assert client.post(f"{API}/saved-searches", headers=traveler, json={"name": "Bad filter", "filters": {"script": "no"}}).status_code == 422


def test_support_replies_status_and_vendor_ownership(client, catalog, db):
    booking = make_booking(db, catalog)
    traveler = headers(catalog["traveler"])
    vendor = headers(catalog["vendor"])
    other = headers(catalog["other_vendor"])
    created = client.post(f"{API}/support/tickets", headers=traveler,
                          json={"subject": "Cancellation terms", "body": "Please explain the cancellation policy.", "booking_id": booking.id})
    assert created.status_code == 201
    ticket_id = created.json()["id"]
    path = f"{API}/support/tickets/{ticket_id}"
    assert client.get(path, headers=other).status_code == 404
    assert client.get(f"{API}/support/tickets", headers=other).json()["items"] == []
    assert client.post(path + "/messages", headers=other, json={"body": "Unauthorized answer"}).status_code == 404
    assert client.patch(path + "/status", headers=traveler, json={"status": "resolved"}).status_code == 403
    assert client.post(path + "/messages", headers=vendor, json={"body": "Your policy is recorded in your booking."}).status_code == 201
    detail = client.get(path, headers=traveler).json()
    assert len(detail["messages"]) == 2
    assert detail["messages"][1]["author_role"] == "vendor"
    assert client.get(f"{API}/notifications", headers=traveler).json()["unread_count"] == 1
    assert client.patch(path + "/status", headers=vendor, json={"status": "resolved"}).json()["status"] == "resolved"
    assert client.post(path + "/messages", headers=traveler, json={"body": "I have another question."}).status_code == 201
    assert client.get(path, headers=traveler).json()["status"] == "open"
    assert client.patch(path + "/status", headers=traveler, json={"status": "closed"}).status_code == 200
    assert client.post(path + "/messages", headers=vendor, json={"body": "Closed request"}).status_code == 409
    assert client.patch(path + "/status", headers=traveler, json={"status": "open"}).status_code == 200
    assert client.get(f"{API}/support/tickets", headers=headers(catalog["admin"])).json()["items"][0]["id"] == ticket_id
    assert client.post(f"{API}/support/tickets", headers=headers(catalog["other"]), json={"subject": "Foreign booking", "body": "Cannot read it", "booking_id": booking.id}).status_code == 404


def test_review_requires_completed_owned_trip_unique_booking_and_moderation(client, catalog, db):
    booking = make_booking(db, catalog, "confirmed")
    traveler = headers(catalog["traveler"])
    body = {"booking_id": booking.id, "rating": 5, "title": "Memorable journey", "text": "A wonderful journey with a thoughtful guide."}
    assert client.post(f"{API}/reviews", headers=traveler, json=body).status_code == 409
    assert client.post(f"{API}/reviews", headers=headers(catalog["other"]), json=body).status_code == 404
    booking.status = "completed"
    booking.end_date = date.today() + timedelta(days=1)
    db.commit()
    assert client.post(f"{API}/reviews", headers=traveler, json=body).status_code == 409
    booking.end_date = date.today() - timedelta(days=1)
    db.commit()
    created = client.post(f"{API}/reviews", headers=traveler, json=body)
    assert created.status_code == 201
    assert created.json()["status"] == "pending"
    assert client.post(f"{API}/reviews", headers=traveler, json=body).status_code == 409
    public = f"{API}/experiences/{catalog['tour'].id}/reviews"
    assert client.get(public).json()["items"] == []
    assert client.get(f"{API}/manage/reviews", headers=headers(catalog["other_vendor"])).json()["items"] == []
    review_id = created.json()["id"]
    moderation = f"{API}/admin/reviews/{review_id}"
    assert client.patch(moderation, headers=headers(catalog["vendor"]), json={"status": "approved"}).status_code == 403
    assert client.patch(moderation, headers=headers(catalog["admin"]), json={"status": "approved"}).status_code == 200
    approved = client.get(public).json()
    assert approved["rating"] == 5 and approved["review_count"] == 1
    assert approved["items"][0]["verified_trip"] is True
    db.refresh(catalog["tour"])
    assert catalog["tour"].rating == 5 and catalog["tour"].review_count == 1
    assert client.patch(moderation, headers=headers(catalog["admin"]), json={"status": "rejected"}).status_code == 200
    db.refresh(catalog["tour"])
    assert catalog["tour"].rating == 0 and catalog["tour"].review_count == 0


def test_last_active_admin_and_immediate_blocking_are_enforced(client, catalog, db):
    admin = headers(catalog["admin"])
    assert client.patch(f"{API}/admin/users/{catalog['admin'].id}", headers=admin, json={"is_active": False}).status_code == 409
    traveler = headers(catalog["traveler"])
    outstanding_reset = reset_token(client, db, "traveler@example.com")
    target = f"{API}/admin/users/{catalog['traveler'].id}"
    blocked = client.patch(target, headers=admin, json={"is_active": False})
    assert blocked.status_code == 200
    assert client.get(f"{API}/auth/me", headers=traveler).status_code == 401
    assert client.post(f"{API}/auth/login", json={"email": "traveler@example.com", "password": "Correct-password-2026"}).status_code == 401
    unblocked = client.patch(target, headers=admin, json={"is_active": True, "role": "vendor"})
    assert unblocked.status_code == 200
    assert client.get(f"{API}/manage/experiences", headers=traveler).status_code == 401
    assert client.post(f"{API}/auth/reset-password", json={"token": outstanding_reset, "new_password": "Should-not-be-accepted-2026"}).status_code == 422
    new_token = client.post(f"{API}/auth/login", json={"email": "traveler@example.com", "password": "Correct-password-2026"}).json()["access_token"]
    assert client.get(f"{API}/manage/experiences", headers={"Authorization": "Bearer " + new_token}).status_code == 200
    log = client.get(f"{API}/admin/audit?action=user.updated", headers=admin).json()
    assert len(log["items"]) == 2
    assert blocked.headers["X-Request-ID"] != unblocked.headers["X-Request-ID"]
    assert {row["details"]["request_id"] for row in log["items"]} == {
        blocked.headers["X-Request-ID"], unblocked.headers["X-Request-ID"]}
    assert all(row["actor_id"] == catalog["admin"].id and row["resource_id"] == catalog["traveler"].id
               and row["created_at"] for row in log["items"])
    assert client.get(f"{API}/admin/audit", headers={"Authorization": "Bearer " + new_token}).status_code == 403


def test_parallel_password_reset_has_exactly_one_redemption(client, catalog, db):
    if db.bind.dialect.name != "postgresql":
        pytest.skip("Reset serialization must be checked on PostgreSQL")
    token = reset_token(client, db, "traveler@example.com")
    body = {"token": token, "new_password": "Concurrent-reset-password-2026"}
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: client.post(f"{API}/auth/reset-password", json=body).status_code, range(2)))
    assert sorted(results) == [200, 422]


def test_categories_support_real_crud_and_reject_deleting_used_category(client, catalog):
    admin = headers(catalog["admin"])
    payload = {"code": "Wellness", "name_ru": "Оздоровление", "name_en": "Wellness", "name_kk": "Сауықтыру"}
    assert client.post(f"{API}/admin/categories", headers=headers(catalog["vendor"]), json=payload).status_code == 403
    assert client.post(f"{API}/admin/categories", headers=admin, json=payload).status_code == 201
    assert client.post(f"{API}/admin/categories", headers=admin, json=payload).status_code == 409
    assert any(item["name"] == "Сауықтыру" for item in client.get(f"{API}/categories?lang=kk").json()["items"])
    assert client.patch(f"{API}/admin/categories/Wellness", headers=admin, json={"name_en": "Wellness retreats"}).status_code == 200
    assert client.delete(f"{API}/admin/categories/Nature", headers=admin).status_code == 409
    assert client.delete(f"{API}/admin/categories/Wellness", headers=admin).status_code == 204


def test_support_history_is_bounded_paginated_and_owned(client, catalog, db):
    ticket = SupportTicket(user_id=catalog["traveler"].id, subject="Long conversation")
    db.add(ticket)
    db.flush()
    for index in range(125):
        db.add(SupportMessage(ticket_id=ticket.id, author_id=catalog["traveler"].id,
                              author_role="traveler", body=f"Message {index:03}",
                              created_at=utc_now() + timedelta(seconds=index)))
    db.commit()
    auth = headers(catalog["traveler"])
    path = f"{API}/support/tickets/{ticket.id}"
    detail = client.get(path, headers=auth).json()
    assert len(detail["messages"]) == 100
    assert detail["messages_total"] == 125 and detail["has_more_messages"] is True
    assert detail["messages"][0]["body"] == "Message 025"
    page = client.get(path + "/messages?limit=20&offset=20", headers=auth).json()
    assert len(page["items"]) == 20 and page["total"] == 125
    assert page["items"][0]["body"] == "Message 020"
    assert client.get(path + "/messages", headers=headers(catalog["other"])).status_code == 404
    assert client.get(path + "/messages?limit=101", headers=auth).status_code == 422
    assert client.get(f"{API}/notifications?offset=1000001", headers=auth).status_code == 422
    assert client.post(path + "/messages", headers=auth, json={"body": "x" * 5001}).status_code == 422
    assert client.post(f"{API}/saved-searches", headers=auth,
                       json={"name": "Party size", "filters": {"travelers": "2", "page": "2", "category": "Nature"}}).status_code == 201


def test_parallel_admin_demotions_preserve_one_active_admin(client, catalog, db):
    if db.bind.dialect.name != "postgresql":
        pytest.skip("Administrator serialization must be checked on PostgreSQL")
    second = catalog["other"]
    second.role = "admin"
    db.commit()
    targets = [(catalog["admin"].id, headers(catalog["admin"])), (second.id, headers(second))]
    def demote(target):
        user_id, auth = target
        return client.patch(f"{API}/admin/users/{user_id}", headers=auth, json={"role": "traveler"}).status_code
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(demote, targets))
    assert sorted(results) == [200, 409]
    assert len(db.scalars(select(User).where(User.role == "admin", User.is_active.is_(True))).all()) == 1

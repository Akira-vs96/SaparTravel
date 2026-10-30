from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.core.clock import at_time
from app.core.config import get_settings
from app.domain.engagement import SupportTicket
from app.domain.models import Booking, CategoryRecord
from app.services import support_service as support
from tests.conftest import headers
from tests.test_commerce import book, pay

CALENDAR = {"id": "agreed-fixture-v1", "timezone": "Asia/Almaty", "approved": True,
            "approval_reference": "acceptance fixture, not a real service agreement",
            "valid_from": "2026-01-01", "valid_until": "2027-12-31", "holidays": [], "working_days": []}


def test_friday_deadline_holiday_and_working_weekend():
    friday = datetime.fromisoformat("2026-10-30T17:55:00+05:00")
    assert support.response_deadline(friday, "P1", CALENDAR) == datetime.fromisoformat("2026-11-02T09:10:00+05:00")
    holiday = {**CALENDAR, "holidays": ["2026-11-02"]}
    deadline = support.response_deadline(friday, "P1", holiday)
    assert deadline == datetime.fromisoformat("2026-11-03T09:10:00+05:00")
    assert support.working_seconds(friday, deadline, holiday) == 900
    weekend = {**CALENDAR, "working_days": ["2026-10-31"]}
    assert support.response_deadline(friday, "P1", weekend) == datetime.fromisoformat("2026-10-31T09:10:00+05:00")


def test_response_month_is_selected_by_deadline_and_missing_response_is_breach():
    created = datetime.fromisoformat("2026-10-30T17:55:00+05:00")
    row = SimpleNamespace(priority="P1", created_at=created, response_due_at=support.response_deadline(created, "P1", CALENDAR),
                          first_response_at=None, response_calendar=CALENDAR)
    now = datetime.fromisoformat("2026-12-01T00:00:00+05:00")
    october = support.response_report([row], "2026-10", now=now)
    assert october["priorities"]["P1"]["percent"] is None
    november = support.response_report([row], "2026-11", now=now)
    assert november["priorities"]["P1"] == {"eligible": 1, "on_time": 0, "breaches": 1, "percent": 0.0, "status": "measured"}
    row.first_response_at = row.response_due_at
    assert support.response_report([row], "2026-11", now=now)["priorities"]["P1"]["percent"] == 100
    row.first_response_at += timedelta(microseconds=1)
    assert support.response_report([row], "2026-11", now=now)["priorities"]["P1"]["breaches"] == 1


def test_support_acknowledgement_requires_staff_content_and_preserves_first_response(client, catalog, tmp_path, monkeypatch):
    path = tmp_path / "calendar.json"
    path.write_text(json.dumps(CALENDAR))
    monkeypatch.setattr(get_settings(), "support_calendar_file", str(path))
    traveler, admin = headers(catalog["traveler"]), headers(catalog["admin"])
    with at_time(datetime.fromisoformat("2026-10-30T17:55:00+05:00")):
        created = client.post("/api/v1/support/tickets", headers=traveler,
                              json={"subject": "Catalog unavailable", "body": "Please investigate this outage.", "priority": "P1"})
    assert created.status_code == 201, created.text
    ticket = created.json()
    assert ticket["response_due_at"] == "2026-11-02T04:10:00+00:00"
    endpoint = "/api/v1/support/tickets/" + ticket["id"]
    assert client.post(endpoint + "/messages", headers=traveler, json={"body": "I accept my own incident and will fix it", "acknowledge": True}).status_code == 403
    assert client.post(endpoint + "/messages", headers=admin, json={"body": "OK", "acknowledge": True}).status_code == 422
    with at_time(datetime.fromisoformat("2026-11-02T09:11:00+05:00")):
        assert client.patch(endpoint + "/priority", headers=admin, json={"priority": "P3"}).status_code == 409
    with at_time(datetime.fromisoformat("2026-11-02T09:09:00+05:00")):
        assert client.post(endpoint + "/messages", headers=admin, json={"body": "P1 accepted. We are checking the catalog database.", "acknowledge": True}).status_code == 201
    first = client.get(endpoint, headers=traveler).json()
    assert first["response_working_minutes"] == 14
    assert client.patch(endpoint + "/priority", headers=admin, json={"priority": "P3"}).status_code == 409
    client.post(endpoint + "/messages", headers=admin, json={"body": "Still checking the connection; next update shortly.", "acknowledge": True})
    assert client.get(endpoint, headers=traveler).json()["first_response_at"] == first["first_response_at"]
    with at_time(datetime.fromisoformat("2026-12-01T00:00:00+05:00")):
        report = client.get("/api/v1/manage/support-metrics?month=2026-11", headers=admin)
    assert report.status_code == 200
    assert report.json()["priorities"]["P1"]["percent"] == 100
    assert report.json()["sla_evaluable"] is True
    evidence = client.get("/api/v1/manage/support-metrics/evidence?month=2026-11", headers=admin)
    assert evidence.status_code == 200
    assert evidence.json()["items"][0]["response_working_seconds"] == 840
    assert all(key not in evidence.text for key in ("author_name", "contact_email", "Catalog unavailable"))
    assert client.get("/api/v1/manage/support-metrics?month=2026-11", headers=traveler).status_code == 403


def test_cancellation_quote_matches_manager_action_and_subtracts_committed_refunds(client, catalog):
    booking = book(client, catalog)
    assert pay(client, catalog, booking["id"]).status_code == 200
    base = "/api/v1/manage/bookings/" + booking["id"]
    admin = headers(catalog["admin"])
    refunded = client.post(base + "/refunds", headers={**admin, "Idempotency-Key": "quote-partial-refund"},
                           json={"amount": "25.50", "reason": "Partial refund before cancellation"})
    assert refunded.status_code == 201
    quote = client.get(base + "/cancellation-quote", headers=admin)
    assert quote.status_code == 200
    expected = Decimal(booking["total_amount"]) - Decimal("25.50")
    assert Decimal(quote.json()["amount"]) == expected
    assert quote.json()["refund_percent"] == 100
    assert client.get(base + "/cancellation-quote", headers=headers(catalog["other_vendor"])).status_code == 404
    result = client.patch(base, headers=admin, json={"status": "cancelled", "reason": "Organizer cancellation with full refund"}).json()
    assert Decimal(result["refunded_amount"]) == Decimal(booking["total_amount"])
    assert Decimal(result["refunds"][-1]["amount"]) == expected


def test_promocode_supports_new_category_and_rejects_unknown_scope(client, catalog, db):
    db.add(CategoryRecord(code="Wellness", name_ru="Здоровье", name_en="Wellness", name_kk="Денсаулық"))
    db.commit()
    now = datetime.now(timezone.utc)
    body = {"code": "WELLNESS10", "kind": "percent", "value": "10", "starts_at": (now - timedelta(days=1)).isoformat(),
            "ends_at": (now + timedelta(days=1)).isoformat(), "category": "Wellness"}
    result = client.post("/api/v1/manage/promocodes", headers=headers(catalog["admin"]), json=body)
    assert result.status_code == 201, result.text
    assert result.json()["category"] == "Wellness"
    assert client.post("/api/v1/manage/promocodes", headers=headers(catalog["admin"]), json={**body, "code": "UNKNOWN", "category": "Unknown"}).status_code == 422


def test_synthetic_monitoring_is_hidden_isolated_and_excluded_from_analytics(client, catalog, db):
    catalog["tour"].is_monitoring = True
    db.commit()
    assert client.get("/api/v1/catalog").json()["total"] == 0
    assert client.get("/api/v1/recommendations").json()["total"] == 0
    from tests.test_api import booking_body
    assert client.post("/api/v1/bookings", headers=headers(catalog["traveler"]), json=booking_body(catalog, 1)).status_code == 403
    catalog["traveler"].is_monitoring = True
    db.commit()
    booking = book(client, catalog)
    assert db.get(Booking, booking["id"]).is_synthetic is True
    analytics = client.get("/api/v1/manage/analytics", headers=headers(catalog["admin"])).json()
    assert analytics["bookings_count"] == 0 and analytics["capacity"] == 0
    csv = client.get("/api/v1/manage/analytics.csv", headers=headers(catalog["admin"])).text
    assert booking["reference"] not in csv

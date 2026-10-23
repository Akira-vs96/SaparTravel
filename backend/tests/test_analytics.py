import csv
from datetime import date
from io import StringIO

from tests.conftest import headers
from tests.test_api import booking_body, pay_booking


API = "/api/v1"


def test_scoped_analytics_distinguishes_orders_receipts_and_refunds(client, catalog):
    traveler = headers(catalog["traveler"])
    vendor = headers(catalog["vendor"])
    other_vendor = headers(catalog["other_vendor"])
    booking = client.post(API + "/bookings", headers=traveler, json={**booking_body(catalog), "contact_name": "=SUM(A1:A2)"}).json()
    unpaid = client.get(API + "/manage/analytics", headers=vendor).json()
    assert unpaid["bookings_count"] == 1 and unpaid["successful_payments"] == "0.00"
    assert unpaid["turnover"] == "0.00" and unpaid["occupied_seats"] == 2
    pay_booking(client, catalog, booking)
    paid = client.get(API + "/manage/analytics", headers=vendor).json()
    assert paid["turnover"] == "551.00" and paid["successful_payments"] == "551.00"
    assert paid["refunds_amount"] == "0.00" and paid["net_received"] == "551.00"
    assert paid["platform_revenue"] is None
    assert client.get(API + "/manage/analytics", headers=other_vendor).json()["bookings_count"] == 0
    assert client.get(API + "/manage/analytics", headers=traveler).status_code == 403
    assert client.get(API + "/manage/analytics?from=2030-01-02&to=2030-01-01", headers=vendor).status_code == 422
    exported = client.get(API + "/manage/analytics.csv", headers=vendor)
    assert exported.status_code == 200
    rows = list(csv.DictReader(StringIO(exported.text.lstrip("\ufeff"))))
    assert rows[0]["contact_name"] == "'=SUM(A1:A2)"
    assert rows[0]["paid"] == "551.00" and rows[0]["currency"] == "KZT"
    assert len(list(csv.DictReader(StringIO(client.get(API + "/manage/analytics.csv", headers=other_vendor).text.lstrip("\ufeff"))))) == 0
    client.post(API + f"/bookings/{booking['id']}/cancel", headers=traveler)
    cancelled = client.get(API + "/manage/analytics", headers=vendor).json()
    assert cancelled["successful_payments"] == "551.00" and cancelled["refunds_amount"] == "551.00"
    assert cancelled["net_received"] == "0.00" and cancelled["occupied_seats"] == 0

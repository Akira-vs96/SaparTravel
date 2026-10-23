"""Full purchasing lifecycle and PostgreSQL concurrency checks."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from threading import Barrier
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from app.db import SessionLocal, engine
from app.domain.models import Booking, Departure, ExperienceService, PaymentAttempt, PromoCode, ProviderOperation, Refund
from app.main import app
from app.services import commerce_service as commerce
from tests.conftest import headers
from tests.test_api import booking_body
API = "/api/v1"


def card(number="4242424242424242", **changes):
    current = commerce.today()
    return {"card_number": number, "holder_name": "Test Traveler", "expiry_month": current.month, "expiry_year": current.year, "cvc": "123", **changes}


def book(client, catalog, **changes):
    response = client.post(f"{API}/bookings", headers=headers(catalog["traveler"]), json={**booking_body(catalog, 1), **changes})
    assert response.status_code == 201, response.text
    return response.json()


def pay(client, catalog, booking_id, number="4242424242424242", key=None, **changes):
    return client.post(f"{API}/bookings/{booking_id}/payments", headers={**headers(catalog["traveler"]), "Idempotency-Key": key or str(uuid4())}, json=card(number, **changes))


def detail(client,catalog,bid):
    return client.get(f"{API}/bookings/{bid}",headers=headers(catalog["traveler"])).json()


def test_checkout_price_snapshot_idempotency_and_documents(client,catalog,db):
    service=ExperienceService(experience_id=catalog["tour"].id,name="Transfer",price=Decimal("100.25"),per_person=False)
    db.add(service);db.commit()
    booking=book(client,catalog,travelers_count=2,participants=[{"name":"First Traveler"},{"name":"Second Traveler"}],service_ids=[service.id])
    assert booking["total_amount"]=="651.25" and booking["currency"]=="KZT"
    assert len(booking["items"])==2 and len(booking["participants"])==2
    key=str(uuid4());response=pay(client,catalog,booking["id"],key=key)
    assert response.status_code==200,response.text
    payment=response.json();assert payment["status"]=="succeeded"
    assert pay(client,catalog,booking["id"],key=key).json()["id"]==payment["id"]
    assert pay(client,catalog,booking["id"],key=key,holder_name="Changed name").status_code==409
    assert pay(client,catalog,booking["id"]).status_code==409
    assert detail(client,catalog,booking["id"])["status"]=="confirmed"
    service.price=10000;catalog["departure"].price=99999;db.commit()
    assert detail(client,catalog,booking["id"])["total_amount"]=="651.25"
    auth=headers(catalog["traveler"])
    assert client.get(f"{API}/bookings/{booking['id']}/confirmation",headers=auth).status_code==200
    assert "BEGIN:VEVENT" in client.get(f"{API}/bookings/{booking['id']}/calendar.ics",headers=auth).text
    assert client.get(f"{API}/bookings/{booking['id']}",headers=headers(catalog["other"])).status_code==404
    assert db.scalar(select(func.count()).select_from(PaymentAttempt).where(PaymentAttempt.status=="succeeded"))==1
    saved=db.scalar(select(PaymentAttempt));assert not hasattr(saved,"cvc") and not hasattr(saved,"card_number")


@pytest.mark.parametrize("changes",[{"card_number":"4242424242424241"},{"card_number":"42"},{"card_number":"4111111111111111"},{"expiry_month":0},{"expiry_month":13},{"expiry_month":"12/30"},{"cvc":"12"},{"cvc":"1234"},{"cvc":"abc"}])
def test_instrument_validation(client,catalog,changes):
    booking=book(client,catalog)
    assert pay(client,catalog,booking["id"],**changes).status_code==422


def test_expiry_boundary_controlled_clock(client,catalog,monkeypatch):
    clock=datetime(2026,1,31,19,0,tzinfo=timezone.utc) # Feb 1 in Almaty.
    monkeypatch.setattr(commerce,"now",lambda:clock)
    booking=book(client,catalog)
    assert pay(client,catalog,booking["id"],expiry_year=2026,expiry_month=1).status_code==422
    assert pay(client,catalog,booking["id"],expiry_year=2026,expiry_month=2).json()["status"]=="succeeded"


@pytest.mark.parametrize("number,code",[("4000000000009995","insufficient_funds"),("4000000000000002","bank_declined"),("4000000000000119","provider_unavailable")])
def test_declines_retry_without_extending_reservation(client,catalog,number,code):
    booking=book(client,catalog);result=pay(client,catalog,booking["id"],number).json()
    assert result["status"]=="failed" and result["error_code"]==code
    assert pay(client,catalog,booking["id"]).json()["status"]=="succeeded"
    assert detail(client,catalog,booking["id"])["expires_at"]==booking["expires_at"]


@pytest.mark.parametrize("outcome,status",[("success","succeeded"),("failure","failed"),("expired","failed"),("cancelled","cancelled")])
def test_3ds_all_outcomes_and_repeated_events(client,catalog,outcome,status):
    booking=book(client,catalog);payment=pay(client,catalog,booking["id"],"4000000000003220").json()
    assert payment["status"]=="requires_action"
    assert pay(client,catalog,booking["id"]).status_code==409
    path=f"{API}/payments/{payment['id']}/confirm";auth=headers(catalog["traveler"])
    assert client.post(path,headers=auth,json={"outcome":outcome}).json()["status"]==status
    assert client.post(path,headers=auth,json={"outcome":"success"}).json()["status"]==status


def test_unknown_late_success_compensates_and_releases_seats(client,catalog,db):
    catalog["departure"].capacity=1;db.commit();booking=book(client,catalog)
    payment=pay(client,catalog,booking["id"],"4000000000009235").json();assert payment["status"]=="unknown"
    assert pay(client,catalog,booking["id"]).status_code==409
    saved=db.get(Booking,booking["id"]);saved.expires_at=commerce.now()-timedelta(seconds=1);db.commit()
    second=book(client,catalog) # Availability must not depend on a worker sweep.
    path=f"{API}/payments/{payment['id']}/reconcile";auth=headers(catalog["traveler"])
    assert client.post(path,headers=auth).json()["status"]=="succeeded"
    assert client.post(path,headers=auth).json()["status"]=="succeeded"
    after=detail(client,catalog,booking["id"])
    assert after["status"]=="expired" and after["refunded_amount"]==after["paid_amount"] and len(after["refunds"])==1
    assert pay(client,catalog,second["id"]).json()["status"]=="succeeded"


def test_unknown_failure_durable_provider_can_retry(client,catalog):
    booking=book(client,catalog);payment=pay(client,catalog,booking["id"],"4000000000000341").json()
    assert payment["status"]=="unknown"
    with SessionLocal() as fresh:
        saved=fresh.get(PaymentAttempt,payment["id"])
        assert fresh.get(ProviderOperation,saved.provider_operation_id).status=="failed"
    assert client.post(f"{API}/payments/{payment['id']}/reconcile",headers=headers(catalog["traveler"])).json()["status"]=="failed"
    assert pay(client,catalog,booking["id"]).json()["status"]=="succeeded"


@pytest.mark.parametrize("days,percent",[(10,Decimal("1")),(4,Decimal("0.8")),(1,Decimal("0.5"))])
def test_cancellation_refund_policy_and_repeat(client,catalog,db,days,percent):
    catalog["departure"].start_date=commerce.today()+timedelta(days=days)
    catalog["departure"].end_date=commerce.today()+timedelta(days=days+2);db.commit()
    booking=book(client,catalog);assert pay(client,catalog,booking["id"]).json()["status"]=="succeeded"
    path=f"{API}/bookings/{booking['id']}/cancel";auth=headers(catalog["traveler"])
    result=client.post(path,headers=auth).json()
    assert result["status"]=="cancelled"
    assert Decimal(result["refunded_amount"])==(Decimal(result["total_amount"])*percent).quantize(Decimal("0.01"))
    assert client.post(path,headers=auth).json()["refunded_amount"]==result["refunded_amount"]
    assert db.scalar(select(func.count()).select_from(Refund))==1


def test_refund_failure_retry_and_overrefund_guard(client,catalog):
    booking=book(client,catalog);pay(client,catalog,booking["id"])
    path=f"{API}/manage/bookings/{booking['id']}/refunds";admin=headers(catalog["admin"])
    response=client.post(path,headers={**admin,"Idempotency-Key":str(uuid4())},json={"amount":"200","reason":"Retry check","scenario":"temporary_failure"})
    assert response.status_code==201,response.text
    failed=response.json();assert failed["status"]=="failed"
    assert client.post(f"{API}/refunds/{failed['id']}/retry",headers=headers(catalog["other"])).status_code==404
    assert client.post(f"{API}/refunds/{failed['id']}/retry",headers=admin).json()["status"]=="succeeded"
    assert client.post(f"{API}/refunds/{failed['id']}/retry",headers=admin).json()["status"]=="succeeded"
    assert client.post(path,headers={**admin,"Idempotency-Key":str(uuid4())},json={"amount":"200","reason":"Too much"}).status_code==409


def test_expired_reserve_payload_tampering_and_service_scope(client,catalog,db):
    booking=book(client,catalog);saved=db.get(Booking,booking["id"]);saved.expires_at=commerce.now()-timedelta(seconds=1);db.commit()
    assert pay(client,catalog,booking["id"]).status_code==409
    for changes,code in [({"currency":"USD"},422),({"service_ids":[str(uuid4())]},422),({"participants":[{"name":"First One"},{"name":"Second One"}]},422)]:
        assert client.post(f"{API}/bookings",headers=headers(catalog["traveler"]),json={**booking_body(catalog, 1),**changes}).status_code==code


def promo(db):
    item=PromoCode(code="TEST10",kind="percent",value=10,min_amount=0,starts_at=commerce.now()-timedelta(days=1),ends_at=commerce.now()+timedelta(days=1),usage_limit=1,per_user_limit=1)
    db.add(item);db.commit();return item


def test_promo_limits_unpaid_release_and_expiry(client,catalog,db):
    item=promo(db);first=book(client,catalog,promo_code="test10")
    assert first["total_amount"]=="247.95" and first["discount_amount"]=="27.55"
    payload={**booking_body(catalog, 1),"promo_code":"TEST10"};auth=headers(catalog["traveler"])
    assert client.post(f"{API}/bookings",headers=auth,json=payload).status_code==409
    client.post(f"{API}/bookings/{first['id']}/cancel",headers=auth)
    second=book(client,catalog,promo_code="TEST10");assert second["total_amount"]==first["total_amount"]
    client.post(f"{API}/bookings/{second['id']}/cancel",headers=auth)
    item.ends_at=commerce.now()-timedelta(seconds=1);item.starts_at=commerce.now()-timedelta(days=2);db.commit()
    assert client.post(f"{API}/bookings",headers=auth,json=payload).status_code==409


def test_late_compensated_payment_does_not_reconsume_released_promo(client,catalog,db):
    item = promo(db)
    first = book(client, catalog, promo_code=item.code)
    unknown = pay(client, catalog, first["id"], number="4000000000009235").json()
    assert unknown["status"] == "unknown"
    stored = db.get(Booking, first["id"])
    stored.expires_at = commerce.now() - timedelta(seconds=1)
    db.commit()
    payload = {**booking_body(catalog, 1), "promo_code": item.code}
    other = headers(catalog["other"])
    second = client.post(f"{API}/bookings", headers=other, json=payload)
    assert second.status_code == 201
    settled = client.post(f"{API}/payments/{unknown['id']}/reconcile", headers=headers(catalog["traveler"]))
    assert settled.status_code == 200 and settled.json()["status"] == "succeeded"
    original = detail(client, catalog, first["id"])
    assert original["status"] == "expired" and original["paid_amount"] == original["refunded_amount"]
    assert client.post(f"{API}/bookings/{second.json()['id']}/cancel", headers=other).status_code == 200
    # No trip was confirmed for the late payment: its compensation cannot
    # silently consume the released single-use code again.
    third = book(client, catalog, promo_code=item.code)
    assert third["status"] == "pending" and third["discount_amount"] == first["discount_amount"]


def test_aggregate_money_overflow_is_rejected_before_reserving(client,catalog,db):
    catalog["departure"].capacity = 20
    services = [ExperienceService(experience_id=catalog["tour"].id, name=f"Large option {index}",
                                  price=Decimal("100000000.00"), per_person=True) for index in range(6)]
    db.add_all(services)
    db.commit()
    body = {**booking_body(catalog, 20), "service_ids": [service.id for service in services]}
    auth = headers(catalog["traveler"])
    assert client.post(f"{API}/bookings/quote", headers=auth, json=body).status_code == 422
    assert client.post(f"{API}/bookings", headers=auth, json=body).status_code == 422
    assert db.scalar(select(func.count()).select_from(Booking)) == 0


def test_partial_refund_accepts_tiyn_and_preserves_exact_balance(client,catalog,db):
    catalog["departure"].price = Decimal("1.00")
    db.commit()
    booking = book(client, catalog)
    assert pay(client, catalog, booking["id"]).status_code == 200
    path = f"{API}/manage/bookings/{booking['id']}/refunds"
    admin = headers(catalog["admin"])
    for amount in ("0.01", "0.99"):
        response = client.post(path, headers={**admin, "Idempotency-Key": str(uuid4())},
                               json={"amount": amount, "reason": "Exact fractional refund"})
        assert response.status_code == 201 and response.json()["amount"] == amount
    assert detail(client, catalog, booking["id"])["refunded_amount"] == "1.00"
    assert client.post(path, headers={**admin, "Idempotency-Key": str(uuid4())},
                       json={"amount": "0.01", "reason": "Cannot exceed payment"}).status_code == 409


@pytest.mark.postgres
@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="PostgreSQL promo row locks required")
def test_promo_confirmation_holds_limit_until_commit_across_expiry(client,catalog,db,monkeypatch):
    from fastapi import HTTPException
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError
    from app.api.schemas import BookingInput
    from app.api.commerce_schemas import PaymentInput
    from app.domain.models import User
    item = promo(db)
    first = book(client, catalog, promo_code=item.code)
    original = catalog["departure"]
    other_date = original.start_date + timedelta(days=3)
    other_departure = Departure(experience_id=catalog["tour"].id, start_date=other_date,
                                end_date=other_date + timedelta(days=2), capacity=2, price=original.price)
    db.add(other_departure)
    db.commit()
    clock = [commerce.now()]
    monkeypatch.setattr(commerce, "now", lambda: clock[0])
    with SessionLocal() as confirming, SessionLocal() as competing:
        user = confirming.get(User, catalog["traveler"].id)
        result = commerce.initiate_payment(confirming, user, first["id"], PaymentInput(**card()), str(uuid4()))
        assert result.status == "succeeded"
        # Confirmation is valid, but its transaction has not committed yet.
        clock[0] = commerce.aware(confirming.get(Booking, first["id"]).expires_at) + timedelta(seconds=1)
        data = BookingInput(**{**booking_body(catalog, 1), "departure_id": other_departure.id, "promo_code": item.code})
        other = competing.get(User, catalog["other"].id)
        competing.execute(text("SET LOCAL lock_timeout = '100ms'"))
        with pytest.raises(OperationalError) as blocked:
            commerce.create_booking(competing, other, data)
        assert blocked.value.orig.sqlstate == "55P03"
        competing.rollback()
        confirming.commit()
        with pytest.raises(HTTPException) as exhausted:
            commerce.create_booking(competing, competing.get(User, catalog["other"].id), data)
        assert exhausted.value.status_code == 409


@pytest.mark.postgres
@pytest.mark.skipif(engine.dialect.name!="postgresql",reason="PostgreSQL row locks required")
def test_parallel_payments_and_refunds_bounded(catalog):
    with TestClient(app) as client: booking=book(client,catalog)
    barrier=Barrier(2)
    def charge(_):
        with TestClient(app) as client:
            barrier.wait(timeout=10);return pay(client,catalog,booking["id"]).status_code
    with ThreadPoolExecutor(max_workers=2) as executor: statuses=list(executor.map(charge,range(2)))
    assert sorted(statuses)==[200,409]
    barrier=Barrier(2)
    def refund(_):
        with TestClient(app) as client:
            barrier.wait(timeout=10)
            return client.post(f"{API}/manage/bookings/{booking['id']}/refunds",headers={**headers(catalog["admin"]),"Idempotency-Key":str(uuid4())},json={"amount":"200","reason":"Parallel refund"}).status_code
    with ThreadPoolExecutor(max_workers=2) as executor: statuses=list(executor.map(refund,range(2)))
    assert sorted(statuses)==[201,409]
    with SessionLocal() as fresh: assert fresh.scalar(select(func.sum(Refund.amount)).where(Refund.status=="succeeded"))==Decimal(200)


@pytest.mark.postgres
@pytest.mark.skipif(engine.dialect.name!="postgresql",reason="PostgreSQL row locks required")
def test_parallel_promo_and_payment_cancel_race(catalog,db):
    promo(db)
    second=Departure(experience_id=catalog["tour"].id,start_date=commerce.today()+timedelta(days=40),end_date=commerce.today()+timedelta(days=42),capacity=5,price=275.5)
    db.add(second);db.commit();barrier=Barrier(2)
    def reserve(did):
        with TestClient(app) as client:
            barrier.wait(timeout=10)
            return client.post(f"{API}/bookings",headers=headers(catalog["traveler"]),json={**booking_body(catalog, 1),"departure_id":did,"promo_code":"TEST10"})
    with ThreadPoolExecutor(max_workers=2) as executor: results=list(executor.map(reserve,[catalog["departure"].id,second.id]))
    assert sorted(r.status_code for r in results)==[201,409]
    booking=next(r.json() for r in results if r.status_code==201);barrier=Barrier(2)
    def action(name):
        with TestClient(app) as client:
            barrier.wait(timeout=10)
            return pay(client,catalog,booking["id"]) if name=="pay" else client.post(f"{API}/bookings/{booking['id']}/cancel",headers=headers(catalog["traveler"]))
    with ThreadPoolExecutor(max_workers=2) as executor: list(executor.map(action,["pay","cancel"]))
    with TestClient(app) as client: after=detail(client,catalog,booking["id"])
    assert after["status"]=="cancelled" and after["paid_amount"]==after["refunded_amount"]


def test_vendor_cancellation_rules_frozen_and_departure_obligations(client,catalog,db):
    vendor=headers(catalog["vendor"]);eid=catalog["tour"].id;did=catalog["departure"].id
    custom=[{"days_before":7,"refund_percent":90},{"days_before":0,"refund_percent":25}]
    path=f"{API}/manage/experiences/{eid}"
    result=client.patch(path,headers=vendor,json={"cancellation_rules":custom})
    assert result.status_code==200,result.text
    booking=book(client,catalog)
    assert booking["cancellation_policy"]["rules"]==custom
    pay(client,catalog,booking["id"])
    assert client.patch(path,headers=vendor,json={"cancellation_rules":[{"days_before":0,"refund_percent":0}]}).status_code==200
    assert detail(client,catalog,booking["id"])["cancellation_policy"]["rules"]==custom
    assert client.patch(f"{API}/manage/departures/{did}",headers=vendor,json={"capacity":1}).status_code==200
    assert client.delete(f"{API}/manage/departures/{did}",headers=vendor).status_code==409
    assert client.patch(f"{API}/manage/departures/{did}",headers=headers(catalog["other_vendor"]),json={"status":"cancelled"}).status_code==404
    cancelled=client.patch(f"{API}/manage/departures/{did}",headers=vendor,json={"status":"cancelled"})
    assert cancelled.status_code==200,cancelled.text
    after=detail(client,catalog,booking["id"])
    assert after["status"]=="cancelled" and after["paid_amount"]==after["refunded_amount"]


def test_3ds_server_timeout_and_worker_idempotency(client,catalog,db):
    booking=book(client,catalog);payment=pay(client,catalog,booking["id"],"4000000000003220").json()
    saved=db.get(PaymentAttempt,payment["id"]);saved.action_expires_at=commerce.now()-timedelta(seconds=1);db.commit()
    assert client.post(f"{API}/payments/{payment['id']}/confirm",headers=headers(catalog["traveler"]),json={"outcome":"success"}).json()["error_code"]=="authentication_expired"
    stored=db.get(Booking,booking["id"]);stored.expires_at=commerce.now()-timedelta(minutes=1);db.commit()
    with SessionLocal() as fresh:
        assert commerce.process_pending(fresh)["expired"]==1
        assert commerce.process_pending(fresh)["expired"]==0
    assert detail(client,catalog,booking["id"])["status"]=="expired"


def test_pending_refund_reserves_balance_and_worker_finishes(client,catalog):
    booking=book(client,catalog);pay(client,catalog,booking["id"])
    path=f"{API}/manage/bookings/{booking['id']}/refunds";auth=headers(catalog["admin"])
    response=client.post(path,headers={**auth,"Idempotency-Key":str(uuid4())},json={"amount":"200","reason":"Processing refund","scenario":"processing"})
    assert response.status_code==201 and response.json()["status"]=="pending"
    assert detail(client,catalog,booking["id"])["refunded_amount"]=="0.00"
    assert client.post(path,headers={**auth,"Idempotency-Key":str(uuid4())},json={"amount":"200","reason":"Over reserved"}).status_code==409
    with SessionLocal() as fresh: commerce.process_pending(fresh)
    assert detail(client,catalog,booking["id"])["refunded_amount"]=="200.00"


def test_quote_exact_without_reserving_and_manager_detail_scope(client,catalog,db):
    promo(db);auth=headers(catalog["traveler"]);payload={**booking_body(catalog,1),"promo_code":"TEST10"}
    quote=client.post(f"{API}/bookings/quote",headers=auth,json=payload)
    assert quote.status_code==200,quote.text
    assert quote.json()["total_amount"]=="247.95" and quote.json()["discount_amount"]=="27.55"
    assert db.scalar(select(func.count()).select_from(Booking))==0
    assert client.get(f"{API}/experiences/{catalog['tour'].slug}").json()["departures"][0]["available_seats"]==4
    booking=book(client,catalog,promo_code="TEST10")
    assert booking["total_amount"]==quote.json()["total_amount"]
    path=f"{API}/manage/bookings/{booking['id']}"
    assert client.get(path,headers=headers(catalog["vendor"])).status_code==200
    assert client.get(path,headers=headers(catalog["admin"])).status_code==200
    assert client.get(path,headers=headers(catalog["other_vendor"])).status_code==404
    assert client.get(path,headers=auth).status_code==403
    payment=pay(client,catalog,booking["id"],"4000000000009235").json()
    assert client.post(f"{API}/payments/{payment['id']}/reconcile",headers=headers(catalog["admin"])).json()["status"]=="succeeded"


def test_published_create_and_unknown_category_validation(client,catalog):
    from tests.test_api import tour_body
    payload={**tour_body(catalog),"is_published":True}
    response=client.post(f"{API}/manage/experiences",headers=headers(catalog["vendor"]),json=payload)
    assert response.status_code==201,response.text
    assert response.json()["currency"]=="KZT"
    assert client.post(f"{API}/manage/experiences",headers=headers(catalog["vendor"]),json={**payload,"category":"MissingCategory"}).status_code==422

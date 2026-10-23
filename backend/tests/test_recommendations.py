"""Recommendations must match real dates, group budgets and live seat inventory."""
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app.domain.models import Booking, Departure, Experience
from app.services import commerce_service as commerce
from tests.conftest import headers
from tests.test_api import booking_body

API = "/api/v1"


def test_recommendations_filters_group_budget_and_localized_explanation(client,catalog,db):
    response=client.get(f"{API}/recommendations",params={"budget":"551.00","category":"Nature","duration_max":3,"travelers":2,"lang":"en"})
    assert response.status_code==200,response.text
    result=response.json();assert result["total"]==1 and result["budget_scope"]=="group_base_fare"
    item=result["items"][0]
    assert item["id"]==catalog["tour"].id and item["quoted_base_amount"]=="551.00"
    assert "Fits your group budget" in item["reason"] and item["recommended_departure"]["available_seats"]==4
    assert db.scalar(select(func.count()).select_from(Booking))==0
    for params in [{"budget":"550.99","travelers":2},{"category":"City"},{"duration_max":2},{"travelers":5}]:
        assert client.get(f"{API}/recommendations",params=params).json()["items"]==[]
    kk=client.get(f"{API}/recommendations?lang=kk&budget=300").json()["items"][0]
    assert "бюджетіне" in kk["reason"] and kk["title"]=="Тау соқпақтары"
    assert client.get(f"{API}/recommendations?travelers=0").status_code==422
    assert client.get(f"{API}/recommendations?budget=NaN").status_code==422


def test_recommendations_sold_out_expired_hold_cancelled_past_and_unpublished(client,catalog,db):
    auth=headers(catalog["traveler"])
    response=client.post(f"{API}/bookings",headers=auth,json=booking_body(catalog,4));assert response.status_code==201
    assert client.get(f"{API}/recommendations").json()["items"]==[]
    booking=db.get(Booking,response.json()["id"]);booking.expires_at=commerce.now()-timedelta(seconds=1);db.commit()
    # A stale pending row must not hide the tour; no worker or detail request runs first.
    assert client.get(f"{API}/recommendations").json()["total"]==1
    catalog["departure"].status="cancelled";db.commit()
    assert client.get(f"{API}/recommendations").json()["items"]==[]
    catalog["departure"].status="scheduled";catalog["departure"].start_date=commerce.today()-timedelta(days=1);db.commit()
    assert client.get(f"{API}/recommendations").json()["items"]==[]
    catalog["departure"].start_date=commerce.today()+timedelta(days=10);catalog["tour"].is_published=False;db.commit()
    assert client.get(f"{API}/recommendations").json()["items"]==[]


def test_recommendations_deduplicate_departures_and_rank_closest_group_budget(client,catalog,db):
    second=Experience(slug="second-trip",title="Другой маршрут",description="Второй маршрут для проверки рекомендаций.",
                      destination_id=catalog["destination"].id,vendor_id=catalog["vendor"].id,category="Nature",duration_days=2,
                      price_from=200,image_url="https://example.com/second.jpg")
    db.add(second);db.flush()
    for experience,delta,price in [(catalog["tour"],50,250),(second,60,200)]:
        start=commerce.today()+timedelta(days=delta)
        db.add(Departure(experience_id=experience.id,start_date=start,end_date=start+timedelta(days=2),capacity=3,price=price))
    db.commit()
    rows=client.get(f"{API}/recommendations?budget=1000&travelers=2").json()["items"]
    assert len(rows)==2 and len({row["id"] for row in rows})==2
    assert rows[0]["id"]==catalog["tour"].id and rows[0]["quoted_base_amount"]=="500.00"
    assert rows[1]["quoted_base_amount"]=="400.00"


def test_recommendations_and_manager_list_batch_queries_as_catalog_grows(client,catalog,db):
    from sqlalchemy import event
    from app.db import engine
    statements=[]
    def capture(connection,cursor,statement,parameters,context,executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)
    def request_count(path,auth=None):
        statements.clear()
        event.listen(engine,"before_cursor_execute",capture)
        try:
            response=client.get(path,headers=auth or {})
        finally:
            event.remove(engine,"before_cursor_execute",capture)
        assert response.status_code==200,response.text
        return len(statements),response.json()
    first_recs,_=request_count(f"{API}/recommendations")
    first_manage,_=request_count(f"{API}/manage/experiences",headers(catalog["vendor"]))
    for index in range(5):
        tour=Experience(slug=f"batch-tour-{index}",title=f"Маршрут {index}",description="Дополнительный маршрут для проверки количества запросов.",
                        destination_id=catalog["destination"].id,vendor_id=catalog["vendor"].id,category="Nature",duration_days=2,
                        price_from=100,image_url="https://example.com/batch.jpg")
        db.add(tour);db.flush()
        for offset in range(5):
            start=commerce.today()+timedelta(days=60+offset)
            db.add(Departure(experience_id=tour.id,start_date=start,end_date=start+timedelta(days=1),capacity=3,price=100))
    db.commit()
    many_recs,recs=request_count(f"{API}/recommendations")
    many_manage,managed=request_count(f"{API}/manage/experiences",headers(catalog["vendor"]))
    assert len(recs["items"])==6 and len(managed["items"])==6
    assert many_recs==first_recs
    assert many_manage==first_manage
    assert sum(len(tour["departures"]) for tour in managed["items"])==26

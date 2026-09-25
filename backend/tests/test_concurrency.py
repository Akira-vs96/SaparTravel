from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal, engine
from app.domain.models import Booking
from app.main import app
from tests.conftest import headers
from tests.test_api import booking_body


@pytest.mark.postgres
@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="PostgreSQL row locks required")
def test_last_seat_cannot_be_booked_twice(catalog, db):
    catalog["departure"].capacity = 1
    db.commit()
    barrier = Barrier(2)
    payload = booking_body(catalog, 1)
    auth = headers(catalog["traveler"])

    def book():
        with TestClient(app) as client:
            barrier.wait(timeout=10)
            response = client.post("/api/v1/bookings", headers=auth, json=payload)
            return response.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(book) for _ in range(2)]
        statuses = sorted(future.result(timeout=20) for future in futures)
    assert statuses == [201, 409]
    with SessionLocal() as check:
        bookings = check.scalars(select(Booking).where(Booking.status != "cancelled")).all()
        assert sum(booking.travelers_count for booking in bookings) == 1

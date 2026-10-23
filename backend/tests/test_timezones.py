from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from app.api.schemas import DepartureInput
from app.core.clock import at_time, business_today
from app.domain.models import Departure
from app.services.catalog_service import experience_detail
from app.services.commerce_service import today


def test_almaty_midnight_boundary_matches_validation_catalog_and_booking(db, catalog):
    with at_time(datetime(2031, 1, 1, 22, 0, tzinfo=timezone.utc)):
        # UTC is still January 1; Kazakhstan already has January 2.
        assert business_today() == today() == date(2031, 1, 2)
        with pytest.raises(ValidationError):
            DepartureInput(start_date=date(2031, 1, 2), capacity=4, price="25000.00")
        valid = DepartureInput(start_date=date(2031, 1, 3), capacity=4, price="25000.00")
        existing = catalog["departure"]
        existing.start_date, existing.end_date = date(2031, 1, 2), date(2031, 1, 4)
        future = Departure(experience_id=catalog["tour"].id, start_date=valid.start_date,
                           end_date=date(2031, 1, 5), capacity=valid.capacity, price=valid.price)
        db.add(future)
        db.commit()
        details = experience_detail(db, catalog["tour"])
        assert [item["id"] for item in details["departures"]] == [future.id]

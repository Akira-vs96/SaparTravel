from datetime import date
import json
from pathlib import Path

from sqlalchemy import func, select

from app.demo import prepare_accounts, seed_scenarios
from app.domain.models import Departure, Experience, PromoCode, User
from app.seed import extend_departures, seed_data


def test_private_demo_accounts_preserve_credentials_ownership_and_departures(db):
    payload = json.loads((Path(__file__).parents[1] / "app/seed_data.json").read_text())
    seed_data(db, payload)
    credentials, accounts = prepare_accounts(db)
    seed_scenarios(db, accounts)
    db.commit()
    assert len(credentials) == 4
    assert len({row["password"] for row in credentials}) == 4
    hashes = {user.email: user.password_hash for user in accounts.values()}
    tours = db.scalars(select(Experience)).all()
    assert len(tours) >= 24
    assert {tour.currency for tour in tours} == {"KZT"}
    assert len({tour.vendor_id for tour in tours}) == 2
    tour = tours[0]
    tour.title = "Название изменено пользователем"
    dates = {departure.id: departure.start_date for departure in db.scalars(select(Departure))}
    db.commit()
    seed_data(db, payload)
    again, existing = prepare_accounts(db)
    seed_scenarios(db, existing)
    db.commit()
    assert again == []
    assert {user.email: user.password_hash for user in existing.values()} == hashes
    assert tour.title == "Название изменено пользователем"
    assert {departure.id: departure.start_date for departure in db.scalars(select(Departure))} == dates
    assert db.scalar(select(func.count()).select_from(PromoCode).where(PromoCode.code == "SAPAR10")) == 1
    service = db.scalar(select(User).where(User.email == "catalog@sapartravel.invalid"))
    assert service is not None and not service.is_active
    extend_departures(db)
    db.flush()
    count = db.scalar(select(func.count()).select_from(Departure))
    extend_departures(db)
    db.flush()
    assert db.scalar(select(func.count()).select_from(Departure)) == count
    assert all(db.get(Departure, key).start_date == value for key, value in dates.items())
    assert any(value > date.today() for value in dates.values())
    assert any(value < date.today() for value in dates.values())

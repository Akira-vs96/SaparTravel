from datetime import date

from sqlalchemy import func, select

from app.domain.models import Departure, Destination, Experience, User
from app.seed import seed_data


def test_seed_is_idempotent_and_preserves_edits(db):
    payload = {
        "destinations": [{"slug": "paris", "name": "Париж", "name_en": "Paris", "name_kk": "Париж",
                          "country": "Франция", "country_en": "France", "country_kk": "Франция", "continent": "Europe",
                          "description": "Прогулки по музеям, улицам и садам Парижа.", "image_url": "https://example.com/paris.jpg"}],
        "experiences": [{"slug": "paris-museums", "destination_slug": "paris", "title": "Музеи Парижа",
                         "title_en": "Paris museums", "title_kk": "Париж мұражайлары", "description": "Погружение в коллекции известных музеев Парижа.",
                         "category": "Culture", "duration_days": 2, "price_from": 400, "image_url": "https://example.com/museum.jpg"}],
    }
    seed_data(db, payload)
    db.commit()
    tour = db.scalar(select(Experience))
    tour.title = "Изменённый администратором маршрут"
    tour.is_published = False
    db.commit()
    seed_data(db, payload)
    db.commit()
    assert db.scalar(select(func.count()).select_from(Destination)) == 1
    assert db.scalar(select(func.count()).select_from(Experience)) == 1
    assert db.scalar(select(func.count()).select_from(Departure)) == 3
    assert db.scalar(select(Experience)).title == "Изменённый администратором маршрут"
    assert not db.scalar(select(Experience)).is_published
    assert all(departure.start_date > date.today() for departure in db.scalars(select(Departure)))
    owner = db.scalar(select(User))
    assert owner.role == "vendor" and not owner.is_active
    assert owner.password_hash.startswith("$argon2")

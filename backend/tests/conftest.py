import os
from pathlib import Path
import shutil
import tempfile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

# TEST_DATABASE_URL must point to a disposable database; never use the application's DATABASE_URL.
_test_directory = tempfile.mkdtemp(prefix="sapartravel-pytest-")
_test_url = os.environ.get("TEST_DATABASE_URL", f"sqlite:///{_test_directory}/test.db")
if make_url(_test_url).get_backend_name() != "sqlite" and not (make_url(_test_url).database or "").endswith("_test"):
    raise RuntimeError("TEST_DATABASE_URL must use a disposable database whose name ends with _test")
os.environ.update(
    DATABASE_URL=_test_url, ENVIRONMENT="testing", JWT_SECRET="pytest-secret-long-and-varied-47c90b126",
    ADMIN_EMAIL="", ADMIN_PASSWORD="", AUTH_RATE_LIMIT="0", SEED_DEMO_DATA="false",
)

from app.core.security import password_hash, token_for
from app.db import Base, SessionLocal, engine
from app.domain.models import Departure, Destination, Experience, User
from app.main import app
from datetime import date, timedelta

HASH = password_hash.hash("Correct-password-2026")


@pytest.fixture(scope="session", autouse=True)
def database_schema():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)
    engine.dispose()
    shutil.rmtree(_test_directory)


@pytest.fixture(autouse=True)
def clean_database(database_schema):
    with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(table.delete())


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session
        session.rollback()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def catalog(db):
    users = {}
    for role, name in (("admin", "Admin"), ("vendor", "Vendor"), ("traveler", "Traveler")):
        user = User(name=name, email=f"{role}@example.com", password_hash=HASH, role=role)
        db.add(user)
        db.flush()
        users[role] = user
    second_vendor = User(name="Other vendor", email="other@example.com", password_hash=HASH, role="vendor")
    other = User(name="Other traveler", email="other-traveler@example.com", password_hash=HASH, role="traveler")
    db.add_all([second_vendor, other])
    destination = Destination(slug="almaty", name="Алматы", name_en="Almaty", name_kk="Алматы",
                              country="Казахстан", country_en="Kazakhstan", country_kk="Қазақстан",
                              continent="Asia", description="Путешествие по горам и городу Алматы.",
                              description_en="A journey through Almaty and its mountains.",
                              description_kk="Алматы қаласы мен тауларына саяхат.",
                              image_url="https://example.com/almaty.jpg")
    db.add(destination)
    db.flush()
    tour = Experience(slug="mountain-trails", title="Горные тропы", title_en="Mountain trails", title_kk="Тау соқпақтары",
                      description="Путешествие по живописным горным тропам.", description_en="Explore spectacular mountain trails.",
                      description_kk="Әсем таулы соқпақтармен саяхат.", vendor_id=users["vendor"].id, destination_id=destination.id,
                      category="Nature", duration_days=3, price_from=250, rating=4.8, review_count=0,
                      image_url="https://example.com/mountain.jpg", tags=["Горы"], tags_en=["Mountains"], tags_kk=["Таулар"],
                      included=["Гид"], included_en=["Guide"], included_kk=["Гид"],
                      itinerary=[{"day": 1, "title": "Знакомство", "description": "Встреча в Алматы"}])
    db.add(tour)
    db.flush()
    departure = Departure(experience_id=tour.id, start_date=date.today() + timedelta(days=10),
                          end_date=date.today() + timedelta(days=12), capacity=4, price=275.50)
    db.add(departure)
    db.commit()
    users.update(other_vendor=second_vendor, other=other, destination=destination, tour=tour, departure=departure)
    return users


def headers(user):
    return {"Authorization": f"Bearer {token_for(user)}"}

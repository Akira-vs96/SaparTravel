"""Explicitly provision synthetic monitoring resources; never run on startup."""
import argparse
from datetime import timedelta
import json
import os
from pathlib import Path
import re
import secrets
from urllib.parse import urlsplit

from sqlalchemy import select, text

from app.core.clock import business_today
from app.core.security import password_hash
from app.db import SessionLocal
from app.domain.models import Departure, Destination, Experience, User


def provision(db, *, deployment_id, origin, directory, points, scope="acceptance-only"):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,50}", deployment_id):
        raise ValueError("Use a deployment identifier of 1 to 50 letters, numbers, underscores or hyphens")
    parsed = urlsplit(origin)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.path not in {"", "/"}
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise ValueError("Use an HTTP(S) origin without credentials or path")
    origin = origin.rstrip("/")
    if scope not in {"acceptance-only", "operational"} or len(points) != 3 or len(set(points)) != 3:
        raise ValueError("Declare exactly three distinct points and a supported scope")
    if not all(re.fullmatch(r"[A-Za-z0-9_-]{1,50}", point) for point in points):
        raise ValueError("Invalid monitoring point")
    if directory.exists():
        raise ValueError("Use a new private output directory; credentials are never overwritten")
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(7240019403)"))
    destination = db.scalar(select(Destination).order_by(Destination.id).limit(1))
    template = db.scalar(select(Experience).where(Experience.is_monitoring.is_(False)).limit(1))
    if not destination or not template:
        raise ValueError("Seed the regular catalog before provisioning monitoring")
    accounts = []
    for point in points:
        email = f"monitor-{deployment_id}-{point}@example.com".lower()
        if db.scalar(select(User.id).where(User.email == email)):
            raise ValueError("Monitoring identity already exists; preserve its original private credentials")
        password = secrets.token_urlsafe(32)
        user = User(name="SaparTravel service probe", email=email, password_hash=password_hash.hash(password),
                    role="traveler", is_active=True, is_monitoring=True)
        db.add(user)
        db.flush()
        accounts.append({"point": point, "email": email, "password": password, "id": user.id})
    tour = Experience(slug="monitor-" + deployment_id, vendor_id=template.vendor_id,
                      destination_id=destination.id, category=template.category, duration_days=1,
                      price_from=1000, image_url=template.image_url, is_monitoring=True,
                      title="Контроль сервиса", title_en="Service probe", title_kk="Қызметті тексеру",
                      description="Технический контрольный тур без реальных поездок и платежей.",
                      description_en="Synthetic service check without real trips or payments.",
                      description_kk="Нақты сапарлар мен төлемдерсіз техникалық тексеру.",
                      itinerary=[{"day": 1, "title": "Контроль", "description": "Проверка бронирования и отмены."}])
    db.add(tour)
    db.flush()
    start = business_today() + timedelta(days=365)
    departure = Departure(experience_id=tour.id, start_date=start, end_date=start, capacity=30, price=1000)
    db.add(departure)
    db.flush()
    manifest = {"scope": scope, "deployment_id": deployment_id, "origin": origin,
                "tour_slug": tour.slug, "departure_id": departure.id, "isolated_database": scope == "acceptance-only"}
    if scope == "operational":
        manifest.update(synthetic_fixture=True, exclude_from_analytics=True)
    directory.mkdir(parents=True, mode=0o700)
    try:
        for account in accounts:
            point = account["point"]
            config = {"point": point, "deployment_id": deployment_id, "origin": origin,
                      "tour_slug": tour.slug, "departure_id": departure.id, "scope": scope, "browser": True}
            for filename, body in ((point + ".json", json.dumps(config, indent=2) + "\n"),
                                   (point + ".env", f"SLI_EMAIL={account['email']}\nSLI_PASSWORD={account['password']}\n")):
                fd = os.open(directory / filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "w") as output:
                    output.write(body)
        (directory / "sapartravel-monitoring.json").write_text(json.dumps(manifest, indent=2) + "\n")
    except BaseException:
        # A failed provision does not certify its files; no credential values are logged.
        raise
    return manifest, accounts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deployment-id", required=True)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--points", nargs=3, required=True)
    parser.add_argument("--scope", choices=("acceptance-only", "operational"), default="acceptance-only")
    args = parser.parse_args()
    try:
        with SessionLocal.begin() as db:
            provision(db, deployment_id=args.deployment_id, origin=args.origin, directory=args.directory,
                      points=args.points, scope=args.scope)
        print("Monitoring fixture ready; keep per-point .env files private and publish only the safety manifest")
    except (ValueError, OSError) as error:
        raise SystemExit(str(error) if isinstance(error, ValueError) else "Cannot write private monitoring configuration") from None


if __name__ == "__main__":
    main()

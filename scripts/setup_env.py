"""Generate a local development configuration without printing secrets."""

import argparse
import os
from pathlib import Path
import secrets


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admin-email", default="admin@example.com")
    args = parser.parse_args()
    target = Path(__file__).resolve().parents[1] / ".env"
    if target.exists():
        print(".env already exists; existing configuration was preserved.")
        return
    email = args.admin_email.strip()
    if not email or "@" not in email or any(char in email for char in "\r\n$#= "):
        parser.error("Provide a valid administrator email address.")
    password = secrets.token_urlsafe(32)
    content = (
        f"POSTGRES_PASSWORD={password}\n"
        f"JWT_SECRET={secrets.token_hex(48)}\n"
        f"ADMIN_EMAIL={email}\n"
        f"ADMIN_PASSWORD={secrets.token_urlsafe(24)}\n"
        "SEED_DEMO_DATA=true\n"
        "ENVIRONMENT=development\n"
        "ACCESS_TOKEN_EXPIRE_MINUTES=120\n"
        "CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173\n"
        "DB_PORT=5432\nAPI_PORT=8000\nWEB_PORT=5173\n"
        f"DATABASE_URL=postgresql+psycopg://sapar:{password}@localhost:5432/sapartravel\n"
    )
    try:
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        print(".env already exists; existing configuration was preserved.")
        return
    with os.fdopen(fd, "w") as output:
        output.write(content)
    print("Created .env with unique database, JWT and administrator secrets.")
    print(f"Administrator: {email}. Read ADMIN_PASSWORD in .env to sign in.")
    print("Start the application: docker compose up --build -d")


if __name__ == "__main__":
    main()

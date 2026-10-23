"""Private local delivery inspection. Run inside the backend environment."""
import argparse
import json
from sqlalchemy import select
from app.core.config import get_settings
from app.db import SessionLocal
from app.domain.engagement import DemoEmail


def main():
    parser = argparse.ArgumentParser(description="Inspect the private SaparTravel demonstration mailbox")
    parser.add_argument("--recipient", required=True, help="Only return messages addressed to this account")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    settings = get_settings()
    if not settings.demo_mailbox_enabled or settings.environment == "production":
        parser.error("Set DEMO_MAILBOX_ENABLED=true in a private non-production environment")
    with SessionLocal() as db:
        rows = db.scalars(select(DemoEmail).where(DemoEmail.recipient == args.recipient.casefold())
                          .order_by(DemoEmail.created_at.desc()).limit(max(1, min(args.limit, 100))))
        for item in rows:
            print(json.dumps({"recipient": item.recipient, "subject": item.subject, "body": item.body,
                              "created_at": item.created_at.isoformat()}, ensure_ascii=False))


if __name__ == "__main__":
    main()

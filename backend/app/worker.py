"""Durable maintenance: expired holds and pending provider reconciliation.

All jobs use database facts and transaction locks. Any process can retry a job
after a restart; a dedicated session advisory lock avoids overlapping sweepers.
"""
import argparse
import logging
import time

from sqlalchemy import text

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db import SessionLocal, engine


logger = logging.getLogger("sapartravel.worker")


def sweep():
    from app.services.commerce_service import process_pending
    # Keep the session-level advisory lock on a dedicated connection: each job
    # commits independently and must not release the sweeper lock between jobs.
    with engine.connect() as lock_connection:
        acquired = engine.dialect.name != "postgresql" or lock_connection.scalar(text("SELECT pg_try_advisory_lock(7240019402)"))
        if not acquired:
            return {"skipped": "another_worker"}
        try:
            with SessionLocal() as db:
                return process_pending(db)
        finally:
            if engine.dialect.name == "postgresql":
                lock_connection.execute(text("SELECT pg_advisory_unlock(7240019402)"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=int, default=10, choices=range(1, 61), metavar="1..60")
    args = parser.parse_args()
    configure_logging(get_settings().log_level)
    while True:
        try:
            result = sweep()
            logger.info("maintenance_completed", extra={"event": "worker.sweep", "result": result})
        except Exception as error:
            # Only class names: no SQL parameters, credentials or card details.
            logger.error("maintenance_failed", extra={"event": "worker.error", "error_type": type(error).__name__})
            if args.once:
                raise SystemExit("Maintenance failed; inspect database availability and migration state") from None
        if args.once:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()

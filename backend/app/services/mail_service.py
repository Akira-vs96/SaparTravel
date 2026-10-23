"""Delivery port. Replace the local adapter with SMTP/API delivery when configured.

The application never returns recovery URLs to the requester. DatabaseMailboxDelivery
is a local simulation; only an authorized administrator/private CLI may inspect it.
"""
from typing import Protocol
from sqlalchemy.orm import Session
from app.domain.engagement import DemoEmail


class MailDelivery(Protocol):
    def deliver(self, db: Session, recipient: str, subject: str, body: str) -> None: ...


class DatabaseMailboxDelivery:
    def deliver(self, db: Session, recipient: str, subject: str, body: str) -> None:
        db.add(DemoEmail(recipient=recipient, subject=subject, body=body))


def get_mail_delivery() -> MailDelivery:
    return DatabaseMailboxDelivery()

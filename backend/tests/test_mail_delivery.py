"""Password recovery must deliver mail or report unavailable without account leaks."""
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from email import policy
from email.parser import BytesParser
import re
import socketserver
import threading

import pytest
from sqlalchemy import func, select

from app.core.config import get_settings
from app.domain.engagement import DemoEmail, OutboundEmail
from app.domain.models import utc_now
from app.db import SessionLocal, engine
from app.services.mail_service import get_mail_delivery, process_mail_queue
from tests.conftest import headers


@pytest.fixture
def smtp_server(monkeypatch):
    state = {"messages": [], "refuse": 0}

    class SMTPHandler(socketserver.StreamRequestHandler):
        def handle(self):
            self.request.settimeout(5)
            self.wfile.write(b"220 localhost ESMTP\r\n")
            while line := self.rfile.readline():
                verb = line.split(b" ", 1)[0].strip().upper()
                if verb in {b"EHLO", b"HELO", b"MAIL", b"RCPT", b"RSET", b"NOOP"}:
                    self.wfile.write(b"250 OK\r\n")
                elif verb == b"DATA":
                    self.wfile.write(b"354 End with dot\r\n")
                    chunks = []
                    while (chunk := self.rfile.readline()) and chunk != b".\r\n":
                        chunks.append(chunk[1:] if chunk.startswith(b"..") else chunk)
                    if state["refuse"]:
                        state["refuse"] -= 1
                        self.wfile.write(b"451 Temporary delivery failure\r\n")
                    else:
                        state["messages"].append(BytesParser(policy=policy.default).parsebytes(b"".join(chunks)))
                        self.wfile.write(b"250 Message accepted\r\n")
                elif verb == b"QUIT":
                    self.wfile.write(b"221 Bye\r\n")
                    return
                else:
                    self.wfile.write(b"502 Unsupported command\r\n")

    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), SMTPHandler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    settings = get_settings()
    for key, value in {"mail_delivery_mode": "smtp", "smtp_host": "127.0.0.1", "smtp_port": server.server_address[1],
                       "smtp_security": "none", "smtp_from_email": "noreply@example.com",
                       "smtp_username": "", "smtp_password": None, "mail_retry_seconds": 1}.items():
        monkeypatch.setattr(settings, key, value)
    yield state
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def test_disabled_delivery_does_not_claim_that_recovery_mail_was_sent(client, catalog, monkeypatch):
    monkeypatch.setenv("MAIL_DELIVERY_MODE", "disabled")
    get_settings.cache_clear()
    try:
        known = client.post("/api/v1/auth/forgot-password", json={"email": "traveler@example.com"})
        unknown = client.post("/api/v1/auth/forgot-password", json={"email": "unknown@example.com"})
        assert known.status_code == unknown.status_code == 503
        assert known.json() == unknown.json()
        assert "token" not in known.text
    finally:
        get_settings.cache_clear()


def test_smtp_recovery_is_transactional_delivered_and_one_use(client, catalog, db, smtp_server):
    response = client.post("/api/v1/auth/forgot-password", json={"email": "traveler@example.com"})
    assert response.status_code == 200 and response.json()["delivery"] == "email"
    assert not smtp_server["messages"]
    assert db.scalar(select(func.count()).select_from(DemoEmail)) == 0
    message = db.scalar(select(OutboundEmail))
    assert message is not None and message.state == "pending"
    assert process_mail_queue(db)["sent"] == 1
    assert len(smtp_server["messages"]) == 1
    received = smtp_server["messages"][0]
    assert received["To"] == "traveler@example.com"
    assert received["From"] == "noreply@example.com"
    assert "восстановление пароля" in received["Subject"]
    token = re.search(r"token=([A-Za-z0-9_-]+)", received.get_content()).group(1)
    result = client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": "Delivered-recovery-password-2026"})
    assert result.status_code == 200
    assert client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": "Another-password-2026"}).status_code == 422
    db.refresh(message)
    assert message.state == "sent" and message.body == "" and message.sent_at is not None
    assert process_mail_queue(db)["sent"] == 0
    assert len(smtp_server["messages"]) == 1


def test_smtp_failure_retries_after_delay_without_losing_message(client, catalog, db, smtp_server):
    smtp_server["refuse"] = 1
    assert client.post("/api/v1/auth/forgot-password", json={"email": "traveler@example.com"}).status_code == 200
    assert process_mail_queue(db)["retried"] == 1
    message = db.scalar(select(OutboundEmail))
    assert message.state == "pending" and message.attempts == 1
    assert message.error_code == "SMTPDataError"
    assert not smtp_server["messages"]
    assert process_mail_queue(db)["sent"] == 0
    message.next_attempt_at = utc_now() - timedelta(seconds=1)
    db.commit()
    assert process_mail_queue(db)["sent"] == 1
    assert len(smtp_server["messages"]) == 1


def test_replaced_reset_is_not_emailed_and_queue_metadata_is_admin_only(client, catalog, db, smtp_server):
    for _ in range(2):
        assert client.post("/api/v1/auth/forgot-password", json={"email": "traveler@example.com"}).status_code == 200
    result = process_mail_queue(db)
    assert result["cancelled"] == result["sent"] == 1
    assert len(smtp_server["messages"]) == 1
    path = "/api/v1/admin/mail-delivery"
    assert client.get(path, headers=headers(catalog["traveler"])).status_code == 403
    result = client.get(path, headers=headers(catalog["admin"]))
    assert result.status_code == 200
    assert result.json()["counts"]["sent"] == 1
    assert "body" not in result.text and "token=" not in result.text


def test_failed_message_can_be_requeued_by_admin_within_link_lifetime(client, catalog, db, smtp_server, monkeypatch):
    monkeypatch.setattr(get_settings(), "mail_max_attempts", 1)
    smtp_server["refuse"] = 1
    client.post("/api/v1/auth/forgot-password", json={"email": "traveler@example.com"})
    assert process_mail_queue(db)["failed"] == 1
    message = db.scalar(select(OutboundEmail))
    path = f"/api/v1/admin/mail-delivery/{message.id}/retry"
    assert client.post(path, headers=headers(catalog["vendor"])).status_code == 403
    assert client.post(path, headers=headers(catalog["admin"])).status_code == 200
    assert process_mail_queue(db)["sent"] == 1
    assert client.post(path, headers=headers(catalog["admin"])).status_code == 409


def test_queue_rollback_and_expired_link_never_send_mail(client, catalog, db, smtp_server):
    get_mail_delivery().deliver(db, "traveler@example.com", "Transaction rollback", "Must not leave the transaction")
    db.rollback()
    assert process_mail_queue(db)["sent"] == 0
    client.post("/api/v1/auth/forgot-password", json={"email": "traveler@example.com"})
    message = db.scalar(select(OutboundEmail))
    message.password_reset.expires_at = utc_now() - timedelta(seconds=1)
    db.commit()
    assert process_mail_queue(db)["cancelled"] == 1
    assert not smtp_server["messages"]


@pytest.mark.postgres
def test_concurrent_mail_workers_do_not_deliver_the_same_queue_row_twice(client, catalog, smtp_server):
    if engine.dialect.name != "postgresql":
        pytest.skip("Queue concurrency requires PostgreSQL")
    client.post("/api/v1/auth/forgot-password", json={"email": "traveler@example.com"})

    def work(_):
        with SessionLocal() as db:
            return process_mail_queue(db, batch_size=1)["sent"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        counts = list(pool.map(work, range(2)))
    assert sum(counts) == 1 and len(smtp_server["messages"]) == 1

"""Persistent demo provider; no network, real instruments, PAN or CVC persistence.

A real provider implements PaymentProvider against its own API and signed webhook
verification. Transport calls belong outside row-lock transactions; reconciliation
applies their persisted outcome under the booking lock.
"""
from typing import Protocol
from app.domain.models import ProviderOperation

TEST_INSTRUMENTS = (
    {"id": "demo_success", "card_number": "4242424242424242", "name": "Успешная оплата", "scenario": "success"},
    {"id": "demo_insufficient", "card_number": "4000000000009995", "name": "Недостаточно средств", "scenario": "insufficient_funds"},
    {"id": "demo_declined", "card_number": "4000000000000002", "name": "Отказ банка", "scenario": "bank_declined"},
    {"id": "demo_3ds", "card_number": "4000000000003220", "name": "Подтверждение 3-D Secure", "scenario": "3ds"},
    {"id": "demo_unavailable", "card_number": "4000000000000119", "name": "Сервис недоступен", "scenario": "provider_unavailable"},
    {"id": "demo_timeout", "card_number": "4000000000009235", "name": "Тайм-аут с поздним успехом", "scenario": "timeout_success"},
    {"id": "demo_timeout_failure", "card_number": "4000000000000341", "name": "Тайм-аут с поздним отказом", "scenario": "timeout_failure"},
)


class PaymentProvider(Protocol):
    def create_payment(self, db, amount, currency, scenario) -> ProviderOperation: ...
    def get_operation(self, db, operation_id) -> ProviderOperation: ...
    def create_refund(self, db, amount, currency, scenario) -> ProviderOperation: ...


class DemoPaymentProvider:
    def create_payment(self, db, amount, currency, scenario):
        status = "pending" if scenario == "3ds" else "succeeded" if scenario in ("success", "timeout_success") else "failed"
        operation = ProviderOperation(kind="payment", amount=amount, currency=currency, scenario=scenario, status=status)
        db.add(operation)
        db.flush()
        return operation

    def get_operation(self, db, operation_id):
        return db.get(ProviderOperation, operation_id)

    def create_refund(self, db, amount, currency, scenario):
        operation = ProviderOperation(kind="refund", amount=amount, currency=currency, scenario=scenario,
                                      status="failed" if scenario == "temporary_failure" else "pending" if scenario == "processing" else "succeeded")
        db.add(operation)
        db.flush()
        return operation


provider = DemoPaymentProvider()

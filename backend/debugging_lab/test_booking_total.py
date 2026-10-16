from decimal import Decimal

import pytest

from debugging_lab.booking_total import calculate_booking_total


def test_calculate_booking_total_includes_service_fee() -> None:
    assert calculate_booking_total(Decimal("125.00"), 2, Decimal("10.00")) == Decimal(
        "260.00"
    )


def test_zero_tickets_still_returns_service_fee() -> None:
    assert calculate_booking_total(Decimal("125.00"), 0, Decimal("10.00")) == Decimal(
        "10.00"
    )


def test_negative_ticket_count_is_rejected() -> None:
    with pytest.raises(ValueError, match="must not be negative"):
        calculate_booking_total(Decimal("125.00"), -1, Decimal("10.00"))

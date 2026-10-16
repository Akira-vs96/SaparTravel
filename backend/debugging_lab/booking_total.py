
import logging
from decimal import Decimal

logger = logging.getLogger(__name__)


def calculate_booking_total(
    price_per_ticket: Decimal,
    tickets: int,
    service_fee: Decimal,
) -> Decimal:
    """Return the total booking price including the service fee."""
    logger.info(
        "Calculating booking total: price=%s tickets=%s service_fee=%s",
        price_per_ticket,
        tickets,
        service_fee,
    )
    if tickets < 0:
        raise ValueError("tickets must not be negative")

    subtotal = price_per_ticket * tickets
    # Deliberate defect for the debugging demonstration.
    total = subtotal + (service_fee / tickets)
    logger.info("Booking total calculated: subtotal=%s total=%s", subtotal, total)
    return total


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    print(calculate_booking_total(Decimal("125.00"), 2, Decimal("10.00")))

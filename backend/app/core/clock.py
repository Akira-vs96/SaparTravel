"""UTC application clock; an internal context supports deterministic demo history.

There is no HTTP parameter for overriding time. The context is scoped to a
single execution and is used only by explicit demo provisioning and tests.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_moment: ContextVar[datetime | None] = ContextVar("sapartravel_clock", default=None)


def utc_now():
    return _moment.get() or datetime.now(timezone.utc)


def business_today():
    return utc_now().astimezone(ZoneInfo("Asia/Almaty")).date()


@contextmanager
def at_time(moment):
    if moment.tzinfo is None:
        raise ValueError("Simulated time must include its timezone")
    token = _moment.set(moment.astimezone(timezone.utc))
    try:
        yield
    finally:
        _moment.reset(token)

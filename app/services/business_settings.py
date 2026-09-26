"""Business figures a workspace sets once, used to turn bookings into estimated revenue."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from sqlalchemy.orm import Session

from app.models.tenant import Tenant

CURRENCIES = ("INR", "USD", "EUR", "GBP", "AED", "SGD", "AUD", "CAD")


@dataclass
class BusinessSettings:
    booking_value: float | None = None  # average revenue from one booked appointment
    currency: str = "INR"


def read(tenant: Tenant | None) -> BusinessSettings:
    try:
        raw = json.loads((tenant.business_settings if tenant else None) or "{}")
    except ValueError:
        raw = {}
    return BusinessSettings(**{k: v for k, v in raw.items() if k in BusinessSettings.__dataclass_fields__})


def save(db: Session, tenant: Tenant, value: BusinessSettings) -> BusinessSettings:
    if value.booking_value is not None and not (0 <= value.booking_value <= 10_000_000):
        raise ValueError("Booking value must be between 0 and 10,000,000.")
    if value.currency not in CURRENCIES:
        raise ValueError(f"Currency must be one of {', '.join(CURRENCIES)}.")
    tenant.business_settings = json.dumps(asdict(value))
    db.commit()
    return value

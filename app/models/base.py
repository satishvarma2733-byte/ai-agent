from datetime import datetime, timezone
from sqlalchemy import Column, DateTime
from app.core.database import Base

class TimestampMixin:
    """Mixin to automatically inject created_at and updated_at datetime properties."""
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )

class SoftDeleteMixin:
    """Mixin adding support for logical soft deletion of records."""
    deleted_at = Column(DateTime, nullable=True)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def delete(self, commit_datetime: datetime | None = None) -> None:
        self.deleted_at = commit_datetime or datetime.now(timezone.utc)

import enum
from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Deterministic constraint names keep Alembic migrations stable on MySQL.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def utcnow() -> datetime:
    """Naive UTC timestamp (MySQL DATETIME has no time zone)."""
    return datetime.now(UTC).replace(tzinfo=None)


class TimestampMixin:
    # Set in Python so values are known after INSERT/UPDATE without a re-select; the server
    # default covers rows written outside the ORM. Connections run with time_zone = UTC.
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, server_default=func.current_timestamp(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow,
        onupdate=utcnow,
        server_default=func.current_timestamp(),
        nullable=False,
    )


def db_enum(enum_cls: type[enum.Enum]) -> Enum:
    """Native MySQL ENUM storing the member *values* (lower-case strings) rather than names."""
    return Enum(
        enum_cls,
        values_callable=lambda e: [m.value for m in e],
        name=enum_cls.__name__.lower(),
        validate_strings=True,
    )

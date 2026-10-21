"""Member and parent portal: family accounts, sign-in codes, portal sessions and the log of
messages sent to families."""

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm import relationship as orm_relationship

from app.models.base import Base, TimestampMixin, db_enum, utcnow
from app.models.dojo import Member


class Relationship(enum.StrEnum):
    FATHER = "father"
    MOTHER = "mother"
    GUARDIAN = "guardian"  # legal guardian
    OTHER = "other"  # other family


class Guardian(TimestampMixin, Base):
    """A parent or guardian. One guardian can be linked to several children (a family)."""

    __tablename__ = "guardians"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(150))
    # +965XXXXXXXX: the number they sign in to the portal with.
    mobile: Mapped[str] = mapped_column(String(16), index=True)
    email: Mapped[str | None] = mapped_column(String(255))

    links: Mapped[list["GuardianLink"]] = orm_relationship(
        back_populates="guardian", cascade="all, delete-orphan", lazy="raise"
    )


class GuardianLink(Base):
    __tablename__ = "guardian_members"

    guardian_id: Mapped[int] = mapped_column(
        ForeignKey("guardians.id", ondelete="CASCADE"), primary_key=True
    )
    member_id: Mapped[int] = mapped_column(
        ForeignKey("members.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    relationship: Mapped[Relationship] = mapped_column(db_enum(Relationship))
    # The primary guardian pays and receives messages.
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")

    guardian: Mapped[Guardian] = orm_relationship(back_populates="links", lazy="joined")
    member: Mapped[Member] = orm_relationship(lazy="raise")


class PortalCode(Base):
    """A one-time sign-in code sent by WhatsApp. Stored only as a keyed hash."""

    __tablename__ = "portal_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    mobile: Mapped[str] = mapped_column(String(16), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    attempts: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    used_at: Mapped[datetime | None] = mapped_column(DateTime)


class PortalSession(Base):
    """A signed-in family. The session belongs to a guardian, or to an adult member who signs
    in for themselves; everything the portal shows is reached through that profile."""

    __tablename__ = "portal_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    mobile: Mapped[str] = mapped_column(String(16))
    guardian_id: Mapped[int | None] = mapped_column(
        ForeignKey("guardians.id", ondelete="CASCADE"), index=True
    )
    member_id: Mapped[int | None] = mapped_column(
        ForeignKey("members.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(255))


class MessageCategory(enum.StrEnum):
    ESSENTIAL = "essential"  # sign-in codes, receipts, booking confirmations: always sent
    SERVICE = "service"  # reminders, test days, progress notes: families can turn these off
    MARKETING = "marketing"  # news and offers: only to families who opted in
    STAFF = "staff"


class MessageStatus(enum.StrEnum):
    SENT = "sent"
    SKIPPED = "skipped"  # the family turned these off
    FAILED = "failed"


class MessageLog(Base):
    """Every WhatsApp / SMS message the system sends (or skips), with its category."""

    __tablename__ = "message_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    to: Mapped[str] = mapped_column(String(32), index=True)
    channel: Mapped[str] = mapped_column(String(10), default="whatsapp")
    category: Mapped[MessageCategory] = mapped_column(db_enum(MessageCategory))
    kind: Mapped[str] = mapped_column(String(40), default="")
    text: Mapped[str] = mapped_column(Text)
    member_id: Mapped[int | None] = mapped_column(ForeignKey("members.id", ondelete="SET NULL"))
    status: Mapped[MessageStatus] = mapped_column(db_enum(MessageStatus))
    error: Mapped[str | None] = mapped_column(String(255))
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

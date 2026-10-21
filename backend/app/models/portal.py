"""Member and parent portal: family accounts, sign-in codes, portal sessions and the log of
messages sent to families."""

import enum
import secrets
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm import relationship as orm_relationship

from app.models.base import Base, TimestampMixin, db_enum, utcnow
from app.models.dojo import KD, Member, PaymentMethod


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
    full_name_ar: Mapped[str | None] = mapped_column(String(150))
    # +965XXXXXXXX: the number they sign in to the portal with.
    mobile: Mapped[str] = mapped_column(String(16), index=True)
    email: Mapped[str | None] = mapped_column(String(255))
    # Language for WhatsApp messages: the one they last used in the portal (Arabic until then).
    language: Mapped[str] = mapped_column(String(2), default="ar", server_default="ar")

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


# ---------------------------------------------------------------- online renewals
class RenewalStatus(enum.StrEnum):
    PENDING = "pending"  # waiting for payment
    PAID = "paid"
    FAILED = "failed"


def renewal_reference() -> str:
    return "EA-REN-" + utcnow().strftime("%Y%m%d") + "-" + secrets.token_hex(3).upper()


class RenewalPayment(Base):
    """A membership renewal paid online from the portal through the payment gateway."""

    __tablename__ = "renewal_payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(30), unique=True, default=renewal_reference)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"), index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("membership_plans.id"))
    amount: Mapped[Decimal] = mapped_column(KD)
    method: Mapped[PaymentMethod] = mapped_column(db_enum(PaymentMethod))
    status: Mapped[RenewalStatus] = mapped_column(
        db_enum(RenewalStatus), default=RenewalStatus.PENDING, server_default="pending"
    )
    gateway_reference: Mapped[str | None] = mapped_column(String(80))
    # Who started it: the signed-in guardian, or the adult member themselves.
    guardian_id: Mapped[int | None] = mapped_column(ForeignKey("guardians.id", ondelete="SET NULL"))
    by_member_id: Mapped[int | None] = mapped_column(ForeignKey("members.id", ondelete="SET NULL"))
    membership_id: Mapped[int | None] = mapped_column(ForeignKey("memberships.id"))
    payment_id: Mapped[int | None] = mapped_column(ForeignKey("payments.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime)


# ---------------------------------------------------------------- freezes
class RequestKind(enum.StrEnum):
    FREEZE = "freeze"


class RequestStatus(enum.StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class MembershipRequest(Base):
    """A change to a membership that the operations manager decides (a freeze)."""

    __tablename__ = "membership_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[RequestKind] = mapped_column(db_enum(RequestKind))
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), index=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"), index=True)
    membership_id: Mapped[int] = mapped_column(ForeignKey("memberships.id"), index=True)
    freeze_start: Mapped[date | None] = mapped_column(Date)
    freeze_weeks: Mapped[int | None] = mapped_column(SmallInteger)
    reason: Mapped[str] = mapped_column(String(255))
    status: Mapped[RequestStatus] = mapped_column(
        db_enum(RequestStatus), default=RequestStatus.PENDING, server_default="pending"
    )
    # Requested in the portal (by the family) or logged by staff.
    from_portal: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)
    decision_note: Mapped[str | None] = mapped_column(String(255))


class MembershipFreeze(Base):
    """An approved freeze: the membership does not run between these dates."""

    __tablename__ = "membership_freezes"

    id: Mapped[int] = mapped_column(primary_key=True)
    membership_id: Mapped[int] = mapped_column(
        ForeignKey("memberships.id", ondelete="CASCADE"), index=True
    )
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    request_id: Mapped[int | None] = mapped_column(ForeignKey("membership_requests.id"))


# ---------------------------------------------------------------- message choices
class FamilyPreference(Base):
    """Per family mobile: whether service messages (reminders, test days, progress notes) are
    sent. Essential messages (sign-in codes, receipts, class changes) always are."""

    __tablename__ = "family_preferences"

    id: Mapped[int] = mapped_column(primary_key=True)
    mobile: Mapped[str] = mapped_column(String(16), unique=True)
    service_messages: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class MessagingOptIn(Base):
    """News and offers by WhatsApp: each choice is kept; the newest one counts."""

    __tablename__ = "messaging_opt_ins"

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id", ondelete="CASCADE"), index=True)
    opted_in: Mapped[bool] = mapped_column(Boolean)
    source: Mapped[str] = mapped_column(String(20))  # portal or desk
    recorded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

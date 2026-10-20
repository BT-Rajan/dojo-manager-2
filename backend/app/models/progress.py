"""Student progression (belt gradings, seminars) and day-to-day operations records."""

import enum
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, db_enum


class GradingStatus(enum.StrEnum):
    PLANNED = "planned"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class GradingOutcome(enum.StrEnum):
    PENDING = "pending"
    PASS = "pass"  # noqa: S105 - not a secret
    FAIL = "fail"
    DEFERRED = "deferred"


class ContactMethod(enum.StrEnum):
    WHATSAPP = "whatsapp"
    CALL = "call"
    SMS = "sms"
    EMAIL = "email"
    IN_PERSON = "in_person"


class FollowUpOutcome(enum.StrEnum):
    RENEWED = "renewed"
    WILL_RENEW = "will_renew"
    NOT_RENEWING = "not_renewing"
    NO_ANSWER = "no_answer"
    OTHER = "other"


class IncidentType(enum.StrEnum):
    INJURY = "injury"
    SAFETY_HAZARD = "safety_hazard"
    CONDUCT = "conduct"
    OTHER = "other"


class CaseStatus(enum.StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class Channel(enum.StrEnum):
    DESK = "desk"
    WHATSAPP = "whatsapp"
    AI_AGENT = "ai_agent"
    CALL = "call"
    EMAIL = "email"
    OTHER = "other"


class GradingEvent(TimestampMixin, Base):
    __tablename__ = "grading_events"
    __table_args__ = (Index("ix_grading_events_branch_date", "branch_id", "event_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"))
    title: Mapped[str] = mapped_column(String(150))
    event_date: Mapped[date] = mapped_column(Date)
    examiner_instructor_id: Mapped[int | None] = mapped_column(ForeignKey("instructors.id"))
    status: Mapped[GradingStatus] = mapped_column(
        db_enum(GradingStatus), default=GradingStatus.PLANNED, server_default="planned"
    )
    notes: Mapped[str | None] = mapped_column(Text)


class GradingResult(TimestampMixin, Base):
    __tablename__ = "grading_results"
    __table_args__ = (UniqueConstraint("event_id", "member_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("grading_events.id", ondelete="CASCADE"))
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"), index=True)
    from_rank_id: Mapped[int | None] = mapped_column(ForeignKey("belt_ranks.id"))
    from_stripes: Mapped[int] = mapped_column(SmallInteger, default=0)
    to_rank_id: Mapped[int | None] = mapped_column(ForeignKey("belt_ranks.id"))
    to_stripes: Mapped[int] = mapped_column(SmallInteger, default=0)
    outcome: Mapped[GradingOutcome] = mapped_column(
        db_enum(GradingOutcome), default=GradingOutcome.PENDING, server_default="pending"
    )
    notes: Mapped[str | None] = mapped_column(String(255))


class Seminar(TimestampMixin, Base):
    """Self-defence & traditional seminars; attendance earns points needed for promotion."""

    __tablename__ = "seminars"

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), index=True)
    title: Mapped[str] = mapped_column(String(150))
    seminar_date: Mapped[date] = mapped_column(Date)
    instructor_id: Mapped[int | None] = mapped_column(ForeignKey("instructors.id"))
    points: Mapped[int] = mapped_column(SmallInteger, default=1, server_default="1")
    notes: Mapped[str | None] = mapped_column(Text)


seminar_attendance = Table(
    "seminar_attendance",
    Base.metadata,
    Column("seminar_id", ForeignKey("seminars.id", ondelete="CASCADE"), primary_key=True),
    Column("member_id", ForeignKey("members.id"), primary_key=True, index=True),
)


class RenewalFollowUp(Base):
    """Contact made with a member whose membership has expired or is about to."""

    __tablename__ = "renewal_followups"
    __table_args__ = (Index("ix_renewal_followups_branch_at", "branch_id", "contacted_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"))
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"), index=True)
    membership_id: Mapped[int | None] = mapped_column(ForeignKey("memberships.id"))
    method: Mapped[ContactMethod] = mapped_column(db_enum(ContactMethod))
    outcome: Mapped[FollowUpOutcome] = mapped_column(db_enum(FollowUpOutcome))
    next_action: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(String(255))
    contacted_at: Mapped[datetime] = mapped_column(DateTime)
    contacted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class Incident(TimestampMixin, Base):
    __tablename__ = "incidents"
    __table_args__ = (Index("ix_incidents_branch_status", "branch_id", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"))
    ref_no: Mapped[str | None] = mapped_column(String(30), unique=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime)
    type: Mapped[IncidentType] = mapped_column(db_enum(IncidentType))
    session_id: Mapped[int | None] = mapped_column(
        ForeignKey("class_sessions.id", ondelete="SET NULL")
    )
    member_id: Mapped[int | None] = mapped_column(ForeignKey("members.id"))
    persons_involved: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    action_taken: Mapped[str | None] = mapped_column(Text)
    guardian_informed: Mapped[str | None] = mapped_column(String(255))
    witnesses: Mapped[str | None] = mapped_column(String(255))
    reported_to_manager_at: Mapped[datetime | None] = mapped_column(DateTime)
    reported_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[CaseStatus] = mapped_column(
        db_enum(CaseStatus), default=CaseStatus.OPEN, server_default="open"
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)


class Complaint(TimestampMixin, Base):
    __tablename__ = "complaints"
    __table_args__ = (Index("ix_complaints_branch_status", "branch_id", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"))
    ref_no: Mapped[str | None] = mapped_column(String(30), unique=True)
    received_on: Mapped[date] = mapped_column(Date)
    member_id: Mapped[int | None] = mapped_column(ForeignKey("members.id"))
    contact_name: Mapped[str] = mapped_column(String(150))
    contact_phone: Mapped[str | None] = mapped_column(String(30))
    channel: Mapped[Channel] = mapped_column(db_enum(Channel))
    description: Mapped[str] = mapped_column(Text)
    handled_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    escalated: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    outcome: Mapped[str | None] = mapped_column(Text)
    member_informed_on: Mapped[date | None] = mapped_column(Date)
    status: Mapped[CaseStatus] = mapped_column(
        db_enum(CaseStatus), default=CaseStatus.OPEN, server_default="open"
    )
    closed_on: Mapped[date | None] = mapped_column(Date)

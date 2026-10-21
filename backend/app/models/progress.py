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


# ---------------------------------------------------------------- curriculum and progress
class Track(enum.StrEnum):
    KICKBOXING = "kickboxing"
    JIUJITSU = "jiujitsu"
    SELF_DEFENCE = "self_defence"


class BeltSkill(Base):
    """A skill a student learns at a belt, in one of the three tracks."""

    __tablename__ = "belt_skills"

    id: Mapped[int] = mapped_column(primary_key=True)
    belt_rank_id: Mapped[int] = mapped_column(
        ForeignKey("belt_ranks.id", ondelete="CASCADE"), index=True
    )
    track: Mapped[Track] = mapped_column(db_enum(Track))
    category: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(120))
    sort_order: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")


class SkillCheck(Base):
    """A skill the student has shown, ticked off by a coach."""

    __tablename__ = "member_skill_checks"

    member_id: Mapped[int] = mapped_column(
        ForeignKey("members.id", ondelete="CASCADE"), primary_key=True
    )
    skill_id: Mapped[int] = mapped_column(
        ForeignKey("belt_skills.id", ondelete="CASCADE"), primary_key=True
    )
    checked_on: Mapped[date] = mapped_column(Date)
    checked_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class Evaluation(TimestampMixin, Base):
    """A coach's evaluation every 4–6 weeks: notes for the family and whether the student is
    ready for the next belt test."""

    __tablename__ = "evaluations"

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id", ondelete="CASCADE"), index=True)
    belt_rank_id: Mapped[int | None] = mapped_column(ForeignKey("belt_ranks.id"))
    eval_date: Mapped[date] = mapped_column(Date)
    instructor_id: Mapped[int | None] = mapped_column(ForeignKey("instructors.id"))
    notes: Mapped[str | None] = mapped_column(Text)
    ready_for_test: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    recorded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class NoteStatus(enum.StrEnum):
    DRAFT = "draft"
    SENT = "sent"


class ProgressNote(TimestampMixin, Base):
    """The monthly note to the family: what the student worked on and what comes next."""

    __tablename__ = "progress_notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id", ondelete="CASCADE"), index=True)
    month: Mapped[date] = mapped_column(Date)  # first day of the month described
    instructor_id: Mapped[int | None] = mapped_column(ForeignKey("instructors.id"))
    worked_on: Mapped[str] = mapped_column(Text)
    next_steps: Mapped[str] = mapped_column(Text)
    status: Mapped[NoteStatus] = mapped_column(
        db_enum(NoteStatus), default=NoteStatus.DRAFT, server_default="draft"
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


# ---------------------------------------------------------------- consent and rules
class MediaConsent(Base):
    """Photo and video consent (EA-MKT-FRM-01). Each change is a new row, so the history of
    what was agreed and when is kept; the newest row is the member's current consent."""

    __tablename__ = "media_consents"

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id", ondelete="CASCADE"), index=True)
    internal_records: Mapped[bool] = mapped_column(Boolean, default=False)
    social_media: Mapped[bool] = mapped_column(Boolean, default=False)
    website_marketing: Mapped[bool] = mapped_column(Boolean, default=False)
    signed_by_name: Mapped[str] = mapped_column(String(150))  # parent/guardian, or the adult
    signed_at: Mapped[datetime] = mapped_column(DateTime)
    recorded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    from_portal: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    notes: Mapped[str | None] = mapped_column(String(255))


RULES_VERSION = "2026-1"


class RulesAgreement(Base):
    """Agreement to the academy rules and safety instructions."""

    __tablename__ = "rules_agreements"

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id", ondelete="CASCADE"), index=True)
    rules_version: Mapped[str] = mapped_column(String(20), default=RULES_VERSION)
    signed_by_name: Mapped[str] = mapped_column(String(150))
    signature: Mapped[str] = mapped_column(String(255))  # "typed:<name>" when signed in the portal
    signed_at: Mapped[datetime] = mapped_column(DateTime)
    recorded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    from_portal: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")

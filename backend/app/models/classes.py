import enum
from datetime import date, datetime, time

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, db_enum
from app.models.dojo import Member


class SessionStatus(enum.StrEnum):
    SCHEDULED = "scheduled"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class AttendanceStatus(enum.StrEnum):
    BOOKED = "booked"
    PRESENT = "present"
    LATE = "late"
    ABSENT = "absent"
    EXCUSED = "excused"


class LeaveType(enum.StrEnum):
    ANNUAL = "annual"
    SICK = "sick"
    EMERGENCY = "emergency"
    OTHER = "other"


class LeadSource(enum.StrEnum):
    WALK_IN = "walk_in"
    WHATSAPP = "whatsapp"
    AI_AGENT = "ai_agent"
    WEBSITE = "website"
    PHONE = "phone"
    REFERRAL = "referral"
    SOCIAL = "social"
    OTHER = "other"


class LeadStatus(enum.StrEnum):
    NEW = "new"
    CONTACTED = "contacted"
    TRIAL_BOOKED = "trial_booked"
    TRIAL_ATTENDED = "trial_attended"
    CONVERTED = "converted"
    LOST = "lost"


class ClassSchedule(TimestampMixin, Base):
    """A weekly recurring class slot. ``weekday`` follows ISO numbering: 1 = Monday … 7 = Sunday."""

    __tablename__ = "class_schedules"
    __table_args__ = (
        CheckConstraint("weekday BETWEEN 1 AND 7", name="weekday_range"),
        CheckConstraint("end_time > start_time", name="time_order"),
        Index("ix_class_schedules_branch_day", "branch_id", "weekday", "start_time"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"))
    program_id: Mapped[int] = mapped_column(ForeignKey("programs.id"))
    instructor_id: Mapped[int | None] = mapped_column(ForeignKey("instructors.id"))
    title: Mapped[str | None] = mapped_column(String(100))
    weekday: Mapped[int] = mapped_column(SmallInteger)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    capacity: Mapped[int] = mapped_column(SmallInteger, default=20, server_default="20")
    room: Mapped[str | None] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")


class ClassSession(TimestampMixin, Base):
    """A dated class occurrence, generated from a schedule or added ad hoc."""

    __tablename__ = "class_sessions"
    __table_args__ = (
        UniqueConstraint("schedule_id", "session_date"),
        CheckConstraint("end_time > start_time", name="time_order"),
        Index("ix_class_sessions_branch_date", "branch_id", "session_date", "start_time"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"))
    schedule_id: Mapped[int | None] = mapped_column(
        ForeignKey("class_schedules.id", ondelete="SET NULL")
    )
    program_id: Mapped[int] = mapped_column(ForeignKey("programs.id"))
    instructor_id: Mapped[int | None] = mapped_column(ForeignKey("instructors.id"), index=True)
    title: Mapped[str | None] = mapped_column(String(100))
    session_date: Mapped[date] = mapped_column(Date)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    capacity: Mapped[int] = mapped_column(SmallInteger, default=20, server_default="20")
    status: Mapped[SessionStatus] = mapped_column(
        db_enum(SessionStatus), default=SessionStatus.SCHEDULED, server_default="scheduled"
    )
    # Class change notice: why it was cancelled or rescheduled, and when members were told.
    change_reason: Mapped[str | None] = mapped_column(String(255))
    members_notified_at: Mapped[datetime | None] = mapped_column(DateTime)


class Attendance(Base):
    __tablename__ = "attendance"
    __table_args__ = (UniqueConstraint("session_id", "member_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("class_sessions.id", ondelete="CASCADE"))
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"), index=True)
    status: Mapped[AttendanceStatus] = mapped_column(db_enum(AttendanceStatus))
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime)
    recorded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    member: Mapped[Member] = relationship(lazy="raise")


class InstructorLeave(TimestampMixin, Base):
    __tablename__ = "instructor_leaves"
    __table_args__ = (CheckConstraint("end_date >= start_date", name="date_order"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    instructor_id: Mapped[int] = mapped_column(ForeignKey("instructors.id"), index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), index=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    type: Mapped[LeaveType] = mapped_column(db_enum(LeaveType))
    reason: Mapped[str | None] = mapped_column(String(255))
    cover_instructor_id: Mapped[int | None] = mapped_column(ForeignKey("instructors.id"))


class Lead(TimestampMixin, Base):
    """A prospective student, from first enquiry through trial class to sign-up."""

    __tablename__ = "leads"
    __table_args__ = (Index("ix_leads_branch_status", "branch_id", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"))
    full_name: Mapped[str] = mapped_column(String(150))
    phone: Mapped[str] = mapped_column(String(30), index=True)
    email: Mapped[str | None] = mapped_column(String(255))
    age: Mapped[int | None] = mapped_column(SmallInteger)
    source: Mapped[LeadSource] = mapped_column(db_enum(LeadSource))
    program_id: Mapped[int | None] = mapped_column(ForeignKey("programs.id"))
    status: Mapped[LeadStatus] = mapped_column(
        db_enum(LeadStatus), default=LeadStatus.NEW, server_default="new"
    )
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    next_action: Mapped[str | None] = mapped_column(String(255))
    next_action_date: Mapped[date | None] = mapped_column(Date)
    trial_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("class_sessions.id", ondelete="SET NULL")
    )
    converted_member_id: Mapped[int | None] = mapped_column(ForeignKey("members.id"))
    lost_reason: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)

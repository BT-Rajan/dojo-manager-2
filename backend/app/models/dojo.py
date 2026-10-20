import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, db_enum
from app.models.org import Branch

KD = Numeric(10, 3)  # Kuwaiti dinar: 3 decimal places


class Discipline(enum.StrEnum):
    KAJUKENBO = "kajukenbo"
    KICKBOXING = "kickboxing"
    JIUJITSU = "jiujitsu"
    SELF_DEFENCE = "self_defence"
    FITNESS = "fitness"
    OPEN_MAT = "open_mat"
    OTHER = "other"


class BeltPhase(enum.StrEnum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    BLACK = "black"


class Gender(enum.StrEnum):
    MALE = "male"
    FEMALE = "female"


class MemberStatus(enum.StrEnum):
    ACTIVE = "active"
    FROZEN = "frozen"
    INACTIVE = "inactive"


class MembershipStatus(enum.StrEnum):
    ACTIVE = "active"
    FROZEN = "frozen"
    CANCELLED = "cancelled"


class PaymentMethod(enum.StrEnum):
    KNET = "knet"
    CARD = "card"  # Visa / Mastercard
    CASH = "cash"


class PaymentCategory(enum.StrEnum):
    NEW = "new"
    RENEWAL = "renewal"
    TRIAL_PASS = "trial_pass"  # noqa: S105 - not a secret
    DAY_PASS = "day_pass"  # noqa: S105 - not a secret
    EQUIPMENT = "equipment"
    OTHER = "other"


class Program(TimestampMixin, Base):
    """A class programme, e.g. Kids Kajukenbo or Adult Kickboxing."""

    __tablename__ = "programs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    discipline: Mapped[Discipline] = mapped_column(db_enum(Discipline))
    description: Mapped[str | None] = mapped_column(Text)
    min_age: Mapped[int | None] = mapped_column(SmallInteger)
    max_age: Mapped[int | None] = mapped_column(SmallInteger)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")


class BeltRank(TimestampMixin, Base):
    """Kajukenbo belt. The belt also marks the kickboxing level; stripes mark grappling level."""

    __tablename__ = "belt_ranks"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    color: Mapped[str] = mapped_column(String(20))
    sort_order: Mapped[int] = mapped_column(SmallInteger, unique=True)
    phase: Mapped[BeltPhase] = mapped_column(db_enum(BeltPhase))
    kickboxing_level: Mapped[str | None] = mapped_column(String(100))
    bjj_equivalent: Mapped[str | None] = mapped_column(String(100))
    seminars_required: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")


class Instructor(TimestampMixin, Base):
    __tablename__ = "instructors"

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), unique=True
    )
    full_name: Mapped[str] = mapped_column(String(150))
    phone: Mapped[str | None] = mapped_column(String(30))
    email: Mapped[str | None] = mapped_column(String(255))
    specialties: Mapped[str | None] = mapped_column(String(255))
    belt_rank_id: Mapped[int | None] = mapped_column(ForeignKey("belt_ranks.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")


class Member(TimestampMixin, Base):
    """A student of the academy."""

    __tablename__ = "members"
    __table_args__ = (
        Index("ix_members_branch_name", "branch_id", "last_name", "first_name"),
        CheckConstraint("stripes BETWEEN 0 AND 4", name="stripes_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"))
    member_no: Mapped[str | None] = mapped_column(String(20), unique=True)
    first_name: Mapped[str] = mapped_column(String(75))
    last_name: Mapped[str] = mapped_column(String(75))
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    gender: Mapped[Gender | None] = mapped_column(db_enum(Gender))
    civil_id: Mapped[str | None] = mapped_column(String(20), unique=True)
    phone: Mapped[str] = mapped_column(String(30), index=True)
    email: Mapped[str | None] = mapped_column(String(255))
    guardian_name: Mapped[str | None] = mapped_column(String(150))
    guardian_phone: Mapped[str | None] = mapped_column(String(30))
    emergency_contact_name: Mapped[str | None] = mapped_column(String(150))
    emergency_contact_phone: Mapped[str | None] = mapped_column(String(30))
    medical_notes: Mapped[str | None] = mapped_column(Text)
    media_consent: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    belt_rank_id: Mapped[int | None] = mapped_column(ForeignKey("belt_ranks.id"))
    stripes: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    status: Mapped[MemberStatus] = mapped_column(
        db_enum(MemberStatus), default=MemberStatus.ACTIVE, server_default="active", index=True
    )
    joined_on: Mapped[date] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)

    branch: Mapped[Branch] = relationship(lazy="raise")
    belt_rank: Mapped[BeltRank | None] = relationship(lazy="selectin")


class MembershipPlan(TimestampMixin, Base):
    __tablename__ = "membership_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"), index=True)
    program_id: Mapped[int | None] = mapped_column(ForeignKey("programs.id"))
    name: Mapped[str] = mapped_column(String(100))
    duration_days: Mapped[int] = mapped_column(SmallInteger)
    price: Mapped[Decimal] = mapped_column(KD)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")


class Membership(TimestampMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (Index("ix_memberships_branch_end", "branch_id", "end_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"), index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"))
    plan_id: Mapped[int] = mapped_column(ForeignKey("membership_plans.id"))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    price: Mapped[Decimal] = mapped_column(KD)
    status: Mapped[MembershipStatus] = mapped_column(
        db_enum(MembershipStatus), default=MembershipStatus.ACTIVE, server_default="active"
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    plan: Mapped[MembershipPlan] = relationship(lazy="selectin")
    member: Mapped[Member] = relationship(lazy="raise")


class Payment(Base):
    """Payments are append-only; mistakes are voided (with a reason), never edited or deleted."""

    __tablename__ = "payments"
    __table_args__ = (Index("ix_payments_branch_paid", "branch_id", "paid_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"))
    member_id: Mapped[int | None] = mapped_column(ForeignKey("members.id"), index=True)
    membership_id: Mapped[int | None] = mapped_column(ForeignKey("memberships.id"))
    amount: Mapped[Decimal] = mapped_column(KD)
    method: Mapped[PaymentMethod] = mapped_column(db_enum(PaymentMethod))
    category: Mapped[PaymentCategory] = mapped_column(db_enum(PaymentCategory))
    reference: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(String(255))
    paid_at: Mapped[datetime] = mapped_column(DateTime)
    received_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    is_void: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    void_reason: Mapped[str | None] = mapped_column(String(255))
    voided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime)

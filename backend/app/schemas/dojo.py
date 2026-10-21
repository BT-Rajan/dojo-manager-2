from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import EmailStr, Field, StringConstraints, computed_field, model_validator

from app.core.clock import today as academy_today
from app.models.dojo import (
    BeltPhase,
    Discipline,
    Gender,
    MembershipStatus,
    MemberStatus,
    PaymentCategory,
    PaymentMethod,
)
from app.schemas.common import InModel, LongText, Money, Name, OutModel, Phone, ShortText

Age = Annotated[int, Field(ge=3, le=99)]
Standing = Literal["active", "lapsed", "new", "frozen", "inactive"]
CivilId = Annotated[str, StringConstraints(pattern=r"^[0-9]{12}$")]  # Kuwaiti civil ID


# ---------------------------------------------------------------- programs
class ProgramIn(InModel):
    name: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    discipline: Discipline
    description: LongText | None = None
    min_age: Age | None = None
    max_age: Age | None = None
    is_active: bool = True

    @model_validator(mode="after")
    def _ages(self):
        if self.min_age and self.max_age and self.min_age > self.max_age:
            raise ValueError("min_age must not exceed max_age")
        return self


class ProgramUpdate(InModel):
    name: Annotated[str, StringConstraints(min_length=1, max_length=100)] | None = None
    discipline: Discipline | None = None
    description: LongText | None = None
    min_age: Age | None = None
    max_age: Age | None = None
    is_active: bool | None = None


class ProgramOut(OutModel):
    id: int
    name: str
    discipline: Discipline
    description: str | None
    min_age: int | None
    max_age: int | None
    is_active: bool


# ---------------------------------------------------------------- belts
class BeltIn(InModel):
    name: Annotated[str, StringConstraints(min_length=1, max_length=50)]
    color: Annotated[str, StringConstraints(min_length=1, max_length=20)]
    sort_order: Annotated[int, Field(ge=0, le=1000)]
    phase: BeltPhase
    bjj_stripe: Annotated[str, StringConstraints(max_length=100)] | None = None
    bjj_equivalent: Annotated[str, StringConstraints(max_length=100)] | None = None
    seminars_required: Annotated[int, Field(ge=0, le=100)] = 0
    name_ar: Annotated[str, StringConstraints(max_length=100)] | None = None
    bjj_stripe_ar: Annotated[str, StringConstraints(max_length=100)] | None = None
    min_classes: Annotated[int, Field(ge=0, le=1000)] = 0
    min_weeks: Annotated[int, Field(ge=0, le=520)] = 0
    min_evaluations: Annotated[int, Field(ge=0, le=50)] = 0


class BeltUpdate(InModel):
    name: Annotated[str, StringConstraints(min_length=1, max_length=50)] | None = None
    color: Annotated[str, StringConstraints(min_length=1, max_length=20)] | None = None
    sort_order: Annotated[int, Field(ge=0, le=1000)] | None = None
    phase: BeltPhase | None = None
    bjj_stripe: Annotated[str, StringConstraints(max_length=100)] | None = None
    bjj_equivalent: Annotated[str, StringConstraints(max_length=100)] | None = None
    seminars_required: Annotated[int, Field(ge=0, le=100)] | None = None
    name_ar: Annotated[str, StringConstraints(max_length=100)] | None = None
    bjj_stripe_ar: Annotated[str, StringConstraints(max_length=100)] | None = None
    min_classes: Annotated[int, Field(ge=0, le=1000)] | None = None
    min_weeks: Annotated[int, Field(ge=0, le=520)] | None = None
    min_evaluations: Annotated[int, Field(ge=0, le=50)] | None = None


class BeltOut(OutModel):
    id: int
    name: str
    color: str
    sort_order: int
    phase: BeltPhase
    bjj_stripe: str | None
    bjj_equivalent: str | None
    seminars_required: int
    name_ar: str | None = None
    bjj_stripe_ar: str | None = None
    min_classes: int = 0
    min_weeks: int = 0
    min_evaluations: int = 0


# ---------------------------------------------------------------- instructors
class InstructorIn(InModel):
    branch_id: int
    full_name: Name
    phone: Phone | None = None
    email: EmailStr | None = None
    specialties: ShortText | None = None
    belt_rank_id: int | None = None
    user_id: int | None = None
    is_active: bool = True


class InstructorUpdate(InModel):
    branch_id: int | None = None
    full_name: Name | None = None
    phone: Phone | None = None
    email: EmailStr | None = None
    specialties: ShortText | None = None
    belt_rank_id: int | None = None
    user_id: int | None = None
    is_active: bool | None = None


class InstructorOut(OutModel):
    id: int
    branch_id: int
    user_id: int | None
    full_name: str
    phone: str | None
    email: str | None
    specialties: str | None
    belt_rank_id: int | None
    is_active: bool


# ---------------------------------------------------------------- members
class _MemberFields(InModel):
    first_name: Annotated[str, StringConstraints(min_length=1, max_length=75)]
    last_name: Annotated[str, StringConstraints(min_length=1, max_length=75)]
    date_of_birth: date | None = None
    gender: Gender | None = None
    civil_id: CivilId | None = None
    phone: Phone
    email: EmailStr | None = None
    guardian_name: Name | None = None
    guardian_phone: Phone | None = None
    emergency_contact_name: Name | None = None
    emergency_contact_phone: Phone | None = None
    health_notes: LongText | None = None
    media_consent: bool = False
    belt_rank_id: int | None = None
    stripes: Annotated[int, Field(ge=0, le=4)] = 0
    notes: LongText | None = None

    @model_validator(mode="after")
    def _dob(self):
        if self.date_of_birth and self.date_of_birth > academy_today():
            raise ValueError("date_of_birth cannot be in the future")
        return self


class MemberIn(_MemberFields):
    branch_id: int
    joined_on: date | None = None


class MemberUpdate(InModel):
    branch_id: int | None = None
    first_name: Annotated[str, StringConstraints(min_length=1, max_length=75)] | None = None
    last_name: Annotated[str, StringConstraints(min_length=1, max_length=75)] | None = None
    date_of_birth: date | None = None
    gender: Gender | None = None
    civil_id: CivilId | None = None
    phone: Phone | None = None
    email: EmailStr | None = None
    guardian_name: Name | None = None
    guardian_phone: Phone | None = None
    emergency_contact_name: Name | None = None
    emergency_contact_phone: Phone | None = None
    health_notes: LongText | None = None
    media_consent: bool | None = None
    belt_rank_id: int | None = None
    stripes: Annotated[int, Field(ge=0, le=4)] | None = None
    status: MemberStatus | None = None
    notes: LongText | None = None


class MemberOut(OutModel):
    id: int
    branch_id: int
    member_no: str | None
    first_name: str
    last_name: str
    date_of_birth: date | None
    gender: Gender | None
    civil_id: str | None
    phone: str
    email: str | None
    guardian_name: str | None
    guardian_phone: str | None
    emergency_contact_name: str | None
    emergency_contact_phone: str | None
    health_notes: str | None
    media_consent: bool
    belt_rank_id: int | None
    belt_rank: BeltOut | None
    stripes: int
    status: MemberStatus
    standing: Standing = "new"
    joined_on: date
    notes: str | None

    @computed_field
    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @computed_field
    @property
    def age(self) -> int | None:
        if not self.date_of_birth:
            return None
        t, b = academy_today(), self.date_of_birth
        return t.year - b.year - ((t.month, t.day) < (b.month, b.day))


class MemberBrief(OutModel):
    id: int
    member_no: str | None
    first_name: str
    last_name: str
    phone: str
    branch_id: int


# ---------------------------------------------------------------- plans & memberships
class PlanIn(InModel):
    name: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    branch_id: int | None = None
    program_id: int | None = None
    duration_days: Annotated[int, Field(ge=1, le=730)]
    price: Money
    is_active: bool = True


class PlanUpdate(InModel):
    name: Annotated[str, StringConstraints(min_length=1, max_length=100)] | None = None
    program_id: int | None = None
    duration_days: Annotated[int, Field(ge=1, le=730)] | None = None
    price: Money | None = None
    is_active: bool | None = None


class PlanOut(OutModel):
    id: int
    name: str
    branch_id: int | None
    program_id: int | None
    duration_days: int
    price: Decimal
    is_active: bool


class InlinePayment(InModel):
    method: PaymentMethod
    reference: Annotated[str, StringConstraints(max_length=100)] | None = None


class MembershipIn(InModel):
    member_id: int
    plan_id: int
    start_date: date | None = None
    price: Money | None = None  # defaults to the plan price; overriding needs a manager
    notes: LongText | None = None
    payment: InlinePayment | None = None


class MembershipUpdate(InModel):
    status: MembershipStatus | None = None
    end_date: date | None = None
    notes: LongText | None = None


class MembershipOut(OutModel):
    id: int
    member_id: int
    branch_id: int
    plan_id: int
    plan: PlanOut
    start_date: date
    end_date: date
    price: Decimal
    status: MembershipStatus
    notes: str | None

    @computed_field
    @property
    def days_left(self) -> int:
        return (self.end_date - academy_today()).days

    @computed_field
    @property
    def is_expired(self) -> bool:
        return self.end_date < academy_today()


class ExpiringMembershipOut(MembershipOut):
    member: MemberBrief


# ---------------------------------------------------------------- payments
class PaymentIn(InModel):
    branch_id: int
    member_id: int | None = None
    membership_id: int | None = None
    amount: Annotated[Decimal, Field(gt=0, max_digits=10, decimal_places=3)]
    method: PaymentMethod
    category: PaymentCategory
    reference: Annotated[str, StringConstraints(max_length=100)] | None = None
    notes: ShortText | None = None


class PaymentVoid(InModel):
    reason: Annotated[str, StringConstraints(min_length=3, max_length=255)]


class PaymentOut(OutModel):
    id: int
    branch_id: int
    member_id: int | None
    membership_id: int | None
    amount: Decimal
    method: PaymentMethod
    category: PaymentCategory
    reference: str | None
    notes: str | None
    paid_at: datetime
    received_by: int | None
    is_void: bool
    void_reason: str | None

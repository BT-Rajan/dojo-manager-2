"""Member and parent portal: sign-in and the family view."""

from datetime import date, datetime, time
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from app.schemas.common import InModel, OutModel

Lang = Literal["en", "ar"]


class SendCodeIn(InModel):
    mobile: Annotated[str, StringConstraints(min_length=1, max_length=20)]
    lang: Lang = "en"


class SendCodeOut(OutModel):
    mobile: str
    # Development only: the WhatsApp message that would have been sent.
    test_message: str | None = None


class VerifyIn(InModel):
    mobile: Annotated[str, StringConstraints(min_length=1, max_length=20)]
    code: Annotated[str, StringConstraints(pattern=r"^\d{4}$")]
    lang: Lang = "en"


class PortalMe(OutModel):
    kind: Literal["guardian", "member"]
    name: str
    mobile: str


class BeltBrief(OutModel):
    id: int
    name: str
    color: str


class RankOut(OutModel):
    belt: BeltBrief
    stripes: int
    next_belt: BeltBrief | None


class ClassBrief(OutModel):
    session_id: int
    session_date: date
    start_time: time
    end_time: time
    title: str


class MembershipBrief(OutModel):
    id: int
    plan_name: str
    start_date: date
    end_date: date
    status: str


class FamilyMemberOut(OutModel):
    id: int
    first_name: str
    last_name: str
    branch_id: int
    branch_name: str
    branch_code: str
    rank: RankOut | None
    next_class: ClassBrief | None
    membership: MembershipBrief | None
    # active, expiring, expired, frozen or none
    status: str
    expiring: bool


# ---------------------------------------------------------------- one member's page
class MemberHead(OutModel):
    id: int
    first_name: str
    last_name: str
    branch_name: str
    branch_code: str


class BookingBrief(OutModel):
    status: str  # booked or waitlisted


class ClassRow(OutModel):
    session_id: int
    session_date: date
    start_time: time
    end_time: time
    title: str
    regular: bool
    booking: BookingBrief | None
    can_book: bool


class AttendedRow(OutModel):
    session_date: date
    start_time: time
    title: str
    status: str


class MemberDetailOut(OutModel):
    member: MemberHead
    status: str
    membership: MembershipBrief | None
    classes: list[ClassRow]
    attendance: list[AttendedRow]
    renewal: "RenewalOption | None" = None
    receipts: list["Receipt"] = []
    freeze: "FreezeInfo | None" = None
    progress: list["ProgressOut"] = []
    consent: "ConsentBrief | None" = None
    rules_signed: bool = False
    signer: str = ""


class BookIn(InModel):
    session_id: int
    lang: Lang = "en"


class BookOut(OutModel):
    status: str
    late_cancellation: bool = False


# ---------------------------------------------------------------- money
class RenewalOption(OutModel):
    plan_name: str
    price: Decimal


class ReceiptLine(OutModel):
    description: str
    amount: Decimal


class Receipt(OutModel):
    reference: str
    paid_at: datetime
    amount: Decimal
    method: str
    lines: list[ReceiptLine]


class FreezeInfo(OutModel):
    can_request: bool
    pending: bool
    used: bool


class RenewIn(InModel):
    method: Literal["knet", "card"] = "knet"
    lang: Lang = "en"


class RenewOut(OutModel):
    reference: str
    pay_url: str


class RenewalOut(OutModel):
    reference: str
    member_id: int
    plan_name: str
    amount: Decimal
    method: str
    status: str
    end_date: date | None = None
    # Test gateway only: the signed Approve / Decline answers.
    test_outcomes: dict[str, str] | None = None


class CompleteIn(InModel):
    outcome: Annotated[str, StringConstraints(max_length=20)]
    sig: Annotated[str, StringConstraints(max_length=64)]
    lang: Lang = "en"


class FreezeIn(InModel):
    start_date: date
    weeks: Annotated[int, Field(ge=1, le=4)]
    reason: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    lang: Lang = "en"


# ---------------------------------------------------------------- progress, photos and rules
class ProgressBelt(OutModel):
    id: int
    name: str
    name_ar: str | None
    color: str
    bjj_stripe: str | None
    bjj_stripe_ar: str | None


class ProgressCheck(OutModel):
    code: str
    en: str
    ar: str
    have: int
    need: int
    ok: bool


class ProgressTest(OutModel):
    event_date: date
    title: str


class ProgressEvaluation(OutModel):
    eval_date: date
    instructor_name: str | None
    notes: str | None


class ProgressNoteBrief(OutModel):
    month: date
    worked_on: str
    next_steps: str


class ProgressOut(OutModel):
    belt: ProgressBelt
    stripes: int
    next: ProgressBelt | None
    done: int
    total: int
    seminars: int
    checks: list[ProgressCheck]
    tests: list[ProgressTest]
    evaluations: list[ProgressEvaluation]
    notes: list[ProgressNoteBrief]


class ConsentBrief(OutModel):
    internal_records: bool
    social_media: bool
    website_marketing: bool


class ConsentIn(InModel):
    internal: bool
    social: bool
    website: bool
    lang: Lang = "en"


class RulesIn(InModel):
    name: Annotated[str, StringConstraints(max_length=150)]
    agree: bool
    lang: Lang = "en"


# MemberDetailOut refers to models defined after it.
MemberDetailOut.model_rebuild()

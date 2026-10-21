"""Member and parent portal: sign-in and the family view."""

from datetime import date, time
from typing import Annotated, Literal

from pydantic import StringConstraints

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

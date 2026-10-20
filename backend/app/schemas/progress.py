from datetime import date, datetime
from typing import Annotated

from pydantic import Field, StringConstraints

from app.models.progress import (
    CaseStatus,
    Channel,
    ContactMethod,
    FollowUpOutcome,
    GradingOutcome,
    GradingStatus,
    IncidentType,
)
from app.schemas.common import InModel, LocalDateTime, LongText, Name, OutModel, Phone, ShortText

Title = Annotated[str, StringConstraints(min_length=1, max_length=150)]
Stripes = Annotated[int, Field(ge=0, le=4)]


# ---------------------------------------------------------------- gradings
class GradingEventIn(InModel):
    branch_id: int
    title: Title
    event_date: date
    examiner_instructor_id: int | None = None
    notes: LongText | None = None


class GradingEventUpdate(InModel):
    title: Title | None = None
    event_date: date | None = None
    examiner_instructor_id: int | None = None
    status: GradingStatus | None = None
    notes: LongText | None = None


class GradingEventOut(OutModel):
    id: int
    branch_id: int
    title: str
    event_date: date
    examiner_instructor_id: int | None
    status: GradingStatus
    notes: str | None


class GradingResultEntry(InModel):
    member_id: int
    outcome: GradingOutcome = GradingOutcome.PENDING
    to_rank_id: int | None = None
    to_stripes: Stripes | None = None
    notes: ShortText | None = None


class GradingResultsIn(InModel):
    entries: Annotated[list[GradingResultEntry], Field(min_length=1, max_length=200)]


class GradingResultOut(OutModel):
    id: int
    event_id: int
    member_id: int
    from_rank_id: int | None
    from_stripes: int
    to_rank_id: int | None
    to_stripes: int
    outcome: GradingOutcome
    notes: str | None


class EligibilityOut(OutModel):
    member_id: int
    member_name: str
    belt_rank_id: int | None
    stripes: int
    next_rank_id: int | None
    seminar_points: int
    seminars_required: int
    classes_since_promotion: int
    last_promoted_on: date | None
    seminar_requirement_met: bool


# ---------------------------------------------------------------- seminars
class SeminarIn(InModel):
    branch_id: int
    title: Title
    seminar_date: date
    instructor_id: int | None = None
    points: Annotated[int, Field(ge=0, le=10)] = 1
    notes: LongText | None = None


class SeminarOut(OutModel):
    id: int
    branch_id: int
    title: str
    seminar_date: date
    instructor_id: int | None
    points: int
    notes: str | None
    attendee_count: int = 0


class SeminarAttendeesIn(InModel):
    member_ids: Annotated[list[int], Field(min_length=1, max_length=300)]


# ---------------------------------------------------------------- renewal follow-ups
class FollowUpIn(InModel):
    member_id: int
    membership_id: int | None = None
    method: ContactMethod
    outcome: FollowUpOutcome
    next_action: ShortText | None = None
    notes: ShortText | None = None


class FollowUpOut(OutModel):
    id: int
    branch_id: int
    member_id: int
    membership_id: int | None
    method: ContactMethod
    outcome: FollowUpOutcome
    next_action: str | None
    notes: str | None
    contacted_at: datetime
    contacted_by: int | None


# ---------------------------------------------------------------- incidents
class IncidentIn(InModel):
    branch_id: int
    occurred_at: LocalDateTime
    type: IncidentType
    session_id: int | None = None
    member_id: int | None = None
    persons_involved: ShortText | None = None
    description: Annotated[str, StringConstraints(min_length=3, max_length=5000)]
    action_taken: LongText | None = None
    guardian_informed: ShortText | None = None
    witnesses: ShortText | None = None


class IncidentUpdate(InModel):
    action_taken: LongText | None = None
    guardian_informed: ShortText | None = None
    witnesses: ShortText | None = None
    reported_to_manager: bool | None = None
    status: CaseStatus | None = None


class IncidentOut(OutModel):
    id: int
    branch_id: int
    ref_no: str | None
    occurred_at: datetime
    type: IncidentType
    session_id: int | None
    member_id: int | None
    persons_involved: str | None
    description: str
    action_taken: str | None
    guardian_informed: str | None
    witnesses: str | None
    reported_to_manager_at: datetime | None
    reported_by: int | None
    status: CaseStatus
    closed_at: datetime | None


# ---------------------------------------------------------------- complaints
class ComplaintIn(InModel):
    branch_id: int
    received_on: date | None = None
    member_id: int | None = None
    contact_name: Name
    contact_phone: Phone | None = None
    channel: Channel
    description: Annotated[str, StringConstraints(min_length=3, max_length=5000)]


class ComplaintUpdate(InModel):
    handled_by: int | None = None
    escalated: bool | None = None
    outcome: LongText | None = None
    member_informed_on: date | None = None
    status: CaseStatus | None = None


class ComplaintOut(OutModel):
    id: int
    branch_id: int
    ref_no: str | None
    received_on: date
    member_id: int | None
    contact_name: str
    contact_phone: str | None
    channel: Channel
    description: str
    handled_by: int | None
    escalated: bool
    outcome: str | None
    member_informed_on: date | None
    status: CaseStatus
    closed_on: date | None

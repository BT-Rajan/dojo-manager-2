from datetime import date, datetime, time
from typing import Annotated

from pydantic import EmailStr, Field, StringConstraints, model_validator

from app.models.classes import (
    AttendanceStatus,
    BookingSource,
    LeadSource,
    LeadStatus,
    LeaveStatus,
    LeaveType,
    SessionStatus,
)
from app.schemas.common import InModel, LongText, Name, OutModel, Phone, ShortText
from app.schemas.dojo import MemberBrief

Title = Annotated[str, StringConstraints(max_length=100)]
Capacity = Annotated[int, Field(ge=1, le=500)]


def _check_times(start: time | None, end: time | None) -> None:
    if start is not None and end is not None and end <= start:
        raise ValueError("end_time must be after start_time")


# ---------------------------------------------------------------- schedules
class ScheduleIn(InModel):
    branch_id: int
    program_id: int
    instructor_id: int | None = None
    title: Title | None = None
    weekday: Annotated[int, Field(ge=1, le=7, description="ISO weekday: 1=Mon … 7=Sun")]
    start_time: time
    end_time: time
    capacity: Capacity = 20
    room: Annotated[str, StringConstraints(max_length=50)] | None = None
    is_active: bool = True

    @model_validator(mode="after")
    def _times(self):
        _check_times(self.start_time, self.end_time)
        return self


class ScheduleUpdate(InModel):
    program_id: int | None = None
    instructor_id: int | None = None
    title: Title | None = None
    weekday: Annotated[int, Field(ge=1, le=7)] | None = None
    start_time: time | None = None
    end_time: time | None = None
    capacity: Capacity | None = None
    room: Annotated[str, StringConstraints(max_length=50)] | None = None
    is_active: bool | None = None


class ScheduleOut(OutModel):
    id: int
    branch_id: int
    program_id: int
    instructor_id: int | None
    title: str | None
    weekday: int
    start_time: time
    end_time: time
    capacity: int
    room: str | None
    is_active: bool


# ---------------------------------------------------------------- sessions
class GenerateSessionsIn(InModel):
    branch_id: int
    date_from: date
    date_to: date

    @model_validator(mode="after")
    def _range(self):
        if self.date_to < self.date_from:
            raise ValueError("date_to before date_from")
        if (self.date_to - self.date_from).days > 62:
            raise ValueError("Generate at most 63 days at a time")
        return self


class SessionIn(InModel):
    branch_id: int
    program_id: int
    instructor_id: int | None = None
    title: Title | None = None
    session_date: date
    start_time: time
    end_time: time
    capacity: Capacity = 20

    @model_validator(mode="after")
    def _times(self):
        _check_times(self.start_time, self.end_time)
        return self


class SessionUpdate(InModel):
    instructor_id: int | None = None
    title: Title | None = None
    session_date: date | None = None
    start_time: time | None = None
    end_time: time | None = None
    capacity: Capacity | None = None
    status: SessionStatus | None = None
    change_reason: ShortText | None = None
    members_notified: bool | None = None


class SessionOut(OutModel):
    id: int
    branch_id: int
    schedule_id: int | None
    program_id: int
    instructor_id: int | None
    original_instructor_id: int | None
    title: str | None
    session_date: date
    start_time: time
    end_time: time
    capacity: int
    status: SessionStatus
    change_reason: str | None
    members_notified_at: datetime | None


class SessionWithCounts(SessionOut):
    booked: int = 0
    attended: int = 0


class GenerateResult(OutModel):
    created: int


# ---------------------------------------------------------------- attendance
class AttendanceEntry(InModel):
    member_id: int
    status: AttendanceStatus


class AttendanceBulkIn(InModel):
    entries: Annotated[list[AttendanceEntry], Field(min_length=1, max_length=200)]


class AttendanceOut(OutModel):
    # None for a regular member who has no booking or check-in for this class yet.
    id: int | None
    session_id: int
    member_id: int
    status: AttendanceStatus | None
    checked_in_at: datetime | None
    member: MemberBrief
    has_active_membership: bool = False
    is_regular: bool = False
    source: BookingSource = BookingSource.DESK
    late_cancellation: bool = False


class MemberAttendanceOut(OutModel):
    session_id: int
    session_date: date
    start_time: time
    program_id: int
    status: AttendanceStatus


# ---------------------------------------------------------------- leave
class LeaveIn(InModel):
    instructor_id: int
    start_date: date
    end_date: date
    type: LeaveType
    reason: ShortText | None = None
    cover_instructor_id: int | None = None

    @model_validator(mode="after")
    def _dates(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date before start_date")
        if self.cover_instructor_id == self.instructor_id:
            raise ValueError("An instructor cannot cover their own leave")
        return self


class LeaveOut(OutModel):
    id: int
    instructor_id: int
    branch_id: int
    start_date: date
    end_date: date
    type: LeaveType
    reason: str | None
    cover_instructor_id: int | None
    status: LeaveStatus
    requested_by: int | None
    decided_by: int | None
    decided_at: datetime | None
    decision_note: str | None
    created_at: datetime


class LeaveRequestIn(InModel):
    """A coach asking for leave; the cover is a suggestion the manager can change."""

    start_date: date
    end_date: date
    type: LeaveType
    reason: ShortText | None = None
    cover_instructor_id: int | None = None

    @model_validator(mode="after")
    def _dates(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date before start_date")
        if (self.end_date - self.start_date).days > 90:
            raise ValueError("Leave can be requested for at most 91 days at a time")
        return self


class LeaveDecisionIn(InModel):
    approve: bool
    cover_instructor_id: int | None = None
    note: ShortText | None = None


class LeaveCreated(LeaveOut):
    sessions_reassigned: int = 0


# ---------------------------------------------------------------- leads
class LeadIn(InModel):
    branch_id: int
    full_name: Name
    phone: Phone
    email: EmailStr | None = None
    age: Annotated[int, Field(ge=2, le=99)] | None = None
    source: LeadSource
    program_id: int | None = None
    owner_user_id: int | None = None
    next_action: ShortText | None = None
    next_action_date: date | None = None
    notes: LongText | None = None


class LeadUpdate(InModel):
    full_name: Name | None = None
    phone: Phone | None = None
    email: EmailStr | None = None
    age: Annotated[int, Field(ge=2, le=99)] | None = None
    program_id: int | None = None
    status: LeadStatus | None = None
    owner_user_id: int | None = None
    next_action: ShortText | None = None
    next_action_date: date | None = None
    lost_reason: ShortText | None = None
    notes: LongText | None = None


class BookTrialIn(InModel):
    session_id: int


class ConvertLeadIn(InModel):
    first_name: Annotated[str, StringConstraints(min_length=1, max_length=75)]
    last_name: Annotated[str, StringConstraints(min_length=1, max_length=75)]
    date_of_birth: date | None = None


class LeadOut(OutModel):
    id: int
    branch_id: int
    full_name: str
    phone: str
    email: str | None
    age: int | None
    source: LeadSource
    program_id: int | None
    status: LeadStatus
    owner_user_id: int | None
    next_action: str | None
    next_action_date: date | None
    trial_session_id: int | None
    converted_member_id: int | None
    lost_reason: str | None
    notes: str | None
    created_at: datetime

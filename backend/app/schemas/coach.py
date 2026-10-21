"""Coach portal: a coach's own view of their classes, and the admin side of portal logins."""

from datetime import date, datetime
from enum import StrEnum

from pydantic import EmailStr

from app.schemas.classes import LeaveOut, SessionWithCounts
from app.schemas.common import InModel, OutModel
from app.schemas.org import BranchOut, Password, Username


class CoachRole(StrEnum):
    """The coach's part in a class."""

    TEACHING = "teaching"  # their own class
    COVERING = "covering"  # someone else's class, taken while that coach is on leave
    COVERED = "covered"  # their class, taught by a cover while they are on leave


class CoachSession(SessionWithCounts):
    coach_role: CoachRole | None = None


class CoachProfile(OutModel):
    id: int
    branch_id: int
    branch: BranchOut
    user_id: int | None
    full_name: str
    phone: str | None
    email: str | None
    specialties: str | None
    belt_rank_id: int | None
    is_active: bool
    today: date
    classes_today: int
    classes_this_week: int
    next_session: CoachSession | None
    leave_today: LeaveOut | None


class CoachDay(OutModel):
    date: date
    sessions: list[CoachSession]
    on_leave: list[LeaveOut]


# ---------------------------------------------------------------- portal logins (admin)
class PortalAccessOut(OutModel):
    instructor_id: int
    full_name: str
    branch_id: int
    is_active: bool
    user_id: int | None
    username: str | None
    user_active: bool | None
    last_login_at: datetime | None


class PortalAccountIn(InModel):
    username: Username
    password: Password
    email: EmailStr | None = None


class PortalAccountUpdate(InModel):
    is_active: bool


class PortalPasswordIn(InModel):
    password: Password

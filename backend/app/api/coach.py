"""Coach portal: the signed-in coach's classes today, their branch's day and their week.

A coach is an instructor-role user linked to an ``Instructor`` record. Staff can open any
coach's portal at their branches by passing ``instructor_id``."""

from datetime import date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select

from app.api.classes import ensure_no_overlap, session_dicts, sessions_with_counts
from app.core.clock import academy_tz
from app.core.clock import today as academy_today
from app.core.deps import ANY_ROLE, DB, CurrentUser, get_scoped_or_404, require_roles, utcnow
from app.models import (
    Branch,
    ClassSchedule,
    ClassSession,
    Instructor,
    InstructorLeave,
    LeaveStatus,
    Role,
    SessionStatus,
)
from app.schemas.classes import LeaveOut, LeaveRequestIn, ScheduleOut
from app.schemas.coach import CoachDay, CoachProfile, CoachRole, CoachSession

router = APIRouter(prefix="/coach", tags=["coach"], dependencies=[require_roles(*ANY_ROLE)])

MAX_RANGE_DAYS = 92


async def get_coach(user: CurrentUser, db: DB, instructor_id: int | None = None) -> Instructor:
    if user.role == Role.INSTRUCTOR:
        inst = await db.scalar(select(Instructor).where(Instructor.user_id == user.id))
        if inst is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "No coach profile is linked to this account"
            )
        if instructor_id is not None and instructor_id != inst.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Coaches can only open their own portal")
        if not inst.is_active:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "This coach profile is inactive")
        return inst
    if instructor_id is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "instructor_id is required")
    return await get_scoped_or_404(db, Instructor, instructor_id, user)


Coach = Annotated[Instructor, Depends(get_coach)]


async def get_own_coach(user: CurrentUser, coach: Coach) -> Instructor:
    """Actions a coach takes for themselves (requests); staff use the staff screens."""
    if user.role != Role.INSTRUCTOR:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the coach can do this from the portal")
    return coach


OwnCoach = Annotated[Instructor, Depends(get_own_coach)]


def _with_role(rows: list[dict], coach: Instructor) -> list[dict]:
    for r in rows:
        if r["instructor_id"] == coach.id:
            covering = r["original_instructor_id"] is not None
            r["coach_role"] = CoachRole.COVERING if covering else CoachRole.TEACHING
        elif r["original_instructor_id"] == coach.id:
            r["coach_role"] = CoachRole.COVERED
        else:
            r["coach_role"] = None
    return rows


async def _my_sessions(db: DB, coach: Instructor, first: date, last: date) -> list[dict]:
    """Sessions the coach teaches, covers, or that are covered for them."""
    stmt = sessions_with_counts().where(
        or_(
            ClassSession.instructor_id == coach.id,
            ClassSession.original_instructor_id == coach.id,
        ),
        ClassSession.branch_id == coach.branch_id,
        ClassSession.session_date.between(first, last),
    )
    return _with_role(await session_dicts(db, stmt), coach)


def _teaches(s: dict) -> bool:
    return s["coach_role"] != CoachRole.COVERED and s["status"] != SessionStatus.CANCELLED


def week_bounds(day: date) -> tuple[date, date]:
    """Academy weeks run Saturday to Friday."""
    start = day - timedelta(days=(day.isoweekday() - 6) % 7)
    return start, start + timedelta(days=6)


async def _leaves_on(db: DB, branch_id: int, day: date, instructor_id: int | None = None):
    stmt = select(InstructorLeave).where(
        InstructorLeave.branch_id == branch_id,
        InstructorLeave.status == LeaveStatus.APPROVED,
        InstructorLeave.start_date <= day,
        InstructorLeave.end_date >= day,
    )
    if instructor_id is not None:
        stmt = stmt.where(InstructorLeave.instructor_id == instructor_id)
    return list(await db.scalars(stmt.order_by(InstructorLeave.start_date)))


@router.get("/me", response_model=CoachProfile)
async def coach_profile(coach: Coach, db: DB) -> dict:
    """The coach's profile with a summary of today and this week."""
    today = academy_today()
    week_start, week_end = week_bounds(today)
    # Look a week ahead too, so "next class" is found on a Friday evening.
    rows = await _my_sessions(db, coach, week_start, max(week_end, today + timedelta(days=7)))
    teaching = [s for s in rows if _teaches(s)]
    now = datetime.now(academy_tz()).time()
    upcoming = [
        s
        for s in teaching
        if s["session_date"] > today or (s["session_date"] == today and s["end_time"] > now)
    ]
    leave = await _leaves_on(db, coach.branch_id, today, coach.id)
    fields = ("id", "branch_id", "user_id", "full_name", "phone", "email", "specialties")
    return {
        **{c: getattr(coach, c) for c in fields},
        "belt_rank_id": coach.belt_rank_id,
        "is_active": coach.is_active,
        "branch": await db.get(Branch, coach.branch_id),
        "today": today,
        "classes_today": sum(1 for s in teaching if s["session_date"] == today),
        "classes_this_week": sum(1 for s in teaching if s["session_date"] <= week_end),
        "next_session": upcoming[0] if upcoming else None,
        "leave_today": LeaveOut.model_validate(leave[0]) if leave else None,
    }


@router.get("/today", response_model=list[CoachSession])
async def coach_today(coach: Coach, db: DB) -> list[dict]:
    """Today's classes for the coach, including classes handed to a cover."""
    today = academy_today()
    return await _my_sessions(db, coach, today, today)


@router.get("/day", response_model=CoachDay)
async def coach_day(coach: Coach, db: DB, day: date | None = None) -> dict:
    """Every class at the coach's branch on one day, with the coach's own marked, and who is
    on leave that day."""
    day = day or academy_today()
    stmt = sessions_with_counts().where(
        ClassSession.branch_id == coach.branch_id, ClassSession.session_date == day
    )
    return {
        "date": day,
        "sessions": _with_role(await session_dicts(db, stmt), coach),
        "on_leave": await _leaves_on(db, coach.branch_id, day),
    }


@router.get("/sessions", response_model=list[CoachSession])
async def coach_sessions(coach: Coach, db: DB, date_from: date, date_to: date) -> list[dict]:
    """The coach's dated classes in a range (at most 93 days)."""
    if date_to < date_from:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "date_to is before date_from")
    if (date_to - date_from).days > MAX_RANGE_DAYS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Range too large (max 93 days)")
    return await _my_sessions(db, coach, date_from, date_to)


@router.get("/timetable", response_model=list[ScheduleOut])
async def coach_timetable(coach: Coach, db: DB) -> list[ClassSchedule]:
    """The coach's weekly recurring classes."""
    stmt = select(ClassSchedule).where(
        ClassSchedule.instructor_id == coach.id,
        ClassSchedule.branch_id == coach.branch_id,
        ClassSchedule.is_active.is_(True),
    )
    return list(await db.scalars(stmt.order_by(ClassSchedule.weekday, ClassSchedule.start_time)))


# ---------------------------------------------------------------- leave requests
MAX_BACKDATE_DAYS = 30


@router.get("/leaves", response_model=list[LeaveOut])
async def coach_leaves(coach: Coach, db: DB) -> list[InstructorLeave]:
    """All the coach's leave: requests, approved, rejected and withdrawn, newest first."""
    stmt = select(InstructorLeave).where(InstructorLeave.instructor_id == coach.id)
    order = (InstructorLeave.start_date.desc(), InstructorLeave.id.desc())
    return list(await db.scalars(stmt.order_by(*order)))


@router.post("/leaves", response_model=LeaveOut, status_code=status.HTTP_201_CREATED)
async def request_leave(
    body: LeaveRequestIn, coach: OwnCoach, user: CurrentUser, db: DB
) -> InstructorLeave:
    """Ask for leave. Nothing changes until a manager approves it."""
    if body.start_date < academy_today() - timedelta(days=MAX_BACKDATE_DAYS):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Leave can be backdated by at most {MAX_BACKDATE_DAYS} days",
        )
    if body.cover_instructor_id is not None:
        cover = await db.get(Instructor, body.cover_instructor_id)
        if (
            cover is None
            or cover.id == coach.id
            or cover.branch_id != coach.branch_id
            or not cover.is_active
        ):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown cover_instructor_id"
            )
    await ensure_no_overlap(db, coach.id, body.start_date, body.end_date)
    leave = InstructorLeave(
        **body.model_dump(),
        instructor_id=coach.id,
        branch_id=coach.branch_id,
        status=LeaveStatus.PENDING,
        requested_by=user.id,
    )
    db.add(leave)
    await db.commit()
    await db.refresh(leave)
    return leave


@router.post("/leaves/{leave_id}/withdraw", response_model=LeaveOut)
async def withdraw_leave(leave_id: int, coach: OwnCoach, user: CurrentUser, db: DB):
    """Withdraw a request that has not been decided yet."""
    leave = await db.get(InstructorLeave, leave_id)
    if leave is None or leave.instructor_id != coach.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "InstructorLeave not found")
    if leave.status != LeaveStatus.PENDING:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Only pending requests can be withdrawn; ask a manager"
        )
    leave.status = LeaveStatus.CANCELLED
    leave.decided_by = user.id
    leave.decided_at = utcnow()
    await db.commit()
    await db.refresh(leave)
    return leave

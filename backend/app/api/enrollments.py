"""Regular weekly classes: a member enrolled in a timetable class has a place every week
without booking."""

from datetime import date, time

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.clock import today as academy_today
from app.core.deps import ANY_ROLE, DB, STAFF, CurrentUser, get_scoped_or_404, require_roles
from app.models import ClassSchedule, Enrollment, Member
from app.schemas.common import InModel, OutModel
from app.services.audit import audit

router = APIRouter(tags=["enrollments"])


class EnrollmentIn(InModel):
    schedule_id: int
    start_date: date | None = None


class EnrollmentEnd(InModel):
    end_date: date | None = None


class EnrollmentOut(OutModel):
    id: int
    member_id: int
    schedule_id: int
    start_date: date
    end_date: date | None
    weekday: int
    start_time: time
    end_time: time
    program_id: int
    title: str | None
    is_active: bool


def _out(e: Enrollment, s: ClassSchedule, today: date) -> dict:
    return {
        "id": e.id,
        "member_id": e.member_id,
        "schedule_id": e.schedule_id,
        "start_date": e.start_date,
        "end_date": e.end_date,
        "weekday": s.weekday,
        "start_time": s.start_time,
        "end_time": s.end_time,
        "program_id": s.program_id,
        "title": s.title,
        "is_active": e.end_date is None or e.end_date >= today,
    }


@router.get(
    "/members/{member_id}/enrollments",
    response_model=list[EnrollmentOut],
    dependencies=[require_roles(*ANY_ROLE)],
)
async def list_enrollments(member_id: int, user: CurrentUser, db: DB) -> list[dict]:
    await get_scoped_or_404(db, Member, member_id, user)
    rows = await db.execute(
        select(Enrollment, ClassSchedule)
        .join(ClassSchedule, ClassSchedule.id == Enrollment.schedule_id)
        .where(Enrollment.member_id == member_id)
        .order_by(Enrollment.end_date.is_not(None), ClassSchedule.weekday, ClassSchedule.start_time)
    )
    today = academy_today()
    return [_out(e, s, today) for e, s in rows.all()]


@router.post(
    "/members/{member_id}/enrollments",
    response_model=EnrollmentOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_roles(*STAFF)],
)
async def enroll(member_id: int, body: EnrollmentIn, user: CurrentUser, db: DB) -> dict:
    """Give the member a regular place in a weekly class at their branch."""
    member = await get_scoped_or_404(db, Member, member_id, user)
    sched = await db.get(ClassSchedule, body.schedule_id, with_for_update=True)
    if sched is None or sched.branch_id != member.branch_id or not sched.is_active:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown schedule_id")
    open_one = await db.scalar(
        select(Enrollment.id).where(
            Enrollment.member_id == member.id,
            Enrollment.schedule_id == sched.id,
            Enrollment.end_date.is_(None),
        )
    )
    if open_one is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Already a regular in this class")
    e = Enrollment(
        member_id=member.id,
        schedule_id=sched.id,
        start_date=body.start_date or academy_today(),
        created_by=user.id,
    )
    db.add(e)
    await db.flush()
    audit(db, user, "enrolled", "member", member.id, schedule_id=sched.id)
    await db.commit()
    return _out(e, sched, academy_today())


@router.post(
    "/enrollments/{enrollment_id}/end",
    response_model=EnrollmentOut,
    dependencies=[require_roles(*STAFF)],
)
async def end_enrollment(enrollment_id: int, body: EnrollmentEnd, user: CurrentUser, db: DB):
    e = await db.get(Enrollment, enrollment_id)
    if e is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Enrollment not found")
    await get_scoped_or_404(db, Member, e.member_id, user)
    end = body.end_date or academy_today()
    if end < e.start_date:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "end_date is before the start")
    e.end_date = end
    audit(db, user, "enrollment_ended", "member", e.member_id, schedule_id=e.schedule_id)
    await db.commit()
    sched = await db.get(ClassSchedule, e.schedule_id)
    return _out(e, sched, academy_today())

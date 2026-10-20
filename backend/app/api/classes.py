from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import case, delete, func, select, update
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.orm import selectinload

from app.core.deps import (
    ANY_ROLE,
    DB,
    STAFF,
    CurrentUser,
    apply_updates,
    can_access_branch,
    ensure_branch,
    ensure_exists,
    get_scoped_or_404,
    require_roles,
    scope_to_branches,
    utcnow,
)
from app.models import (
    Attendance,
    AttendanceStatus,
    ClassSchedule,
    ClassSession,
    Instructor,
    InstructorLeave,
    Member,
    Membership,
    MembershipStatus,
    Program,
    SessionStatus,
)
from app.schemas.classes import (
    AttendanceBulkIn,
    AttendanceOut,
    GenerateResult,
    GenerateSessionsIn,
    LeaveCreated,
    LeaveIn,
    LeaveOut,
    MemberAttendanceOut,
    ScheduleIn,
    ScheduleOut,
    ScheduleUpdate,
    SessionIn,
    SessionOut,
    SessionUpdate,
    SessionWithCounts,
)

router = APIRouter(tags=["classes"])
any_role = [require_roles(*ANY_ROLE)]
staff = [require_roles(*STAFF)]

ATTENDING = (AttendanceStatus.BOOKED, AttendanceStatus.PRESENT, AttendanceStatus.LATE)
PRESENT = (AttendanceStatus.PRESENT, AttendanceStatus.LATE)


async def _check_instructor(db: DB, user, instructor_id: int | None) -> None:
    if instructor_id is None:
        return
    inst = await db.get(Instructor, instructor_id)
    if inst is None or not can_access_branch(user, inst.branch_id):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown instructor_id")


# ---------------------------------------------------------------- weekly schedule
@router.get("/schedules", response_model=list[ScheduleOut], dependencies=any_role)
async def list_schedules(
    user: CurrentUser, db: DB, branch_id: int | None = None, active: bool | None = True
) -> list[ClassSchedule]:
    stmt = scope_to_branches(select(ClassSchedule), ClassSchedule.branch_id, user, branch_id)
    if active is not None:
        stmt = stmt.where(ClassSchedule.is_active == active)
    order = (ClassSchedule.weekday, ClassSchedule.start_time)
    return list(await db.scalars(stmt.order_by(*order)))


@router.post("/schedules", response_model=ScheduleOut, status_code=201, dependencies=staff)
async def create_schedule(body: ScheduleIn, user: CurrentUser, db: DB) -> ClassSchedule:
    ensure_branch(user, body.branch_id)
    await ensure_exists(db, Program, body.program_id, "program_id")
    await _check_instructor(db, user, body.instructor_id)
    sched = ClassSchedule(**body.model_dump())
    db.add(sched)
    await db.commit()
    return sched


@router.patch("/schedules/{schedule_id}", response_model=ScheduleOut, dependencies=staff)
async def update_schedule(
    schedule_id: int, body: ScheduleUpdate, user: CurrentUser, db: DB
) -> ClassSchedule:
    sched = await get_scoped_or_404(db, ClassSchedule, schedule_id, user)
    data = body.model_dump(exclude_unset=True)
    await ensure_exists(db, Program, data.get("program_id"), "program_id")
    await _check_instructor(db, user, data.get("instructor_id"))
    apply_updates(sched, data)
    if sched.end_time <= sched.start_time:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "end_time must follow start")
    await db.commit()
    return sched


# ---------------------------------------------------------------- dated sessions
@router.post("/sessions/generate", response_model=GenerateResult, dependencies=staff)
async def generate_sessions(body: GenerateSessionsIn, user: CurrentUser, db: DB) -> dict:
    """Create dated sessions from the weekly schedule. Idempotent; instructors on leave are
    replaced by their cover instructor."""
    ensure_branch(user, body.branch_id)
    schedules = list(
        await db.scalars(
            select(ClassSchedule).where(
                ClassSchedule.branch_id == body.branch_id, ClassSchedule.is_active.is_(True)
            )
        )
    )
    if not schedules:
        return {"created": 0}
    existing = set(
        (
            await db.execute(
                select(ClassSession.schedule_id, ClassSession.session_date).where(
                    ClassSession.schedule_id.in_([s.id for s in schedules]),
                    ClassSession.session_date.between(body.date_from, body.date_to),
                )
            )
        ).all()
    )
    leaves = list(
        await db.scalars(
            select(InstructorLeave).where(
                InstructorLeave.branch_id == body.branch_id,
                InstructorLeave.start_date <= body.date_to,
                InstructorLeave.end_date >= body.date_from,
            )
        )
    )

    def instructors_for(instructor_id: int | None, day: date) -> tuple[int | None, int | None]:
        """(teaching instructor, instructor on leave being covered)"""
        for lv in leaves:
            if lv.instructor_id == instructor_id and lv.start_date <= day <= lv.end_date:
                return lv.cover_instructor_id, instructor_id
        return instructor_id, None

    by_weekday: dict[int, list[ClassSchedule]] = {}
    for s in schedules:
        by_weekday.setdefault(s.weekday, []).append(s)

    rows = []
    day = body.date_from
    while day <= body.date_to:
        for s in by_weekday.get(day.isoweekday(), ()):
            if (s.id, day) not in existing:
                teacher, on_leave = instructors_for(s.instructor_id, day)
                rows.append(
                    {
                        "branch_id": s.branch_id,
                        "schedule_id": s.id,
                        "program_id": s.program_id,
                        "instructor_id": teacher,
                        "original_instructor_id": on_leave,
                        "title": s.title,
                        "session_date": day,
                        "start_time": s.start_time,
                        "end_time": s.end_time,
                        "capacity": s.capacity,
                    }
                )
        day += timedelta(days=1)
    if rows:
        await db.execute(mysql_insert(ClassSession), rows)
        await db.commit()
    return {"created": len(rows)}


@router.get("/sessions", response_model=list[SessionWithCounts], dependencies=any_role)
async def list_sessions(
    user: CurrentUser,
    db: DB,
    date_from: date,
    date_to: date,
    branch_id: int | None = None,
    instructor_id: int | None = None,
    program_id: int | None = None,
) -> list[dict]:
    if (date_to - date_from).days > 92:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Range too large (max 93 days)")
    counts = (
        select(
            Attendance.session_id,
            func.sum(case((Attendance.status.in_(ATTENDING), 1), else_=0)).label("booked"),
            func.sum(case((Attendance.status.in_(PRESENT), 1), else_=0)).label("attended"),
        )
        .group_by(Attendance.session_id)
        .subquery()
    )
    stmt = (
        select(
            ClassSession,
            func.coalesce(counts.c.booked, 0),
            func.coalesce(counts.c.attended, 0),
        )
        .outerjoin(counts, counts.c.session_id == ClassSession.id)
        .where(ClassSession.session_date.between(date_from, date_to))
        .order_by(ClassSession.session_date, ClassSession.start_time)
    )
    stmt = scope_to_branches(stmt, ClassSession.branch_id, user, branch_id)
    if instructor_id is not None:
        stmt = stmt.where(ClassSession.instructor_id == instructor_id)
    if program_id is not None:
        stmt = stmt.where(ClassSession.program_id == program_id)
    out = []
    for sess, booked, attended in (await db.execute(stmt)).all():
        row = SessionOut.model_validate(sess).model_dump()
        out.append(row | {"booked": int(booked), "attended": int(attended)})
    return out


@router.post("/sessions", response_model=SessionOut, status_code=201, dependencies=staff)
async def create_session(body: SessionIn, user: CurrentUser, db: DB) -> ClassSession:
    ensure_branch(user, body.branch_id)
    await ensure_exists(db, Program, body.program_id, "program_id")
    await _check_instructor(db, user, body.instructor_id)
    sess = ClassSession(**body.model_dump())
    db.add(sess)
    await db.commit()
    return sess


@router.patch("/sessions/{session_id}", response_model=SessionOut, dependencies=staff)
async def update_session(
    session_id: int, body: SessionUpdate, user: CurrentUser, db: DB
) -> ClassSession:
    """Edit, cancel or reschedule a class. Cancelling or moving a class needs a reason."""
    sess = await get_scoped_or_404(db, ClassSession, session_id, user)
    data = body.model_dump(exclude_unset=True)
    notified = data.pop("members_notified", None)
    await _check_instructor(db, user, data.get("instructor_id"))
    moved = any(k in data for k in ("session_date", "start_time", "end_time"))
    cancelled = data.get("status") == SessionStatus.CANCELLED
    if (moved or cancelled) and not (data.get("change_reason") or sess.change_reason):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "change_reason is required")
    apply_updates(sess, data)
    if sess.end_time <= sess.start_time:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "end_time must follow start")
    if notified:
        sess.members_notified_at = utcnow()
    await db.commit()
    return sess


# ---------------------------------------------------------------- attendance
async def _active_member_ids(db: DB, member_ids: list[int], on: date) -> set[int]:
    if not member_ids:
        return set()
    rows = await db.scalars(
        select(Membership.member_id).where(
            Membership.member_id.in_(member_ids),
            Membership.status == MembershipStatus.ACTIVE,
            Membership.start_date <= on,
            Membership.end_date >= on,
        )
    )
    return set(rows)


async def _attendance_rows(db: DB, sess: ClassSession) -> list[dict]:
    records = list(
        await db.scalars(
            select(Attendance)
            .where(Attendance.session_id == sess.id)
            .options(selectinload(Attendance.member))
            .order_by(Attendance.id)
        )
    )
    active = await _active_member_ids(db, [a.member_id for a in records], sess.session_date)
    return [
        AttendanceOut.model_validate(a).model_dump()
        | {"has_active_membership": a.member_id in active}
        for a in records
    ]


@router.get(
    "/sessions/{session_id}/attendance", response_model=list[AttendanceOut], dependencies=any_role
)
async def get_attendance(session_id: int, user: CurrentUser, db: DB) -> list[dict]:
    sess = await get_scoped_or_404(db, ClassSession, session_id, user)
    return await _attendance_rows(db, sess)


@router.post(
    "/sessions/{session_id}/attendance", response_model=list[AttendanceOut], dependencies=any_role
)
async def record_attendance(
    session_id: int, body: AttendanceBulkIn, user: CurrentUser, db: DB
) -> list[dict]:
    """Book members into a class or mark attendance (bulk upsert)."""
    sess = await get_scoped_or_404(db, ClassSession, session_id, user)
    # Lock the class row so concurrent bookings cannot overfill it.
    await db.refresh(sess, with_for_update=True)
    capacity = sess.capacity
    if sess.status == SessionStatus.CANCELLED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Class is cancelled")
    entries = {e.member_id: e.status for e in body.entries}  # last entry per member wins
    members = list(await db.scalars(select(Member).where(Member.id.in_(entries))))
    if len(members) != len(entries) or not all(
        can_access_branch(user, m.branch_id) for m in members
    ):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown member_id")

    now = utcnow()
    stmt = mysql_insert(Attendance).values(
        [
            {
                "session_id": sess.id,
                "member_id": mid,
                "status": st,
                "checked_in_at": now if st in PRESENT else None,
                "recorded_by": user.id,
            }
            for mid, st in entries.items()
        ]
    )
    stmt = stmt.on_duplicate_key_update(
        status=stmt.inserted.status,
        checked_in_at=func.coalesce(Attendance.checked_in_at, stmt.inserted.checked_in_at),
        recorded_by=stmt.inserted.recorded_by,
    )
    await db.execute(stmt)
    taken = await db.scalar(
        select(func.count()).where(
            Attendance.session_id == sess.id, Attendance.status.in_(ATTENDING)
        )
    )
    if taken > capacity:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"Class is full ({capacity})")
    await db.commit()
    return await _attendance_rows(db, sess)


@router.delete(
    "/sessions/{session_id}/attendance/{member_id}", status_code=204, dependencies=any_role
)
async def remove_attendance(session_id: int, member_id: int, user: CurrentUser, db: DB) -> None:
    await get_scoped_or_404(db, ClassSession, session_id, user)
    await db.execute(
        delete(Attendance).where(
            Attendance.session_id == session_id, Attendance.member_id == member_id
        )
    )
    await db.commit()


@router.get(
    "/members/{member_id}/attendance",
    response_model=list[MemberAttendanceOut],
    dependencies=any_role,
)
async def member_attendance(
    member_id: int, user: CurrentUser, db: DB, limit: int = 50
) -> list[dict]:
    await get_scoped_or_404(db, Member, member_id, user)
    rows = await db.execute(
        select(
            ClassSession.id,
            ClassSession.session_date,
            ClassSession.start_time,
            ClassSession.program_id,
            Attendance.status,
        )
        .join(Attendance, Attendance.session_id == ClassSession.id)
        .where(Attendance.member_id == member_id)
        .order_by(ClassSession.session_date.desc(), ClassSession.start_time.desc())
        .limit(min(max(limit, 1), 500))
    )
    keys = ("session_id", "session_date", "start_time", "program_id", "status")
    return [dict(zip(keys, r, strict=True)) for r in rows.all()]


# ---------------------------------------------------------------- instructor leave
@router.get("/leaves", response_model=list[LeaveOut], dependencies=any_role)
async def list_leaves(
    user: CurrentUser,
    db: DB,
    branch_id: int | None = None,
    instructor_id: int | None = None,
    active_on: date | None = None,
) -> list[InstructorLeave]:
    stmt = scope_to_branches(select(InstructorLeave), InstructorLeave.branch_id, user, branch_id)
    if instructor_id is not None:
        stmt = stmt.where(InstructorLeave.instructor_id == instructor_id)
    if active_on is not None:
        stmt = stmt.where(
            InstructorLeave.start_date <= active_on, InstructorLeave.end_date >= active_on
        )
    return list(await db.scalars(stmt.order_by(InstructorLeave.start_date.desc())))


@router.post("/leaves", response_model=LeaveCreated, status_code=201, dependencies=staff)
async def create_leave(body: LeaveIn, user: CurrentUser, db: DB) -> dict:
    """Record leave and hand the instructor's already-generated classes in that period to the
    cover instructor (unassigned when there is no cover)."""
    inst = await get_scoped_or_404(db, Instructor, body.instructor_id, user)
    await _check_instructor(db, user, body.cover_instructor_id)
    leave = InstructorLeave(**body.model_dump(), branch_id=inst.branch_id)
    db.add(leave)
    result = await db.execute(
        update(ClassSession)
        .where(
            ClassSession.instructor_id == leave.instructor_id,
            ClassSession.original_instructor_id.is_(None),
            ClassSession.status == SessionStatus.SCHEDULED,
            ClassSession.session_date.between(leave.start_date, leave.end_date),
        )
        .values(
            instructor_id=leave.cover_instructor_id,
            original_instructor_id=leave.instructor_id,
        )
    )
    await db.commit()
    return LeaveOut.model_validate(leave).model_dump() | {"sessions_reassigned": result.rowcount}


@router.delete("/leaves/{leave_id}", status_code=204, dependencies=staff)
async def delete_leave(leave_id: int, user: CurrentUser, db: DB) -> None:
    """Cancel leave: classes still being covered go back to the instructor."""
    leave = await get_scoped_or_404(db, InstructorLeave, leave_id, user)
    await db.execute(
        update(ClassSession)
        .where(
            ClassSession.original_instructor_id == leave.instructor_id,
            ClassSession.status == SessionStatus.SCHEDULED,
            ClassSession.session_date.between(leave.start_date, leave.end_date),
        )
        .values(instructor_id=leave.instructor_id, original_instructor_id=None)
    )
    await db.delete(leave)
    await db.commit()

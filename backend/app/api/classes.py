from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import Select, case, func, select, update
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
    LeaveStatus,
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
    LeaveDecisionIn,
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
from app.services.bookings import (
    places_taken,
    promote_waitlist,
    regular_member_ids,
    regulars_by_session,
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


def sessions_with_counts() -> Select:
    """Sessions with their booked and present counts, in date and time order. Callers add
    their own filters (and branch scoping)."""
    counts = (
        select(
            Attendance.session_id,
            func.sum(case((Attendance.status.in_(ATTENDING), 1), else_=0)).label("booked"),
            func.sum(case((Attendance.status.in_(PRESENT), 1), else_=0)).label("attended"),
        )
        .group_by(Attendance.session_id)
        .subquery()
    )
    return (
        select(
            ClassSession,
            func.coalesce(counts.c.booked, 0),
            func.coalesce(counts.c.attended, 0),
        )
        .outerjoin(counts, counts.c.session_id == ClassSession.id)
        .order_by(ClassSession.session_date, ClassSession.start_time)
    )


async def session_dicts(db: DB, stmt: Select) -> list[dict]:
    """Rows of ``sessions_with_counts``. ``booked`` is the places taken: regular members plus
    everyone else booked or checked in."""
    rows = (await db.execute(stmt)).all()
    sessions = [sess for sess, _, _ in rows]
    regulars = await regulars_by_session(db, sessions)
    holding: dict[int, set[int]] = {}
    if any(regulars.values()):
        pairs = await db.execute(
            select(Attendance.session_id, Attendance.member_id).where(
                Attendance.session_id.in_([s.id for s in sessions]),
                Attendance.status.in_(ATTENDING),
            )
        )
        for sid, mid in pairs.all():
            holding.setdefault(sid, set()).add(mid)
    out = []
    for sess, booked, attended in rows:
        row = SessionOut.model_validate(sess).model_dump()
        regular = regulars.get(sess.id, set())
        taken = len(regular | holding.get(sess.id, set())) if regular else int(booked)
        out.append(row | {"booked": taken, "attended": int(attended)})
    return out


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
                InstructorLeave.status == LeaveStatus.APPROVED,
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
    stmt = sessions_with_counts().where(ClassSession.session_date.between(date_from, date_to))
    stmt = scope_to_branches(stmt, ClassSession.branch_id, user, branch_id)
    if instructor_id is not None:
        stmt = stmt.where(ClassSession.instructor_id == instructor_id)
    if program_id is not None:
        stmt = stmt.where(ClassSession.program_id == program_id)
    return await session_dicts(db, stmt)


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
    """The class roster: regular members first (with or without a check-in yet), then
    bookings, the waiting list in order, and cancellations."""
    records = list(
        await db.scalars(
            select(Attendance)
            .where(Attendance.session_id == sess.id)
            .options(selectinload(Attendance.member))
            .order_by(Attendance.booked_at, Attendance.id)
        )
    )
    regulars = await regular_member_ids(db, sess)
    recorded = {a.member_id for a in records}
    missing = regulars - recorded
    members = (
        list(await db.scalars(select(Member).where(Member.id.in_(missing)))) if missing else []
    )
    ids = list(recorded | missing)
    active = await _active_member_ids(db, ids, sess.session_date)
    rows = [
        {
            "id": None,
            "session_id": sess.id,
            "member_id": m.id,
            "status": None,
            "checked_in_at": None,
            "member": m,
            "is_regular": True,
        }
        for m in sorted(members, key=lambda m: (m.first_name, m.last_name))
    ] + [
        AttendanceOut.model_validate(a).model_dump() | {"is_regular": a.member_id in regulars}
        for a in records
    ]
    order = {None: 0, AttendanceStatus.WAITLISTED: 2, AttendanceStatus.CANCELLED: 3}
    rows.sort(key=lambda r: (not r["is_regular"], order.get(r["status"], 1)))
    return [
        AttendanceOut.model_validate(r).model_dump()
        | {"has_active_membership": r["member_id"] in active}
        for r in rows
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
    freed = await db.scalar(
        select(func.count()).where(
            Attendance.session_id == sess.id,
            Attendance.member_id.in_(entries),
            Attendance.status == AttendanceStatus.BOOKED,
        )
    )
    stmt = mysql_insert(Attendance).values(
        [
            {
                "session_id": sess.id,
                "member_id": mid,
                "status": st,
                "checked_in_at": now if st in PRESENT else None,
                "recorded_by": user.id,
                "booked_at": now,
                "cancelled_at": now if st == AttendanceStatus.CANCELLED else None,
            }
            for mid, st in entries.items()
        ]
    )
    stmt = stmt.on_duplicate_key_update(
        status=stmt.inserted.status,
        checked_in_at=func.coalesce(Attendance.checked_in_at, stmt.inserted.checked_in_at),
        recorded_by=stmt.inserted.recorded_by,
        cancelled_at=stmt.inserted.cancelled_at,
    )
    await db.execute(stmt)
    if await places_taken(db, sess) > capacity:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"Class is full ({capacity})")
    if freed:
        # A booked member marked absent, excused or cancelled frees their place.
        await promote_waitlist(db, sess)
    await db.commit()
    return await _attendance_rows(db, sess)


@router.delete(
    "/sessions/{session_id}/attendance/{member_id}", status_code=204, dependencies=any_role
)
async def remove_attendance(session_id: int, member_id: int, user: CurrentUser, db: DB) -> None:
    """Remove a booking (or a wrong check-in). A booked place freed this way goes to the
    waiting list."""
    sess = await get_scoped_or_404(db, ClassSession, session_id, user)
    await db.refresh(sess, with_for_update=True)
    row = await db.scalar(
        select(Attendance).where(
            Attendance.session_id == session_id, Attendance.member_id == member_id
        )
    )
    if row is not None:
        had_place = row.status == AttendanceStatus.BOOKED
        await db.delete(row)
        await db.flush()
        if had_place and sess.status == SessionStatus.SCHEDULED:
            await promote_waitlist(db, sess)
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
OPEN_LEAVE = (LeaveStatus.PENDING, LeaveStatus.APPROVED)


async def ensure_no_overlap(db: DB, instructor_id: int, first: date, last: date) -> None:
    """One coach cannot have two pending or approved leaves on the same day."""
    clash = await db.scalar(
        select(InstructorLeave.id).where(
            InstructorLeave.instructor_id == instructor_id,
            InstructorLeave.status.in_(OPEN_LEAVE),
            InstructorLeave.start_date <= last,
            InstructorLeave.end_date >= first,
        )
    )
    if clash is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Overlaps leave already requested or approved"
        )


async def hand_to_cover(db: DB, leave: InstructorLeave) -> int:
    """Put approved leave into effect: the coach's already-generated classes in the period go
    to the cover (unassigned when there is none). Returns how many classes moved."""
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
    return result.rowcount


async def hand_back(db: DB, leave: InstructorLeave) -> None:
    """Undo ``hand_to_cover``: classes still being covered go back to the coach."""
    await db.execute(
        update(ClassSession)
        .where(
            ClassSession.original_instructor_id == leave.instructor_id,
            ClassSession.status == SessionStatus.SCHEDULED,
            ClassSession.session_date.between(leave.start_date, leave.end_date),
        )
        .values(instructor_id=leave.instructor_id, original_instructor_id=None)
    )


@router.get("/leaves", response_model=list[LeaveOut], dependencies=any_role)
async def list_leaves(
    user: CurrentUser,
    db: DB,
    branch_id: int | None = None,
    instructor_id: int | None = None,
    active_on: date | None = None,
    leave_status: Annotated[LeaveStatus | None, Query(alias="status")] = None,
) -> list[InstructorLeave]:
    stmt = scope_to_branches(select(InstructorLeave), InstructorLeave.branch_id, user, branch_id)
    if instructor_id is not None:
        stmt = stmt.where(InstructorLeave.instructor_id == instructor_id)
    if active_on is not None:
        stmt = stmt.where(
            InstructorLeave.start_date <= active_on, InstructorLeave.end_date >= active_on
        )
    if leave_status is not None:
        stmt = stmt.where(InstructorLeave.status == leave_status)
    return list(await db.scalars(stmt.order_by(InstructorLeave.start_date.desc())))


@router.post("/leaves", response_model=LeaveCreated, status_code=201, dependencies=staff)
async def create_leave(body: LeaveIn, user: CurrentUser, db: DB) -> dict:
    """Record leave (approved at once) and hand the instructor's already-generated classes in
    that period to the cover instructor (unassigned when there is no cover)."""
    inst = await get_scoped_or_404(db, Instructor, body.instructor_id, user)
    await _check_instructor(db, user, body.cover_instructor_id)
    await ensure_no_overlap(db, inst.id, body.start_date, body.end_date)
    leave = InstructorLeave(
        **body.model_dump(),
        branch_id=inst.branch_id,
        status=LeaveStatus.APPROVED,
        requested_by=user.id,
        decided_by=user.id,
        decided_at=utcnow(),
    )
    db.add(leave)
    moved = await hand_to_cover(db, leave)
    await db.commit()
    await db.refresh(leave)
    return LeaveOut.model_validate(leave).model_dump() | {"sessions_reassigned": moved}


@router.post("/leaves/{leave_id}/decision", response_model=LeaveCreated, dependencies=staff)
async def decide_leave(leave_id: int, body: LeaveDecisionIn, user: CurrentUser, db: DB) -> dict:
    """Approve or reject a coach's leave request. Approving can set or change the cover."""
    leave = await get_scoped_or_404(db, InstructorLeave, leave_id, user)
    if leave.status != LeaveStatus.PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Leave is already {leave.status}")
    moved = 0
    if body.approve:
        if "cover_instructor_id" in body.model_fields_set:
            if body.cover_instructor_id == leave.instructor_id:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT, "A coach cannot cover their own leave"
                )
            await _check_instructor(db, user, body.cover_instructor_id)
            leave.cover_instructor_id = body.cover_instructor_id
        leave.status = LeaveStatus.APPROVED
        moved = await hand_to_cover(db, leave)
    else:
        leave.status = LeaveStatus.REJECTED
    leave.decided_by = user.id
    leave.decided_at = utcnow()
    leave.decision_note = body.note
    await db.commit()
    await db.refresh(leave)
    return LeaveOut.model_validate(leave).model_dump() | {"sessions_reassigned": moved}


@router.delete("/leaves/{leave_id}", status_code=204, dependencies=staff)
async def delete_leave(leave_id: int, user: CurrentUser, db: DB) -> None:
    """Remove leave: classes still being covered go back to the instructor."""
    leave = await get_scoped_or_404(db, InstructorLeave, leave_id, user)
    if leave.status == LeaveStatus.APPROVED:
        await hand_back(db, leave)
    await db.delete(leave)
    await db.commit()

"""Belt gradings (promotion tests) and seminars."""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.mysql import insert as mysql_insert

from app.core.deps import (
    ANY_ROLE,
    DB,
    STAFF,
    CurrentUser,
    apply_updates,
    can_access_branch,
    ensure_branch,
    get_scoped_or_404,
    require_roles,
    scope_to_branches,
)
from app.models import (
    Attendance,
    AttendanceStatus,
    BeltRank,
    ClassSession,
    GradingEvent,
    GradingOutcome,
    GradingResult,
    GradingStatus,
    Instructor,
    Member,
    MemberStatus,
    Seminar,
    seminar_attendance,
)
from app.schemas.progress import (
    EligibilityOut,
    GradingEventIn,
    GradingEventOut,
    GradingEventUpdate,
    GradingResultOut,
    GradingResultsIn,
    SeminarAttendeesIn,
    SeminarIn,
    SeminarOut,
)

router = APIRouter(tags=["gradings"])
any_role = [require_roles(*ANY_ROLE)]
staff = [require_roles(*STAFF)]


async def _check_instructor(db: DB, user, instructor_id: int | None) -> None:
    if instructor_id is None:
        return
    inst = await db.get(Instructor, instructor_id)
    if inst is None or not can_access_branch(user, inst.branch_id):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown instructor")


async def _belts(db: DB) -> list[BeltRank]:
    return list(await db.scalars(select(BeltRank).order_by(BeltRank.sort_order)))


def _next_rank(belts: list[BeltRank], current_id: int | None) -> BeltRank | None:
    if current_id is None:
        return belts[0] if belts else None
    order = {b.id: i for i, b in enumerate(belts)}
    i = order.get(current_id)
    return belts[i + 1] if i is not None and i + 1 < len(belts) else None


async def _members_in_scope(db: DB, user, member_ids) -> dict[int, Member]:
    members = {m.id: m for m in await db.scalars(select(Member).where(Member.id.in_(member_ids)))}
    if len(members) != len(set(member_ids)) or not all(
        can_access_branch(user, m.branch_id) for m in members.values()
    ):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown member_id")
    return members


# ---------------------------------------------------------------- grading events
@router.get("/gradings", response_model=list[GradingEventOut], dependencies=any_role)
async def list_gradings(
    user: CurrentUser, db: DB, branch_id: int | None = None, status: GradingStatus | None = None
) -> list[GradingEvent]:
    stmt = scope_to_branches(select(GradingEvent), GradingEvent.branch_id, user, branch_id)
    if status is not None:
        stmt = stmt.where(GradingEvent.status == status)
    return list(await db.scalars(stmt.order_by(GradingEvent.event_date.desc())))


@router.post("/gradings", response_model=GradingEventOut, status_code=201, dependencies=staff)
async def create_grading(body: GradingEventIn, user: CurrentUser, db: DB) -> GradingEvent:
    ensure_branch(user, body.branch_id)
    await _check_instructor(db, user, body.examiner_instructor_id)
    event = GradingEvent(**body.model_dump())
    db.add(event)
    await db.commit()
    return event


@router.patch("/gradings/{event_id}", response_model=GradingEventOut, dependencies=staff)
async def update_grading(
    event_id: int, body: GradingEventUpdate, user: CurrentUser, db: DB
) -> GradingEvent:
    event = await get_scoped_or_404(db, GradingEvent, event_id, user)
    data = body.model_dump(exclude_unset=True)
    if event.status == GradingStatus.COMPLETED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Grading is already finalised")
    if data.get("status") == GradingStatus.COMPLETED:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Use the finalise endpoint")
    await _check_instructor(db, user, data.get("examiner_instructor_id"))
    apply_updates(event, data)
    await db.commit()
    return event


@router.get(
    "/gradings/{event_id}/results", response_model=list[GradingResultOut], dependencies=any_role
)
async def grading_results(event_id: int, user: CurrentUser, db: DB) -> list[GradingResult]:
    await get_scoped_or_404(db, GradingEvent, event_id, user)
    stmt = select(GradingResult).where(GradingResult.event_id == event_id)
    return list(await db.scalars(stmt.order_by(GradingResult.id)))


@router.post(
    "/gradings/{event_id}/results", response_model=list[GradingResultOut], dependencies=any_role
)
async def record_results(
    event_id: int, body: GradingResultsIn, user: CurrentUser, db: DB
) -> list[GradingResult]:
    """Add candidates or record outcomes. The target rank defaults to the next belt."""
    event = await get_scoped_or_404(db, GradingEvent, event_id, user)
    if event.status != GradingStatus.PLANNED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Grading is not open")
    members = await _members_in_scope(db, user, [e.member_id for e in body.entries])
    belts = await _belts(db)
    by_id = {b.id: b for b in belts}
    existing = {
        r.member_id: r
        for r in await db.scalars(
            select(GradingResult).where(
                GradingResult.event_id == event.id, GradingResult.member_id.in_(members)
            )
        )
    }
    for e in body.entries:
        m = members[e.member_id]
        res = existing.get(m.id)
        if res is None:
            res = GradingResult(
                event_id=event.id,
                member_id=m.id,
                from_rank_id=m.belt_rank_id,
                from_stripes=m.stripes,
            )
            nxt = _next_rank(belts, m.belt_rank_id)
            res.to_rank_id = nxt.id if nxt else m.belt_rank_id
            res.to_stripes = 0 if nxt else min(m.stripes + 1, 4)
            db.add(res)
            existing[m.id] = res
        if e.to_rank_id is not None:
            if e.to_rank_id not in by_id:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown to_rank_id")
            res.to_rank_id = e.to_rank_id
        if e.to_stripes is not None:
            res.to_stripes = e.to_stripes
        if e.outcome == GradingOutcome.PASS:
            frm = by_id.get(res.from_rank_id).sort_order if res.from_rank_id else -1
            to = by_id[res.to_rank_id].sort_order if res.to_rank_id else -1
            if (to, res.to_stripes) <= (frm, res.from_stripes):
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    f"Member {m.id}: a pass must award a higher belt or more stripes",
                )
        res.outcome = e.outcome
        res.notes = e.notes if e.notes is not None else res.notes
    await db.commit()
    return sorted(existing.values(), key=lambda r: r.id)


@router.post("/gradings/{event_id}/finalize", response_model=GradingEventOut, dependencies=staff)
async def finalize_grading(event_id: int, user: CurrentUser, db: DB) -> GradingEvent:
    """Close the grading and promote every member who passed."""
    event = await get_scoped_or_404(db, GradingEvent, event_id, user)
    await db.refresh(event, with_for_update=True)
    if event.status != GradingStatus.PLANNED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Grading is not open")
    results = list(
        await db.scalars(select(GradingResult).where(GradingResult.event_id == event.id))
    )
    if any(r.outcome == GradingOutcome.PENDING for r in results):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Some results are pending")
    passed = {r.member_id: r for r in results if r.outcome == GradingOutcome.PASS}
    if passed:
        for m in await db.scalars(select(Member).where(Member.id.in_(passed))):
            m.belt_rank_id = passed[m.id].to_rank_id
            m.stripes = passed[m.id].to_stripes
    event.status = GradingStatus.COMPLETED
    await db.commit()
    return event


@router.get("/gradings-eligibility", response_model=list[EligibilityOut], dependencies=any_role)
async def eligibility(user: CurrentUser, db: DB, branch_id: int) -> list[dict]:
    """Promotion readiness per active member: seminar points against the next belt's
    requirement, and classes attended since their last promotion."""
    ensure_branch(user, branch_id)
    belts = await _belts(db)
    members = list(
        await db.scalars(
            select(Member)
            .where(Member.branch_id == branch_id, Member.status == MemberStatus.ACTIVE)
            .order_by(Member.last_name, Member.first_name)
        )
    )
    if not members:
        return []
    ids = [m.id for m in members]
    points = dict(
        (
            await db.execute(
                select(seminar_attendance.c.member_id, func.sum(Seminar.points))
                .join(Seminar, Seminar.id == seminar_attendance.c.seminar_id)
                .where(seminar_attendance.c.member_id.in_(ids))
                .group_by(seminar_attendance.c.member_id)
            )
        ).all()
    )
    last_promo = (
        select(GradingResult.member_id, func.max(GradingEvent.event_date).label("d"))
        .join(GradingEvent, GradingEvent.id == GradingResult.event_id)
        .where(
            GradingResult.outcome == GradingOutcome.PASS,
            GradingEvent.status == GradingStatus.COMPLETED,
            GradingResult.member_id.in_(ids),
        )
        .group_by(GradingResult.member_id)
        .subquery()
    )
    promoted_on = dict((await db.execute(select(last_promo.c.member_id, last_promo.c.d))).all())
    classes = dict(
        (
            await db.execute(
                select(Attendance.member_id, func.count())
                .join(ClassSession, ClassSession.id == Attendance.session_id)
                .join(Member, Member.id == Attendance.member_id)
                .outerjoin(last_promo, last_promo.c.member_id == Attendance.member_id)
                .where(
                    Attendance.member_id.in_(ids),
                    Attendance.status.in_((AttendanceStatus.PRESENT, AttendanceStatus.LATE)),
                    ClassSession.session_date >= func.coalesce(last_promo.c.d, Member.joined_on),
                )
                .group_by(Attendance.member_id)
            )
        ).all()
    )
    out = []
    for m in members:
        nxt = _next_rank(belts, m.belt_rank_id)
        required = nxt.seminars_required if nxt else 0
        pts = int(points.get(m.id) or 0)
        out.append(
            {
                "member_id": m.id,
                "member_name": f"{m.first_name} {m.last_name}",
                "belt_rank_id": m.belt_rank_id,
                "stripes": m.stripes,
                "next_rank_id": nxt.id if nxt else None,
                "seminar_points": pts,
                "seminars_required": required,
                "classes_since_promotion": int(classes.get(m.id, 0)),
                "last_promoted_on": promoted_on.get(m.id),
                "seminar_requirement_met": pts >= required,
            }
        )
    return out


# ---------------------------------------------------------------- seminars
@router.get("/seminars", response_model=list[SeminarOut], dependencies=any_role)
async def list_seminars(user: CurrentUser, db: DB, branch_id: int | None = None) -> list[dict]:
    counts = (
        select(seminar_attendance.c.seminar_id, func.count().label("n"))
        .group_by(seminar_attendance.c.seminar_id)
        .subquery()
    )
    stmt = select(Seminar, func.coalesce(counts.c.n, 0)).outerjoin(
        counts, counts.c.seminar_id == Seminar.id
    )
    stmt = scope_to_branches(stmt, Seminar.branch_id, user, branch_id)
    rows = (await db.execute(stmt.order_by(Seminar.seminar_date.desc()))).all()
    return [SeminarOut.model_validate(s).model_dump() | {"attendee_count": n} for s, n in rows]


@router.post("/seminars", response_model=SeminarOut, status_code=201, dependencies=staff)
async def create_seminar(body: SeminarIn, user: CurrentUser, db: DB) -> Seminar:
    ensure_branch(user, body.branch_id)
    await _check_instructor(db, user, body.instructor_id)
    seminar = Seminar(**body.model_dump())
    db.add(seminar)
    await db.commit()
    return seminar


@router.get("/seminars/{seminar_id}/attendees", response_model=list[int], dependencies=any_role)
async def seminar_attendees(seminar_id: int, user: CurrentUser, db: DB) -> list[int]:
    await get_scoped_or_404(db, Seminar, seminar_id, user)
    stmt = select(seminar_attendance.c.member_id).where(
        seminar_attendance.c.seminar_id == seminar_id
    )
    return list(await db.scalars(stmt))


@router.post("/seminars/{seminar_id}/attendees", response_model=list[int], dependencies=any_role)
async def add_seminar_attendees(
    seminar_id: int, body: SeminarAttendeesIn, user: CurrentUser, db: DB
) -> list[int]:
    await get_scoped_or_404(db, Seminar, seminar_id, user)
    ids = sorted(set(body.member_ids))
    await _members_in_scope(db, user, ids)
    stmt = mysql_insert(seminar_attendance).values(
        [{"seminar_id": seminar_id, "member_id": i} for i in ids]
    )
    await db.execute(stmt.on_duplicate_key_update(member_id=stmt.inserted.member_id))
    await db.commit()
    return await seminar_attendees(seminar_id, user, db)


@router.delete(
    "/seminars/{seminar_id}/attendees/{member_id}", status_code=204, dependencies=any_role
)
async def remove_seminar_attendee(seminar_id: int, member_id: int, user: CurrentUser, db: DB):
    await get_scoped_or_404(db, Seminar, seminar_id, user)
    await db.execute(
        delete(seminar_attendance).where(
            seminar_attendance.c.seminar_id == seminar_id,
            seminar_attendance.c.member_id == member_id,
        )
    )
    await db.commit()

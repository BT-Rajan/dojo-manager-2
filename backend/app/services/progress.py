"""A student's progress towards the next belt: skills at their belt, seminar points, coach
evaluations, monthly notes, test days, and the checks a coach looks at before a test."""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Attendance,
    AttendanceStatus,
    BeltRank,
    BeltSkill,
    ClassSession,
    Evaluation,
    GradingEvent,
    GradingOutcome,
    GradingResult,
    GradingStatus,
    Instructor,
    Member,
    NoteStatus,
    ProgressNote,
    Seminar,
    SkillCheck,
    seminar_attendance,
)


async def belts(db: AsyncSession) -> list[BeltRank]:
    return list(await db.scalars(select(BeltRank).order_by(BeltRank.sort_order)))


async def since_last_belt(db: AsyncSession, member: Member) -> date:
    """The date of the member's last promotion, or the day they joined."""
    promoted = await db.scalar(
        select(func.max(GradingEvent.event_date))
        .join(GradingResult, GradingResult.event_id == GradingEvent.id)
        .where(
            GradingResult.member_id == member.id,
            GradingResult.outcome == GradingOutcome.PASS,
            GradingEvent.status == GradingStatus.COMPLETED,
        )
    )
    return promoted or member.joined_on


async def seminar_points(db: AsyncSession, member: Member) -> int:
    total = await db.scalar(
        select(func.coalesce(func.sum(Seminar.points), 0))
        .join(seminar_attendance, seminar_attendance.c.seminar_id == Seminar.id)
        .where(seminar_attendance.c.member_id == member.id)
    )
    return int(total or 0)


async def classes_since(db: AsyncSession, member: Member, since: date) -> int:
    return int(
        await db.scalar(
            select(func.count())
            .select_from(Attendance)
            .join(ClassSession, ClassSession.id == Attendance.session_id)
            .where(
                Attendance.member_id == member.id,
                Attendance.status.in_((AttendanceStatus.PRESENT, AttendanceStatus.LATE)),
                ClassSession.session_date >= since,
            )
        )
        or 0
    )


CHECKS = (
    ("classes", "Classes since last belt", "الحصص منذ آخر حزام"),
    ("weeks", "Weeks at this belt", "أسابيع على هذا الحزام"),
    ("seminars", "Seminars attended (total)", "الندوات المحضورة (الإجمالي)"),
    ("evaluations", "Evaluations since last belt", "التقييمات منذ آخر حزام"),
)


async def progress(db: AsyncSession, member: Member, today: date) -> dict | None:
    """Everything the family and coaches see about the way to the next belt; None when the
    member has no belt yet."""
    if member.belt_rank_id is None:
        return None
    ranks = await belts(db)
    idx = next((i for i, b in enumerate(ranks) if b.id == member.belt_rank_id), None)
    if idx is None:
        return None
    belt = ranks[idx]
    nxt = ranks[idx + 1] if idx + 1 < len(ranks) else None
    since = await since_last_belt(db, member)
    classes = await classes_since(db, member, since)
    seminars = await seminar_points(db, member)
    evals_since = list(
        await db.scalars(
            select(Evaluation)
            .where(Evaluation.member_id == member.id, Evaluation.eval_date >= since)
            .order_by(Evaluation.eval_date.desc(), Evaluation.id.desc())
        )
    )
    ready = bool(evals_since) and evals_since[0].ready_for_test
    checks = []
    if nxt is not None:
        have = {
            "classes": classes,
            "weeks": (today - since).days // 7,
            "seminars": seminars,
            "evaluations": len(evals_since),
        }
        need = {
            "classes": nxt.min_classes,
            "weeks": nxt.min_weeks,
            "seminars": nxt.seminars_required,
            "evaluations": nxt.min_evaluations,
        }
        checks = [
            {
                "code": c,
                "en": en,
                "ar": ar,
                "have": have[c],
                "need": need[c],
                "ok": have[c] >= need[c],
            }
            for c, en, ar in CHECKS
        ]
        checks.append(
            {
                "code": "ready",
                "en": "Latest evaluation says ready",
                "ar": "آخر تقييم: جاهز للاختبار",
                "have": int(ready),
                "need": 1,
                "ok": ready,
            }
        )

    skills = list(
        await db.scalars(
            select(BeltSkill)
            .where(BeltSkill.belt_rank_id == belt.id, BeltSkill.is_active.is_(True))
            .order_by(BeltSkill.track, BeltSkill.sort_order, BeltSkill.id)
        )
    )
    checked = dict(
        (
            await db.execute(
                select(SkillCheck.skill_id, SkillCheck.checked_on).where(
                    SkillCheck.member_id == member.id,
                    SkillCheck.skill_id.in_([s.id for s in skills] or [-1]),
                )
            )
        ).all()
    )
    tests = list(
        await db.scalars(
            select(GradingEvent)
            .join(GradingResult, GradingResult.event_id == GradingEvent.id)
            .where(
                GradingResult.member_id == member.id,
                GradingEvent.status == GradingStatus.PLANNED,
                GradingEvent.event_date >= today,
            )
            .order_by(GradingEvent.event_date)
        )
    )
    evaluations = (
        await db.execute(
            select(Evaluation, Instructor.full_name)
            .outerjoin(Instructor, Instructor.id == Evaluation.instructor_id)
            .where(Evaluation.member_id == member.id)
            .order_by(Evaluation.eval_date.desc(), Evaluation.id.desc())
        )
    ).all()
    notes = list(
        await db.scalars(
            select(ProgressNote)
            .where(ProgressNote.member_id == member.id, ProgressNote.status == NoteStatus.SENT)
            .order_by(ProgressNote.month.desc(), ProgressNote.id.desc())
            .limit(3)
        )
    )
    return {
        "belt": belt,
        "stripes": member.stripes,
        "next": nxt,
        "since": since,
        "classes": classes,
        "seminars": seminars,
        "checks": checks,
        "eligible": bool(checks) and all(c["ok"] for c in checks),
        "skills": [
            {
                "id": s.id,
                "track": s.track,
                "category": s.category,
                "name": s.name,
                "checked_on": checked.get(s.id),
            }
            for s in skills
        ],
        "done": sum(1 for s in skills if s.id in checked),
        "total": len(skills),
        "tests": [{"id": t.id, "title": t.title, "event_date": t.event_date} for t in tests],
        "evaluations": [
            {
                "id": e.id,
                "eval_date": e.eval_date,
                "instructor_name": name,
                "notes": e.notes,
                "ready_for_test": e.ready_for_test,
            }
            for e, name in evaluations
        ],
        "notes": [
            {"id": n.id, "month": n.month, "worked_on": n.worked_on, "next_steps": n.next_steps}
            for n in notes
        ],
    }

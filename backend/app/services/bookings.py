"""Class places: regular members (weekly enrolments), bookings and the waiting list.

A class's places are taken by its regular members plus everyone booked or checked in who is
not a regular. When the class is full, new bookings go on the waiting list; when a booked
place is freed, the first on the waiting list gets it and is told by WhatsApp."""

from datetime import date, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import academy_tz
from app.models import (
    Attendance,
    AttendanceStatus,
    ClassSession,
    Enrollment,
    Guardian,
    GuardianLink,
    Member,
    MemberStatus,
    Program,
)
from app.models.base import utcnow
from app.services.messaging import send_message

# Statuses that hold a place in the class.
HOLDS_PLACE = (AttendanceStatus.BOOKED, AttendanceStatus.PRESENT, AttendanceStatus.LATE)
# Cancelling a booked place less than this long before the class is recorded as late.
NOTICE = timedelta(hours=2)
ADULT_AGE = 18


async def regular_member_ids(db: AsyncSession, session: ClassSession) -> set[int]:
    """Members with a regular place in this class on its date."""
    if session.schedule_id is None:
        return set()
    rows = await db.scalars(
        select(Enrollment.member_id)
        .join(Member, Member.id == Enrollment.member_id)
        .where(
            Enrollment.schedule_id == session.schedule_id,
            Enrollment.start_date <= session.session_date,
            or_(Enrollment.end_date.is_(None), Enrollment.end_date >= session.session_date),
            Member.status != MemberStatus.INACTIVE,
        )
    )
    return set(rows)


async def regulars_by_session(
    db: AsyncSession, sessions: list[ClassSession]
) -> dict[int, set[int]]:
    """``regular_member_ids`` for many sessions in one query."""
    schedule_ids = {s.schedule_id for s in sessions if s.schedule_id}
    if not schedule_ids:
        return {s.id: set() for s in sessions}
    rows = (
        await db.execute(
            select(
                Enrollment.schedule_id,
                Enrollment.member_id,
                Enrollment.start_date,
                Enrollment.end_date,
            )
            .join(Member, Member.id == Enrollment.member_id)
            .where(Enrollment.schedule_id.in_(schedule_ids), Member.status != MemberStatus.INACTIVE)
        )
    ).all()
    out: dict[int, set[int]] = {}
    for s in sessions:
        out[s.id] = {
            mid
            for sid, mid, start, end in rows
            if sid == s.schedule_id
            and start <= s.session_date
            and (end is None or end >= s.session_date)
        }
    return out


async def places_taken(db: AsyncSession, session: ClassSession) -> int:
    holding = set(
        await db.scalars(
            select(Attendance.member_id).where(
                Attendance.session_id == session.id, Attendance.status.in_(HOLDS_PLACE)
            )
        )
    )
    return len(await regular_member_ids(db, session) | holding)


def starts_at(session: ClassSession) -> datetime:
    return datetime.combine(session.session_date, session.start_time, tzinfo=academy_tz())


def has_started(session: ClassSession) -> bool:
    return datetime.now(academy_tz()) >= starts_at(session)


# ---------------------------------------------------------------- reaching the family
async def primary_guardian(db: AsyncSession, member_id: int) -> Guardian | None:
    link = await db.scalar(
        select(GuardianLink)
        .where(GuardianLink.member_id == member_id)
        .order_by(GuardianLink.is_primary.desc(), GuardianLink.guardian_id)
        .limit(1)
    )
    return link.guardian if link else None


def is_minor(member: Member, today: date) -> bool:
    dob = member.date_of_birth
    if dob is None:
        return False
    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    return age < ADULT_AGE


async def contact(db: AsyncSession, member: Member) -> tuple[str, str]:
    """(mobile, language) for messages about ``member``: children are reached through their
    primary guardian, adults on their own number."""
    today = datetime.now(academy_tz()).date()
    guardian = None
    if is_minor(member, today) or not member.portal_mobile:
        guardian = await primary_guardian(db, member.id)
    if guardian is not None:
        return guardian.mobile, guardian.language
    return member.portal_mobile or "", member.language


async def class_title(db: AsyncSession, session: ClassSession) -> str:
    if session.title:
        return session.title
    program = await db.get(Program, session.program_id)
    return program.name if program else "Class"


def when(session: ClassSession) -> str:
    return f"{session.session_date:%d/%m} {session.start_time:%H:%M}"


# ---------------------------------------------------------------- waiting list
async def promote_waitlist(db: AsyncSession, session: ClassSession) -> list[int]:
    """Give freed places to the waiting list in the order people joined it. Returns the
    member ids that got a place. The caller holds the session row lock and commits."""
    promoted = []
    capacity = session.capacity
    while await places_taken(db, session) < capacity:
        nxt = await db.scalar(
            select(Attendance)
            .where(
                Attendance.session_id == session.id,
                Attendance.status == AttendanceStatus.WAITLISTED,
            )
            .order_by(Attendance.booked_at, Attendance.id)
            .limit(1)
        )
        if nxt is None:
            break
        nxt.status = AttendanceStatus.BOOKED
        await db.flush()
        promoted.append(nxt.member_id)
        member = await db.get(Member, nxt.member_id)
        mobile, lang = await contact(db, member)
        if mobile:
            title = await class_title(db, session)
            text = (
                f"أصبح لديك مكان في حصة {title} يوم {when(session)}."
                if lang == "ar"
                else f"A place opened up for you: {title} on {when(session)}."
            )
            await send_message(db, mobile, text, kind="waitlist_place", member_id=member.id)
    return promoted


async def cancel_booking(db: AsyncSession, session: ClassSession, row: Attendance) -> None:
    """Cancel a booking or waiting-list spot; a freed place goes to the waiting list."""
    had_place = row.status == AttendanceStatus.BOOKED
    now = utcnow()
    row.status = AttendanceStatus.CANCELLED
    row.cancelled_at = now
    row.late_cancellation = had_place and starts_at(session) - datetime.now(academy_tz()) < NOTICE
    await db.flush()
    if had_place:
        await promote_waitlist(db, session)

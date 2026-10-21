"""The member and parent portal. Every function takes the signed-in portal session and
reaches members only through that session's own guardian or member profile, never by an id
sent from the browser alone."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import academy_tz
from app.core.clock import today as academy_today
from app.models import (
    Attendance,
    AttendanceStatus,
    BookingSource,
    ClassSession,
    Guardian,
    GuardianLink,
    Member,
    Membership,
    MembershipStatus,
    MemberStatus,
    PortalSession,
    SessionStatus,
)
from app.models.base import utcnow
from app.services.bookings import (
    cancel_booking,
    class_title,
    contact,
    has_started,
    places_taken,
    regular_member_ids,
    regulars_by_session,
    when,
)
from app.services.messaging import send_message

EXPIRING_DAYS = 5  # "renew soon" from this many days before the end date
ADULT_AGE = 18


def age_on(dob: date | None, on: date) -> int | None:
    if dob is None:
        return None
    return on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))


async def find_account(db: AsyncSession, mobile: str) -> tuple[Guardian | Member | None, str]:
    """The profile that signs in with ``mobile``: a guardian, or else an adult member."""
    guardian = await db.scalar(select(Guardian).where(Guardian.mobile == mobile).limit(1))
    if guardian is not None:
        return guardian, "guardian"
    members = await db.scalars(
        select(Member)
        .where(Member.portal_mobile == mobile, Member.status != MemberStatus.INACTIVE)
        .order_by(Member.id)
    )
    today = academy_today()
    for m in members:
        age = age_on(m.date_of_birth, today)
        if age is None or age >= ADULT_AGE:
            return m, "member"
    return None, ""


async def family(db: AsyncSession, session: PortalSession) -> list[Member]:
    """The signed-in family's current members: a guardian's children (and the adult member
    themselves when they sign in for their own account)."""
    ids: set[int] = set()
    if session.guardian_id is not None:
        ids |= set(
            await db.scalars(
                select(GuardianLink.member_id).where(
                    GuardianLink.guardian_id == session.guardian_id
                )
            )
        )
    if session.member_id is not None:
        ids.add(session.member_id)
    if not ids:
        return []
    stmt = (
        select(Member)
        .where(Member.id.in_(ids), Member.status != MemberStatus.INACTIVE)
        .order_by(Member.first_name, Member.id)
    )
    return list(await db.scalars(stmt))


async def member_for(db: AsyncSession, session: PortalSession, member_id: int) -> Member:
    for m in await family(db, session):
        if m.id == member_id:
            return m
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")


async def profile_name(db: AsyncSession, session: PortalSession) -> str:
    if session.guardian_id is not None:
        g = await db.get(Guardian, session.guardian_id)
        return g.full_name if g else ""
    m = await db.get(Member, session.member_id) if session.member_id else None
    return f"{m.first_name} {m.last_name}" if m else ""


# ---------------------------------------------------------------- membership status
@dataclass
class MemberStatusInfo:
    """``code``: active, expiring, expired, frozen or none; ``membership``: the one it is
    about (the current one, or the latest)."""

    code: str
    membership: Membership | None


async def member_status(db: AsyncSession, member: Member, today: date) -> MemberStatusInfo:
    items = list(
        await db.scalars(
            select(Membership)
            .where(
                Membership.member_id == member.id,
                Membership.status != MembershipStatus.CANCELLED,
            )
            .order_by(Membership.end_date.desc(), Membership.id.desc())
        )
    )
    covering = [m for m in items if m.start_date <= today <= m.end_date]
    if member.status == MemberStatus.FROZEN:
        return MemberStatusInfo(
            "frozen", covering[0] if covering else (items[0] if items else None)
        )
    for m in covering:
        if m.status == MembershipStatus.FROZEN:
            return MemberStatusInfo("frozen", m)
    active = [m for m in covering if m.status == MembershipStatus.ACTIVE]
    if active:
        m = max(active, key=lambda x: x.end_date)
        return MemberStatusInfo(
            "expiring" if (m.end_date - today).days <= EXPIRING_DAYS else "active", m
        )
    if items:
        return MemberStatusInfo("expired", items[0])
    return MemberStatusInfo("none", None)


async def next_class(db: AsyncSession, member: Member) -> ClassSession | None:
    """The member's next class: a regular weekly class or one they are booked into."""
    rows = await upcoming(db, member, days=60, bookable=False)
    return rows[0]["session"] if rows else None


# ---------------------------------------------------------------- classes
BOOK_AHEAD_DAYS = 7


async def membership_for_class(
    db: AsyncSession, member: Member, program_id: int, day: date
) -> tuple[Membership | None, str]:
    """The membership that covers a class, or a reason: other_program, frozen, expired or
    no_membership."""
    items = list(
        await db.scalars(
            select(Membership)
            .where(
                Membership.member_id == member.id,
                Membership.status != MembershipStatus.CANCELLED,
            )
            .order_by(Membership.end_date)
        )
    )
    covering = [m for m in items if m.start_date <= day <= m.end_date]
    if member.status == MemberStatus.FROZEN or any(
        m.status == MembershipStatus.FROZEN for m in covering
    ):
        return None, "frozen"
    usable = [m for m in covering if m.status == MembershipStatus.ACTIVE]
    fitting = [m for m in usable if m.plan.program_id in (None, program_id)]
    if fitting:
        return fitting[0], ""  # the one ending soonest
    if usable:
        return None, "other_program"
    if items:
        return None, "expired"
    return None, "no_membership"


async def upcoming(
    db: AsyncSession, member: Member, days: int = BOOK_AHEAD_DAYS, bookable: bool = True
) -> list[dict]:
    """Classes in the next ``days`` at the member's branch that are theirs (a regular place or a
    booking) and, with ``bookable``, the ones their membership lets them book."""
    now = datetime.now(academy_tz())
    today = now.date()
    sessions = list(
        await db.scalars(
            select(ClassSession)
            .where(
                ClassSession.branch_id == member.branch_id,
                ClassSession.status == SessionStatus.SCHEDULED,
                ClassSession.session_date.between(today, today + timedelta(days=days)),
            )
            .order_by(ClassSession.session_date, ClassSession.start_time)
        )
    )
    sessions = [s for s in sessions if s.session_date > today or s.start_time > now.time()]
    if not sessions:
        return []
    bookings = {
        a.session_id: a
        for a in await db.scalars(
            select(Attendance).where(
                Attendance.member_id == member.id,
                Attendance.session_id.in_([s.id for s in sessions]),
                Attendance.status.in_((AttendanceStatus.BOOKED, AttendanceStatus.WAITLISTED)),
            )
        )
    }
    regulars = await regulars_by_session(db, sessions)
    rows = []
    for s in sessions:
        regular = member.id in regulars.get(s.id, set())
        booking = bookings.get(s.id)
        can_book = False
        if bookable and not regular and booking is None:
            membership, warning = await membership_for_class(
                db, member, s.program_id, s.session_date
            )
            can_book = membership is not None and warning == ""
        if regular or booking or can_book:
            rows.append(
                {"session": s, "regular": regular, "booking": booking, "can_book": can_book}
            )
    return rows


async def recent_attendance(db: AsyncSession, member: Member, limit: int = 10) -> list[tuple]:
    rows = await db.execute(
        select(ClassSession, Attendance)
        .join(Attendance, Attendance.session_id == ClassSession.id)
        .where(
            Attendance.member_id == member.id,
            Attendance.status.in_((AttendanceStatus.PRESENT, AttendanceStatus.LATE)),
        )
        .order_by(ClassSession.session_date.desc(), ClassSession.start_time.desc())
        .limit(limit)
    )
    return list(rows.all())


MESSAGES = {
    "booking_confirmed": (
        "{member} is booked for {cls} on {when}. — Elite Academy",
        "تم حجز {member} في {cls} بتاريخ {when}. — أكاديمية إيليت",
    ),
    "waitlisted": (
        "{cls} on {when} is full: {member} is on the waiting list and we'll message you if a "
        "place opens. — Elite Academy",
        "حصة {cls} بتاريخ {when} ممتلئة: {member} في قائمة الانتظار وسنراسلك إن توفر مكان. "
        "— أكاديمية إيليت",
    ),
}


def render(key: str, lang: str, **values) -> str:
    en, ar = MESSAGES[key]
    return (ar if lang == "ar" else en).format(**values)


async def remember_language(db: AsyncSession, session: PortalSession, lang: str) -> None:
    """Messages go out in the language the family last used in the portal."""
    if session.guardian_id is not None:
        g = await db.get(Guardian, session.guardian_id)
        if g is not None:
            g.language = lang
    elif session.member_id is not None:
        m = await db.get(Member, session.member_id)
        if m is not None:
            m.language = lang


async def book(
    db: AsyncSession, session: PortalSession, member: Member, session_id: int, lang: str
) -> Attendance:
    """Book a class from the portal: up to 7 days ahead, at the member's branch, when their
    membership covers it. A full class puts them on the waiting list."""
    cls = await db.get(ClassSession, session_id, with_for_update=True)
    today = academy_today()
    if cls is None or cls.branch_id != member.branch_id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Book classes at your own branch."
        )
    if cls.status != SessionStatus.SCHEDULED:
        raise HTTPException(status.HTTP_409_CONFLICT, "This class is cancelled.")
    if has_started(cls):
        raise HTTPException(status.HTTP_409_CONFLICT, "This class has already started.")
    if not today <= cls.session_date <= today + timedelta(days=BOOK_AHEAD_DAYS):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Classes can be booked up to {BOOK_AHEAD_DAYS} days ahead.",
        )
    membership, warning = await membership_for_class(db, member, cls.program_id, cls.session_date)
    if membership is None or warning:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "The membership doesn't cover this class — please contact the branch.",
        )
    if member.id in await regular_member_ids(db, cls):
        raise HTTPException(status.HTTP_409_CONFLICT, "Already has a regular place in this class.")
    row = await db.scalar(
        select(Attendance).where(Attendance.session_id == cls.id, Attendance.member_id == member.id)
    )
    if row is not None and row.status != AttendanceStatus.CANCELLED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Already booked into this class.")
    full = await places_taken(db, cls) >= cls.capacity
    new_status = AttendanceStatus.WAITLISTED if full else AttendanceStatus.BOOKED
    now = utcnow()
    if row is None:
        row = Attendance(session_id=cls.id, member_id=member.id)
        db.add(row)
    row.status = new_status
    row.source = BookingSource.PORTAL
    row.booked_at = now
    row.cancelled_at = None
    row.late_cancellation = False
    row.checked_in_at = None
    await remember_language(db, session, lang)
    await db.flush()
    mobile, msg_lang = await contact(db, member)
    if mobile:
        key = "waitlisted" if full else "booking_confirmed"
        text = render(
            key,
            msg_lang,
            member=f"{member.first_name} {member.last_name}",
            cls=await class_title(db, cls),
            when=when(cls),
        )
        await send_message(db, mobile, text, kind=key, member_id=member.id)
    return row


async def cancel(
    db: AsyncSession, session: PortalSession, member: Member, session_id: int, lang: str
) -> Attendance:
    cls = await db.get(ClassSession, session_id, with_for_update=True)
    row = (
        await db.scalar(
            select(Attendance).where(
                Attendance.session_id == session_id, Attendance.member_id == member.id
            )
        )
        if cls
        else None
    )
    if row is None or row.status not in (AttendanceStatus.BOOKED, AttendanceStatus.WAITLISTED):
        raise HTTPException(status.HTTP_409_CONFLICT, "This booking can no longer be cancelled.")
    if has_started(cls):
        raise HTTPException(status.HTTP_409_CONFLICT, "This class has already started.")
    await remember_language(db, session, lang)
    await cancel_booking(db, cls, row)
    return row

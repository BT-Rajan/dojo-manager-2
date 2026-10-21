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
    """The member's next class: the next one they are booked into."""
    now = datetime.now(academy_tz())
    today = now.date()
    stmt = (
        select(ClassSession)
        .join(Attendance, Attendance.session_id == ClassSession.id)
        .where(
            Attendance.member_id == member.id,
            Attendance.status == AttendanceStatus.BOOKED,
            ClassSession.status == SessionStatus.SCHEDULED,
            ClassSession.session_date >= today,
            ClassSession.session_date <= today + timedelta(days=60),
        )
        .order_by(ClassSession.session_date, ClassSession.start_time)
    )
    for s in await db.scalars(stmt):
        if s.session_date > today or s.end_time > now.time():
            return s
    return None

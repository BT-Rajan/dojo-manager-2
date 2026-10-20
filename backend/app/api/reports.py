"""Dashboard and periodic reports (weekly sales, weekly branch report, attendance)."""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import and_, case, exists, func, select, true
from sqlalchemy.orm import aliased
from sqlalchemy.sql import ColumnElement

from app.core.deps import ANY_ROLE, DB, STAFF, CurrentUser, ensure_branch, require_roles
from app.models import (
    Attendance,
    AttendanceStatus,
    CaseStatus,
    ClassSession,
    Complaint,
    Incident,
    InventoryItem,
    Lead,
    LeadStatus,
    Member,
    Membership,
    MembershipStatus,
    MemberStatus,
    Payment,
    PaymentCategory,
    Program,
    SessionStatus,
    StockLevel,
    User,
)

router = APIRouter(tags=["reports"])

PRESENT = (AttendanceStatus.PRESENT, AttendanceStatus.LATE)
ATTENDING = (AttendanceStatus.BOOKED, *PRESENT)


def _branch_filter(user: User, branch_id: int | None):
    """Returns a function mapping a branch column to a WHERE clause for the caller's scope."""
    if branch_id is not None:
        ensure_branch(user, branch_id)
        return lambda col: col == branch_id
    if user.sees_all_branches:
        return lambda col: true()
    ids = user.branch_ids or [-1]
    return lambda col: col.in_(ids)


def _day_bounds(d1: date, d2: date) -> tuple[datetime, datetime]:
    return datetime.combine(d1, time.min), datetime.combine(d2 + timedelta(days=1), time.min)


def _last_saturday(d: date) -> date:
    return d - timedelta(days=(d.weekday() - 5) % 7)  # academy weeks run Saturday-Friday


def _active_on(day: date) -> ColumnElement[bool]:
    return exists().where(
        Membership.member_id == Member.id,
        Membership.status == MembershipStatus.ACTIVE,
        Membership.start_date <= day,
        Membership.end_date >= day,
    )


async def _count(db: DB, stmt) -> int:
    return int(await db.scalar(stmt) or 0)


@router.get("/dashboard", dependencies=[require_roles(*ANY_ROLE)])
async def dashboard(user: CurrentUser, db: DB, branch_id: int | None = None) -> dict[str, Any]:
    f = _branch_filter(user, branch_id)
    today = date.today()
    month_start = today.replace(day=1)
    later = aliased(Membership)
    latest = ~exists().where(
        later.member_id == Membership.member_id,
        later.end_date > Membership.end_date,
        later.status != MembershipStatus.CANCELLED,
    )

    counts = (
        select(
            Attendance.session_id,
            func.sum(case((Attendance.status.in_(ATTENDING), 1), else_=0)).label("booked"),
            func.sum(case((Attendance.status.in_(PRESENT), 1), else_=0)).label("attended"),
        )
        .group_by(Attendance.session_id)
        .subquery()
    )
    today_rows = (
        await db.execute(
            select(
                ClassSession.id,
                ClassSession.branch_id,
                ClassSession.start_time,
                ClassSession.end_time,
                ClassSession.status,
                ClassSession.capacity,
                ClassSession.instructor_id,
                Program.name,
                func.coalesce(counts.c.booked, 0),
                func.coalesce(counts.c.attended, 0),
            )
            .join(Program, Program.id == ClassSession.program_id)
            .outerjoin(counts, counts.c.session_id == ClassSession.id)
            .where(ClassSession.session_date == today, f(ClassSession.branch_id))
            .order_by(ClassSession.start_time)
        )
    ).all()
    keys = (
        "id",
        "branch_id",
        "start_time",
        "end_time",
        "status",
        "capacity",
        "instructor_id",
        "program",
        "booked",
        "attended",
    )
    result: dict[str, Any] = {
        "date": today,
        "active_members": await _count(
            db,
            select(func.count())
            .select_from(Member)
            .where(f(Member.branch_id), Member.status == MemberStatus.ACTIVE, _active_on(today)),
        ),
        "new_members_this_month": await _count(
            db,
            select(func.count()).where(f(Member.branch_id), Member.joined_on >= month_start),
        ),
        "expiring_within_5_days": await _count(
            db,
            select(func.count()).where(
                f(Membership.branch_id),
                Membership.status == MembershipStatus.ACTIVE,
                Membership.end_date.between(today, today + timedelta(days=5)),
                latest,
            ),
        ),
        "expired_last_30_days": await _count(
            db,
            select(func.count()).where(
                f(Membership.branch_id),
                Membership.status == MembershipStatus.ACTIVE,
                Membership.end_date.between(today - timedelta(days=30), today - timedelta(days=1)),
                latest,
            ),
        ),
        "today_classes": [
            {
                k: (int(v) if k in ("booked", "attended") else v)
                for k, v in zip(keys, r, strict=True)
            }
            for r in today_rows
        ],
        "open_leads": await _count(
            db,
            select(func.count()).where(
                f(Lead.branch_id), Lead.status.not_in((LeadStatus.CONVERTED, LeadStatus.LOST))
            ),
        ),
        "open_incidents": await _count(
            db,
            select(func.count()).where(f(Incident.branch_id), Incident.status == CaseStatus.OPEN),
        ),
        "open_complaints": await _count(
            db,
            select(func.count()).where(f(Complaint.branch_id), Complaint.status == CaseStatus.OPEN),
        ),
        "low_stock_items": await _count(
            db,
            select(func.count())
            .select_from(StockLevel)
            .join(InventoryItem, InventoryItem.id == StockLevel.item_id)
            .where(
                f(StockLevel.branch_id),
                InventoryItem.is_active.is_(True),
                StockLevel.quantity <= InventoryItem.reorder_level,
            ),
        ),
    }
    if user.role in STAFF:
        rev = select(func.coalesce(func.sum(Payment.amount), 0)).where(
            f(Payment.branch_id), Payment.is_void.is_(False)
        )
        lo, hi = _day_bounds(today, today)
        result["revenue_today"] = await db.scalar(rev.where(Payment.paid_at.between(lo, hi)))
        lo, _ = _day_bounds(month_start, today)
        result["revenue_month"] = await db.scalar(rev.where(Payment.paid_at.between(lo, hi)))
    return result


@router.get("/reports/weekly-sales", dependencies=[require_roles(*STAFF)])
async def weekly_sales(
    user: CurrentUser, db: DB, branch_id: int, week_start: date | None = None
) -> dict[str, Any]:
    """Every transaction of the week (Saturday-Friday) with totals by method and category."""
    ensure_branch(user, branch_id)
    start = week_start or _last_saturday(date.today())
    end = start + timedelta(days=6)
    lo, hi = _day_bounds(start, end)
    rows = (
        await db.execute(
            select(Payment, Member.first_name, Member.last_name)
            .outerjoin(Member, Member.id == Payment.member_id)
            .where(
                Payment.branch_id == branch_id,
                Payment.is_void.is_(False),
                Payment.paid_at >= lo,
                Payment.paid_at < hi,
            )
            .order_by(Payment.paid_at)
        )
    ).all()
    by_method: dict[str, Decimal] = {}
    by_category: dict[str, Decimal] = {}
    lines = []
    for p, first, last in rows:
        by_method[p.method] = by_method.get(p.method, Decimal(0)) + p.amount
        by_category[p.category] = by_category.get(p.category, Decimal(0)) + p.amount
        lines.append(
            {
                "payment_id": p.id,
                "paid_at": p.paid_at,
                "member": f"{first} {last}" if first else None,
                "category": p.category,
                "method": p.method,
                "amount": p.amount,
                "reference": p.reference,
            }
        )
    return {
        "branch_id": branch_id,
        "week_start": start,
        "week_end": end,
        "transactions": lines,
        "total": sum(by_method.values(), Decimal(0)),
        "by_method": by_method,
        "by_category": by_category,
    }


async def _week_measures(db: DB, branch_id: int, start: date) -> dict[str, int]:
    end = start + timedelta(days=6)
    lo, hi = _day_bounds(start, end)
    later = aliased(Membership)
    renewed = exists().where(
        later.member_id == Membership.member_id,
        later.end_date > Membership.end_date,
        later.status != MembershipStatus.CANCELLED,
    )
    lead_created = and_(Lead.branch_id == branch_id, Lead.created_at >= lo, Lead.created_at < hi)
    return {
        "active_members": await _count(
            db,
            select(func.count())
            .select_from(Member)
            .where(Member.branch_id == branch_id, _active_on(end)),
        ),
        "new_members": await _count(
            db,
            select(func.count()).where(
                Member.branch_id == branch_id, Member.joined_on.between(start, end)
            ),
        ),
        "renewals": await _count(
            db,
            select(func.count()).where(
                Payment.branch_id == branch_id,
                Payment.category == PaymentCategory.RENEWAL,
                Payment.is_void.is_(False),
                Payment.paid_at >= lo,
                Payment.paid_at < hi,
            ),
        ),
        "members_lost": await _count(
            db,
            select(func.count()).where(
                Membership.branch_id == branch_id,
                Membership.status != MembershipStatus.CANCELLED,
                Membership.end_date.between(start, end),
                ~renewed,
            ),
        ),
        "new_leads": await _count(db, select(func.count()).where(lead_created)),
        "trials_booked": await _count(
            db,
            select(func.count())
            .select_from(Lead)
            .join(ClassSession, ClassSession.id == Lead.trial_session_id)
            .where(Lead.branch_id == branch_id, ClassSession.session_date.between(start, end)),
        ),
        "leads_converted": await _count(
            db,
            select(func.count())
            .select_from(Lead)
            .join(Member, Member.id == Lead.converted_member_id)
            .where(Lead.branch_id == branch_id, Member.joined_on.between(start, end)),
        ),
        "incidents": await _count(
            db,
            select(func.count()).where(
                Incident.branch_id == branch_id,
                Incident.occurred_at >= lo,
                Incident.occurred_at < hi,
            ),
        ),
        "complaints_received": await _count(
            db,
            select(func.count()).where(
                Complaint.branch_id == branch_id, Complaint.received_on.between(start, end)
            ),
        ),
        "complaints_closed": await _count(
            db,
            select(func.count()).where(
                Complaint.branch_id == branch_id, Complaint.closed_on.between(start, end)
            ),
        ),
        "class_changes": await _count(
            db,
            select(func.count()).where(
                ClassSession.branch_id == branch_id,
                ClassSession.session_date.between(start, end),
                ClassSession.change_reason.is_not(None),
            ),
        ),
        "classes_cancelled": await _count(
            db,
            select(func.count()).where(
                ClassSession.branch_id == branch_id,
                ClassSession.session_date.between(start, end),
                ClassSession.status == SessionStatus.CANCELLED,
            ),
        ),
        "attendances": await _count(
            db,
            select(func.count())
            .select_from(Attendance)
            .join(ClassSession, ClassSession.id == Attendance.session_id)
            .where(
                ClassSession.branch_id == branch_id,
                ClassSession.session_date.between(start, end),
                Attendance.status.in_(PRESENT),
            ),
        ),
    }


@router.get("/reports/weekly-branch", dependencies=[require_roles(*STAFF)])
async def weekly_branch(
    user: CurrentUser, db: DB, branch_id: int, week_start: date | None = None
) -> dict[str, Any]:
    """This week against last week for the weekly branch report."""
    ensure_branch(user, branch_id)
    start = week_start or _last_saturday(date.today())
    this = await _week_measures(db, branch_id, start)
    last = await _week_measures(db, branch_id, start - timedelta(days=7))
    return {
        "branch_id": branch_id,
        "week_start": start,
        "week_end": start + timedelta(days=6),
        "measures": [
            {"measure": k, "this_week": this[k], "last_week": last[k], "change": this[k] - last[k]}
            for k in this
        ],
    }


@router.get("/reports/attendance", dependencies=[require_roles(*STAFF)])
async def attendance_report(
    user: CurrentUser, db: DB, branch_id: int, date_from: date, date_to: date
) -> list[dict[str, Any]]:
    """Per programme: classes held, total attendances and average class size."""
    ensure_branch(user, branch_id)
    if date_to < date_from or (date_to - date_from).days > 366:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid date range")
    present = func.sum(case((Attendance.status.in_(PRESENT), 1), else_=0))
    rows = (
        await db.execute(
            select(
                Program.id,
                Program.name,
                func.count(func.distinct(ClassSession.id)),
                func.coalesce(present, 0),
            )
            .join(ClassSession, ClassSession.program_id == Program.id)
            .outerjoin(Attendance, Attendance.session_id == ClassSession.id)
            .where(
                ClassSession.branch_id == branch_id,
                ClassSession.session_date.between(date_from, date_to),
                ClassSession.status != SessionStatus.CANCELLED,
            )
            .group_by(Program.id, Program.name)
            .order_by(Program.name)
        )
    ).all()
    return [
        {
            "program_id": pid,
            "program": name,
            "classes": int(n),
            "attendances": int(att),
            "average_class_size": round(int(att) / int(n), 1) if n else 0.0,
        }
        for pid, name, n, att in rows
    ]

from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.deps import (
    DB,
    MANAGEMENT,
    STAFF,
    CurrentUser,
    Page,
    ensure_branch,
    get_scoped_or_404,
    require_roles,
    scope_to_branches,
    utcnow,
)
from app.models import Member, Membership, Payment, PaymentCategory, PaymentMethod
from app.schemas.dojo import PaymentIn, PaymentOut, PaymentVoid
from app.services.audit import audit

router = APIRouter(prefix="/payments", tags=["payments"], dependencies=[require_roles(*STAFF)])


@router.get("", response_model=list[PaymentOut])
async def list_payments(
    user: CurrentUser,
    db: DB,
    page: Page,
    branch_id: int | None = None,
    member_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    method: PaymentMethod | None = None,
    category: PaymentCategory | None = None,
    include_void: bool = False,
) -> list[Payment]:
    stmt = scope_to_branches(select(Payment), Payment.branch_id, user, branch_id)
    if member_id is not None:
        stmt = stmt.where(Payment.member_id == member_id)
    if date_from:
        stmt = stmt.where(Payment.paid_at >= datetime.combine(date_from, time.min))
    if date_to:
        stmt = stmt.where(Payment.paid_at < datetime.combine(date_to + timedelta(days=1), time.min))
    if method:
        stmt = stmt.where(Payment.method == method)
    if category:
        stmt = stmt.where(Payment.category == category)
    if not include_void:
        stmt = stmt.where(Payment.is_void.is_(False))
    return list(await db.scalars(page.apply(stmt.order_by(Payment.paid_at.desc()))))


@router.post("", response_model=PaymentOut, status_code=status.HTTP_201_CREATED)
async def record_payment(body: PaymentIn, user: CurrentUser, db: DB) -> Payment:
    ensure_branch(user, body.branch_id)
    if body.member_id is not None:
        member = await get_scoped_or_404(db, Member, body.member_id, user)
        if member.branch_id != body.branch_id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Member is at another branch"
            )
    if body.membership_id is not None:
        ms = await get_scoped_or_404(db, Membership, body.membership_id, user)
        if ms.member_id != body.member_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Membership/member mismatch")
    now = utcnow()
    payment = Payment(**body.model_dump(), paid_at=now, created_at=now, received_by=user.id)
    db.add(payment)
    await db.commit()
    return payment


@router.post(
    "/{payment_id}/void", response_model=PaymentOut, dependencies=[require_roles(*MANAGEMENT)]
)
async def void_payment(payment_id: int, body: PaymentVoid, user: CurrentUser, db: DB) -> Payment:
    payment = await get_scoped_or_404(db, Payment, payment_id, user)
    if payment.is_void:
        raise HTTPException(status.HTTP_409_CONFLICT, "Payment already void")
    payment.is_void = True
    payment.void_reason = body.reason
    payment.voided_by = user.id
    audit(db, user, "void", "payment", payment.id, amount=payment.amount, reason=body.reason)
    await db.commit()
    return payment

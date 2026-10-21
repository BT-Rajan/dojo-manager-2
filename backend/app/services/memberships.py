from datetime import timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import today as academy_today
from app.core.deps import utcnow
from app.models import (
    Member,
    Membership,
    MembershipPlan,
    MembershipStatus,
    Payment,
    PaymentCategory,
    Role,
    User,
)
from app.schemas.dojo import MembershipIn


async def create_membership(
    db: AsyncSession, member: Member, body: MembershipIn, user: User | None
):
    """``user`` is None for a renewal the family paid online in the portal."""
    plan = await db.get(MembershipPlan, body.plan_id)
    if plan is None or not plan.is_active:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown or inactive plan")
    if plan.branch_id is not None and plan.branch_id != member.branch_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Plan not offered at branch")
    if (
        body.price is not None
        and body.price != plan.price
        and (user is None or user.role)
        not in (
            Role.OWNER,
            Role.MANAGER,
        )
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only managers can override plan prices")

    # Lock the member's memberships so concurrent renewals cannot overlap.
    latest_end = await db.scalar(
        select(func.max(Membership.end_date))
        .where(
            Membership.member_id == member.id,
            Membership.status != MembershipStatus.CANCELLED,
        )
        .with_for_update()
    )
    is_renewal = latest_end is not None
    today = academy_today()
    start = body.start_date
    if start is None:
        # Renewing before expiry continues from the day after the current membership ends.
        start = latest_end + timedelta(days=1) if latest_end and latest_end >= today else today

    price: Decimal = body.price if body.price is not None else plan.price
    membership = Membership(
        member_id=member.id,
        branch_id=member.branch_id,
        plan_id=plan.id,
        start_date=start,
        end_date=start + timedelta(days=plan.duration_days - 1),
        price=price,
        notes=body.notes,
        created_by=user.id if user else None,
    )
    db.add(membership)
    await db.flush()

    if body.payment is not None and price > 0:
        now = utcnow()
        db.add(
            Payment(
                branch_id=member.branch_id,
                member_id=member.id,
                membership_id=membership.id,
                amount=price,
                method=body.payment.method,
                category=PaymentCategory.RENEWAL if is_renewal else PaymentCategory.NEW,
                reference=body.payment.reference,
                paid_at=now,
                created_at=now,
                received_by=user.id if user else None,
            )
        )
    await db.refresh(membership, ["plan"])
    return membership

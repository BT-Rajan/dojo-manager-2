from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import exists, select
from sqlalchemy.orm import aliased, selectinload

from app.core.deps import (
    DB,
    MANAGEMENT,
    STAFF,
    CurrentUser,
    apply_updates,
    get_scoped_or_404,
    require_roles,
    scope_to_branches,
)
from app.models import Member, Membership, MembershipStatus
from app.schemas.dojo import ExpiringMembershipOut, MembershipIn, MembershipOut, MembershipUpdate
from app.services.audit import audit
from app.services.memberships import create_membership

router = APIRouter(
    prefix="/memberships", tags=["memberships"], dependencies=[require_roles(*STAFF)]
)


@router.post("", response_model=MembershipOut, status_code=status.HTTP_201_CREATED)
async def add_membership(body: MembershipIn, user: CurrentUser, db: DB) -> Membership:
    member = await get_scoped_or_404(db, Member, body.member_id, user)
    membership = await create_membership(db, member, body, user)
    await db.commit()
    return membership


@router.get("/expiring", response_model=list[ExpiringMembershipOut])
async def expiring_memberships(
    user: CurrentUser,
    db: DB,
    branch_id: int | None = None,
    days: Annotated[int, Query(ge=0, le=60)] = 5,
    expired_since_days: Annotated[int, Query(ge=0, le=365)] = 30,
) -> list[Membership]:
    """Renewal follow-up list: members whose latest membership has expired recently or
    expires within ``days`` days (the per-shift expiry list)."""
    today = date.today()
    later = aliased(Membership)
    has_later = exists().where(
        later.member_id == Membership.member_id,
        later.end_date > Membership.end_date,
        later.status != MembershipStatus.CANCELLED,
    )
    stmt = (
        select(Membership)
        .join(Member, Member.id == Membership.member_id)
        .where(
            Membership.status == MembershipStatus.ACTIVE,
            Membership.end_date <= today + timedelta(days=days),
            Membership.end_date >= today - timedelta(days=expired_since_days),
            ~has_later,
        )
        .options(selectinload(Membership.member))
        .order_by(Membership.end_date)
    )
    stmt = scope_to_branches(stmt, Membership.branch_id, user, branch_id)
    return list(await db.scalars(stmt))


@router.patch("/{membership_id}", response_model=MembershipOut)
async def update_membership(
    membership_id: int, body: MembershipUpdate, user: CurrentUser, db: DB
) -> Membership:
    membership = await get_scoped_or_404(db, Membership, membership_id, user)
    data = body.model_dump(exclude_unset=True)
    if "end_date" in data:
        if user.role not in MANAGEMENT:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only managers can change end dates")
        if data["end_date"] < membership.start_date:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "end_date before start")
    apply_updates(membership, data)
    audit(db, user, "update", "membership", membership.id, **{k: str(v) for k, v in data.items()})
    await db.commit()
    return membership

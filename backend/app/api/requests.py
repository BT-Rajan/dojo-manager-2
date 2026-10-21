"""Membership requests the operations manager decides: freezes (from the member portal)."""

from datetime import date, datetime

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.core.deps import (
    DB,
    MANAGEMENT,
    STAFF,
    CurrentUser,
    get_scoped_or_404,
    require_roles,
    scope_to_branches,
    utcnow,
)
from app.models import Member, Membership, MembershipRequest, RequestStatus
from app.schemas.common import InModel, OutModel, ShortText
from app.services.audit import audit
from app.services.portal import apply_freeze

router = APIRouter(prefix="/membership-requests", tags=["membership requests"])


class RequestOut(OutModel):
    id: int
    kind: str
    branch_id: int
    member_id: int
    member_name: str
    membership_id: int
    plan_name: str
    membership_end: date
    freeze_start: date | None
    freeze_weeks: int | None
    reason: str
    status: RequestStatus
    from_portal: bool
    created_at: datetime
    decided_at: datetime | None
    decision_note: str | None


class DecisionIn(InModel):
    approve: bool
    note: ShortText | None = None


async def _out(db, req: MembershipRequest) -> dict:
    member = await db.get(Member, req.member_id)
    ms = await db.get(Membership, req.membership_id)
    return {
        **{c: getattr(req, c) for c in RequestOut.model_fields if hasattr(req, c)},
        "member_name": f"{member.first_name} {member.last_name}",
        "plan_name": ms.plan.name,
        "membership_end": ms.end_date,
    }


@router.get("", response_model=list[RequestOut], dependencies=[require_roles(*STAFF)])
async def list_requests(
    user: CurrentUser,
    db: DB,
    branch_id: int | None = None,
    request_status: RequestStatus | None = Query(None, alias="status"),
) -> list[dict]:
    stmt = scope_to_branches(
        select(MembershipRequest).order_by(MembershipRequest.created_at.desc()),
        MembershipRequest.branch_id,
        user,
        branch_id,
    )
    if request_status is not None:
        stmt = stmt.where(MembershipRequest.status == request_status)
    return [await _out(db, r) for r in await db.scalars(stmt.limit(200))]


@router.post(
    "/{request_id}/decision", response_model=RequestOut, dependencies=[require_roles(*MANAGEMENT)]
)
async def decide(request_id: int, body: DecisionIn, user: CurrentUser, db: DB) -> dict:
    """Approve or reject. Approving a freeze pauses the membership and moves its end date."""
    req = await get_scoped_or_404(db, MembershipRequest, request_id, user)
    await db.refresh(req, with_for_update=True)
    if req.status != RequestStatus.PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT, "This request has already been decided.")
    if req.created_by == user.id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "A request you logged must be decided by someone else."
        )
    req.status = RequestStatus.APPROVED if body.approve else RequestStatus.REJECTED
    req.decided_by = user.id
    req.decided_at = utcnow()
    req.decision_note = body.note
    if body.approve:
        await apply_freeze(db, req)
    audit(db, user, f"{req.kind}_{req.status}", "membership_request", req.id)
    await db.commit()
    return await _out(db, req)

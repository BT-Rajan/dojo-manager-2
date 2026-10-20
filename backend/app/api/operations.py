"""Front-desk operations: renewal follow-ups, incident reports and the complaint log."""

from datetime import date

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.deps import (
    ANY_ROLE,
    DB,
    STAFF,
    CurrentUser,
    Page,
    apply_updates,
    ensure_branch,
    ensure_exists,
    get_or_404,
    get_scoped_or_404,
    require_roles,
    scope_to_branches,
    utcnow,
)
from app.models import (
    Branch,
    CaseStatus,
    ClassSession,
    Complaint,
    Incident,
    IncidentType,
    Member,
    Membership,
    RenewalFollowUp,
    User,
)
from app.schemas.progress import (
    ComplaintIn,
    ComplaintOut,
    ComplaintUpdate,
    FollowUpIn,
    FollowUpOut,
    IncidentIn,
    IncidentOut,
    IncidentUpdate,
)
from app.services.audit import audit

router = APIRouter(tags=["operations"])
any_role = [require_roles(*ANY_ROLE)]
staff = [require_roles(*STAFF)]


async def _member_in_branch(db: DB, user, member_id: int | None, branch_id: int) -> None:
    if member_id is None:
        return
    m = await get_scoped_or_404(db, Member, member_id, user)
    if m.branch_id != branch_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Member is at another branch")


# ---------------------------------------------------------------- renewal follow-ups
@router.get("/followups", response_model=list[FollowUpOut], dependencies=staff)
async def list_followups(
    user: CurrentUser,
    db: DB,
    page: Page,
    branch_id: int | None = None,
    member_id: int | None = None,
) -> list[RenewalFollowUp]:
    stmt = scope_to_branches(select(RenewalFollowUp), RenewalFollowUp.branch_id, user, branch_id)
    if member_id is not None:
        stmt = stmt.where(RenewalFollowUp.member_id == member_id)
    return list(await db.scalars(page.apply(stmt.order_by(RenewalFollowUp.contacted_at.desc()))))


@router.post("/followups", response_model=FollowUpOut, status_code=201, dependencies=staff)
async def record_followup(body: FollowUpIn, user: CurrentUser, db: DB) -> RenewalFollowUp:
    member = await get_scoped_or_404(db, Member, body.member_id, user)
    if body.membership_id is not None:
        ms = await get_or_404(db, Membership, body.membership_id)
        if ms.member_id != member.id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Membership/member mismatch")
    fu = RenewalFollowUp(
        **body.model_dump(), branch_id=member.branch_id, contacted_at=utcnow(), contacted_by=user.id
    )
    db.add(fu)
    await db.commit()
    return fu


# ---------------------------------------------------------------- incidents
@router.get("/incidents", response_model=list[IncidentOut], dependencies=staff)
async def list_incidents(
    user: CurrentUser,
    db: DB,
    page: Page,
    branch_id: int | None = None,
    status: CaseStatus | None = None,
    type: IncidentType | None = None,
) -> list[Incident]:
    stmt = scope_to_branches(select(Incident), Incident.branch_id, user, branch_id)
    if status is not None:
        stmt = stmt.where(Incident.status == status)
    if type is not None:
        stmt = stmt.where(Incident.type == type)
    return list(await db.scalars(page.apply(stmt.order_by(Incident.occurred_at.desc()))))


@router.post("/incidents", response_model=IncidentOut, status_code=201, dependencies=any_role)
async def report_incident(body: IncidentIn, user: CurrentUser, db: DB) -> Incident:
    """Any staff member, instructors included, can report an incident."""
    ensure_branch(user, body.branch_id)
    if body.occurred_at > utcnow():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "occurred_at is in the future")
    await _member_in_branch(db, user, body.member_id, body.branch_id)
    if body.session_id is not None:
        sess = await get_scoped_or_404(db, ClassSession, body.session_id, user)
        if sess.branch_id != body.branch_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Class is at another branch")
    branch = await get_or_404(db, Branch, body.branch_id)
    incident = Incident(**body.model_dump(), reported_by=user.id)
    db.add(incident)
    await db.flush()
    incident.ref_no = f"INC-{branch.code}-{incident.id:05d}"
    await db.commit()
    return incident


@router.get("/incidents/{incident_id}", response_model=IncidentOut, dependencies=staff)
async def get_incident(incident_id: int, user: CurrentUser, db: DB) -> Incident:
    return await get_scoped_or_404(db, Incident, incident_id, user)


@router.patch("/incidents/{incident_id}", response_model=IncidentOut, dependencies=staff)
async def update_incident(
    incident_id: int, body: IncidentUpdate, user: CurrentUser, db: DB
) -> Incident:
    incident = await get_scoped_or_404(db, Incident, incident_id, user)
    data = body.model_dump(exclude_unset=True)
    if data.pop("reported_to_manager", None) and incident.reported_to_manager_at is None:
        incident.reported_to_manager_at = utcnow()
    if data.get("status") == CaseStatus.CLOSED and incident.status != CaseStatus.CLOSED:
        if not (data.get("action_taken") or incident.action_taken):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Record the action taken")
        incident.closed_at = utcnow()
    elif data.get("status") == CaseStatus.OPEN:
        incident.closed_at = None
    apply_updates(incident, data)
    audit(db, user, "update", "incident", incident.id, fields=sorted(data))
    await db.commit()
    return incident


# ---------------------------------------------------------------- complaints
@router.get("/complaints", response_model=list[ComplaintOut], dependencies=staff)
async def list_complaints(
    user: CurrentUser,
    db: DB,
    page: Page,
    branch_id: int | None = None,
    status: CaseStatus | None = None,
) -> list[Complaint]:
    stmt = scope_to_branches(select(Complaint), Complaint.branch_id, user, branch_id)
    if status is not None:
        stmt = stmt.where(Complaint.status == status)
    order = (Complaint.received_on.desc(), Complaint.id.desc())
    return list(await db.scalars(page.apply(stmt.order_by(*order))))


@router.post("/complaints", response_model=ComplaintOut, status_code=201, dependencies=staff)
async def log_complaint(body: ComplaintIn, user: CurrentUser, db: DB) -> Complaint:
    ensure_branch(user, body.branch_id)
    await _member_in_branch(db, user, body.member_id, body.branch_id)
    branch = await get_or_404(db, Branch, body.branch_id)
    data = body.model_dump()
    data["received_on"] = data["received_on"] or date.today()
    complaint = Complaint(**data, handled_by=user.id)
    db.add(complaint)
    await db.flush()
    complaint.ref_no = f"CMP-{branch.code}-{complaint.id:05d}"
    await db.commit()
    return complaint


@router.patch("/complaints/{complaint_id}", response_model=ComplaintOut, dependencies=staff)
async def update_complaint(
    complaint_id: int, body: ComplaintUpdate, user: CurrentUser, db: DB
) -> Complaint:
    complaint = await get_scoped_or_404(db, Complaint, complaint_id, user)
    data = body.model_dump(exclude_unset=True)
    await ensure_exists(db, User, data.get("handled_by"), "handled_by")
    if data.get("status") == CaseStatus.CLOSED and complaint.status != CaseStatus.CLOSED:
        if not (data.get("outcome") or complaint.outcome):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Record the outcome")
        complaint.closed_on = date.today()
    elif data.get("status") == CaseStatus.OPEN:
        complaint.closed_on = None
    apply_updates(complaint, data)
    await db.commit()
    return complaint

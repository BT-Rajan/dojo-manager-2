from datetime import date

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import or_, select

from app.core.deps import (
    DB,
    STAFF,
    CurrentUser,
    Page,
    apply_updates,
    ensure_branch,
    ensure_exists,
    get_or_404,
    get_scoped_or_404,
    like_pattern,
    require_roles,
    scope_to_branches,
)
from app.models import Branch, ClassSession, Lead, LeadStatus, Member, Program, SessionStatus, User
from app.schemas.classes import BookTrialIn, ConvertLeadIn, LeadIn, LeadOut, LeadUpdate
from app.schemas.dojo import MemberOut

router = APIRouter(prefix="/leads", tags=["leads"], dependencies=[require_roles(*STAFF)])

CLOSED = (LeadStatus.CONVERTED, LeadStatus.LOST)


@router.get("", response_model=list[LeadOut])
async def list_leads(
    user: CurrentUser,
    db: DB,
    page: Page,
    branch_id: int | None = None,
    status: LeadStatus | None = None,
    open_only: bool = False,
    q: str | None = None,
) -> list[Lead]:
    stmt = scope_to_branches(select(Lead), Lead.branch_id, user, branch_id)
    if status is not None:
        stmt = stmt.where(Lead.status == status)
    if open_only:
        stmt = stmt.where(Lead.status.not_in(CLOSED))
    if q and (term := q.strip()[:75]):
        pat = like_pattern(term)
        stmt = stmt.where(or_(Lead.full_name.like(pat), Lead.phone.like(pat)))
    stmt = stmt.order_by(Lead.next_action_date.is_(None), Lead.next_action_date, Lead.id.desc())
    return list(await db.scalars(page.apply(stmt)))


@router.post("", response_model=LeadOut, status_code=201)
async def create_lead(body: LeadIn, user: CurrentUser, db: DB) -> Lead:
    ensure_branch(user, body.branch_id)
    await ensure_exists(db, Program, body.program_id, "program_id")
    await ensure_exists(db, User, body.owner_user_id, "owner_user_id")
    lead = Lead(**body.model_dump())
    lead.owner_user_id = lead.owner_user_id or user.id
    db.add(lead)
    await db.commit()
    return lead


@router.get("/{lead_id}", response_model=LeadOut)
async def get_lead(lead_id: int, user: CurrentUser, db: DB) -> Lead:
    return await get_scoped_or_404(db, Lead, lead_id, user)


@router.patch("/{lead_id}", response_model=LeadOut)
async def update_lead(lead_id: int, body: LeadUpdate, user: CurrentUser, db: DB) -> Lead:
    lead = await get_scoped_or_404(db, Lead, lead_id, user)
    data = body.model_dump(exclude_unset=True)
    if data.get("status") == LeadStatus.CONVERTED:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Use the convert endpoint")
    if data.get("status") == LeadStatus.LOST and not (data.get("lost_reason") or lead.lost_reason):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "lost_reason is required")
    await ensure_exists(db, Program, data.get("program_id"), "program_id")
    await ensure_exists(db, User, data.get("owner_user_id"), "owner_user_id")
    apply_updates(lead, data)
    await db.commit()
    return lead


@router.post("/{lead_id}/book-trial", response_model=LeadOut)
async def book_trial(lead_id: int, body: BookTrialIn, user: CurrentUser, db: DB) -> Lead:
    lead = await get_scoped_or_404(db, Lead, lead_id, user)
    if lead.status in CLOSED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Lead is closed")
    sess = await get_scoped_or_404(db, ClassSession, body.session_id, user)
    if sess.branch_id != lead.branch_id or sess.status != SessionStatus.SCHEDULED:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Not a bookable class")
    if sess.session_date < date.today():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Class is in the past")
    lead.trial_session_id = sess.id
    lead.status = LeadStatus.TRIAL_BOOKED
    lead.next_action = "Confirm trial attendance"
    lead.next_action_date = sess.session_date
    await db.commit()
    return lead


@router.post("/{lead_id}/convert", response_model=MemberOut, status_code=201)
async def convert_lead(lead_id: int, body: ConvertLeadIn, user: CurrentUser, db: DB) -> Member:
    """Register the lead as a member. Their membership is added separately."""
    lead = await get_scoped_or_404(db, Lead, lead_id, user)
    if lead.status in CLOSED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Lead is closed")
    branch = await get_or_404(db, Branch, lead.branch_id)
    member = Member(
        branch_id=lead.branch_id,
        first_name=body.first_name,
        last_name=body.last_name,
        date_of_birth=body.date_of_birth,
        phone=lead.phone,
        email=lead.email,
        joined_on=date.today(),
        notes=lead.notes,
    )
    db.add(member)
    await db.flush()
    member.member_no = f"{branch.code}-{member.id:05d}"
    lead.status = LeadStatus.CONVERTED
    lead.converted_member_id = member.id
    lead.next_action = None
    lead.next_action_date = None
    await db.commit()
    await db.refresh(member, ["belt_rank"])
    return member

from datetime import date

from fastapi import APIRouter, status
from sqlalchemy import or_, select

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
    like_pattern,
    require_roles,
    scope_to_branches,
)
from app.models import BeltRank, Branch, Member, Membership, MemberStatus
from app.schemas.dojo import MemberIn, MemberOut, MembershipOut, MemberUpdate

router = APIRouter(prefix="/members", tags=["members"])


@router.get("", response_model=list[MemberOut], dependencies=[require_roles(*ANY_ROLE)])
async def list_members(
    user: CurrentUser,
    db: DB,
    page: Page,
    branch_id: int | None = None,
    q: str | None = None,
    status: MemberStatus | None = None,
    belt_rank_id: int | None = None,
) -> list[Member]:
    stmt = scope_to_branches(select(Member), Member.branch_id, user, branch_id)
    if q and (term := q.strip()[:75]):
        pat = like_pattern(term)
        stmt = stmt.where(
            or_(
                Member.first_name.like(pat),
                Member.last_name.like(pat),
                Member.phone.like(pat),
                Member.member_no.like(pat),
                Member.civil_id.like(pat),
            )
        )
    if status is not None:
        stmt = stmt.where(Member.status == status)
    if belt_rank_id is not None:
        stmt = stmt.where(Member.belt_rank_id == belt_rank_id)
    stmt = stmt.order_by(Member.last_name, Member.first_name, Member.id)
    return list(await db.scalars(page.apply(stmt)))


@router.post(
    "",
    response_model=MemberOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_roles(*STAFF)],
)
async def create_member(body: MemberIn, user: CurrentUser, db: DB) -> Member:
    ensure_branch(user, body.branch_id)
    branch = await get_or_404(db, Branch, body.branch_id)
    await ensure_exists(db, BeltRank, body.belt_rank_id, "belt_rank_id")
    data = body.model_dump()
    data["joined_on"] = data["joined_on"] or date.today()
    member = Member(**data)
    db.add(member)
    await db.flush()
    member.member_no = f"{branch.code}-{member.id:05d}"
    await db.commit()
    await db.refresh(member, ["belt_rank"])
    return member


@router.get("/{member_id}", response_model=MemberOut, dependencies=[require_roles(*ANY_ROLE)])
async def get_member(member_id: int, user: CurrentUser, db: DB) -> Member:
    return await get_scoped_or_404(db, Member, member_id, user)


@router.patch("/{member_id}", response_model=MemberOut, dependencies=[require_roles(*STAFF)])
async def update_member(member_id: int, body: MemberUpdate, user: CurrentUser, db: DB) -> Member:
    member = await get_scoped_or_404(db, Member, member_id, user)
    data = body.model_dump(exclude_unset=True)
    if "branch_id" in data:
        ensure_branch(user, data["branch_id"])
        await get_or_404(db, Branch, data["branch_id"])
    await ensure_exists(db, BeltRank, data.get("belt_rank_id"), "belt_rank_id")
    apply_updates(member, data)
    await db.commit()
    await db.refresh(member, ["belt_rank"])
    return member


@router.get(
    "/{member_id}/memberships",
    response_model=list[MembershipOut],
    dependencies=[require_roles(*ANY_ROLE)],
)
async def member_memberships(member_id: int, user: CurrentUser, db: DB) -> list[Membership]:
    await get_scoped_or_404(db, Member, member_id, user)
    stmt = (
        select(Membership)
        .where(Membership.member_id == member_id)
        .order_by(Membership.end_date.desc())
    )
    return list(await db.scalars(stmt))

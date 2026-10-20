from typing import Literal

from fastapi import APIRouter, Response, status
from sqlalchemy import case, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import today as academy_today
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
from app.models import BeltRank, Branch, Member, Membership, MembershipStatus, MemberStatus
from app.schemas.dojo import MemberIn, MemberOut, MembershipOut, MemberUpdate, Standing

router = APIRouter(prefix="/members", tags=["members"])


def standing_expr():
    """Where a member stands today (academy time), derived from their memberships:
    inactive/frozen enrolment wins; otherwise active if a membership covers today, lapsed if
    they have had one, new if they never have."""
    on = academy_today()
    covering = (
        Membership.member_id == Member.id,
        Membership.start_date <= on,
        Membership.end_date >= on,
    )
    current = exists().where(*covering, Membership.status == MembershipStatus.ACTIVE)
    frozen = exists().where(*covering, Membership.status == MembershipStatus.FROZEN)
    had_any = exists().where(
        Membership.member_id == Member.id, Membership.status != MembershipStatus.CANCELLED
    )
    return case(
        (Member.status == MemberStatus.INACTIVE, "inactive"),
        (Member.status == MemberStatus.FROZEN, "frozen"),
        (current, "active"),
        (frozen, "frozen"),
        (had_any, "lapsed"),
        else_="new",
    )


async def with_standing(db: AsyncSession, member: Member) -> Member:
    member.standing = await db.scalar(select(standing_expr()).where(Member.id == member.id))
    return member


SortKey = Literal["name", "member_no", "joined_on", "age", "belt", "standing"]


@router.get("", response_model=list[MemberOut], dependencies=[require_roles(*ANY_ROLE)])
async def list_members(
    response: Response,
    user: CurrentUser,
    db: DB,
    page: Page,
    branch_id: int | None = None,
    q: str | None = None,
    standing: Standing | None = None,
    status: MemberStatus | None = None,
    belt_rank_id: int | None = None,
    sort: SortKey = "name",
    order: Literal["asc", "desc"] = "asc",
) -> list[Member]:
    """Members page. The total matching count is returned in ``X-Total-Count``."""
    st = standing_expr()
    stmt = scope_to_branches(
        select(Member, st.label("standing")), Member.branch_id, user, branch_id
    )
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
    if standing is not None:
        stmt = stmt.where(st == standing)
    if status is not None:
        stmt = stmt.where(Member.status == status)
    if belt_rank_id is not None:
        stmt = stmt.where(Member.belt_rank_id == belt_rank_id)

    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    response.headers["X-Total-Count"] = str(total)

    desc = order == "desc"
    name = (Member.last_name, Member.first_name)
    nulls_last: list = []  # members without a belt / birth date sort after the rest
    if sort == "belt":
        stmt = stmt.outerjoin(BeltRank, BeltRank.id == Member.belt_rank_id)
        nulls_last = [BeltRank.sort_order.is_(None)]
        keys = [BeltRank.sort_order, Member.stripes]
    elif sort == "age":
        nulls_last = [Member.date_of_birth.is_(None)]
        keys = [Member.date_of_birth]
        desc = not desc  # older members have earlier birth dates
    else:
        keys = {
            "name": list(name),
            "member_no": [Member.id],  # numbers are generated in id order
            "joined_on": [Member.joined_on],
            "standing": [st],
        }[sort]
    stmt = stmt.order_by(
        *nulls_last, *(k.desc() if desc else k.asc() for k in keys), *name, Member.id
    )
    members = []
    for m, standing_value in (await db.execute(page.apply(stmt))).all():
        m.standing = standing_value
        members.append(m)
    return members


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
    data["joined_on"] = data["joined_on"] or academy_today()
    member = Member(**data)
    db.add(member)
    await db.flush()
    member.member_no = f"{branch.code}-{member.id:05d}"
    await db.commit()
    await db.refresh(member, ["belt_rank"])
    return await with_standing(db, member)


@router.get("/{member_id}", response_model=MemberOut, dependencies=[require_roles(*ANY_ROLE)])
async def get_member(member_id: int, user: CurrentUser, db: DB) -> Member:
    return await with_standing(db, await get_scoped_or_404(db, Member, member_id, user))


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
    return await with_standing(db, member)


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

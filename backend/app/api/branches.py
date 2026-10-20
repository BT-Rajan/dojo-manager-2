from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.deps import (
    ANY_ROLE,
    DB,
    MANAGEMENT,
    CurrentUser,
    ensure_branch,
    get_or_404,
    require_roles,
)
from app.models.org import Branch, Role
from app.schemas.org import BranchIn, BranchOut, BranchUpdate

router = APIRouter(prefix="/branches", tags=["branches"], dependencies=[require_roles(*ANY_ROLE)])


@router.get("", response_model=list[BranchOut])
async def list_branches(user: CurrentUser, db: DB) -> list[Branch]:
    """Branches the caller may work in (all of them for owners and managers)."""
    stmt = select(Branch).order_by(Branch.name)
    if not user.sees_all_branches:
        stmt = stmt.where(Branch.id.in_(user.branch_ids or [-1]))
    return list(await db.scalars(stmt))


@router.get("/{branch_id}", response_model=BranchOut)
async def get_branch(branch_id: int, user: CurrentUser, db: DB) -> Branch:
    ensure_branch(user, branch_id)
    return await get_or_404(db, Branch, branch_id)


@router.post(
    "",
    response_model=BranchOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_roles(Role.OWNER)],
)
async def create_branch(body: BranchIn, db: DB) -> Branch:
    branch = Branch(**body.model_dump())
    db.add(branch)
    try:
        await db.commit()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Branch name or code exists") from None
    return branch


@router.patch("/{branch_id}", response_model=BranchOut, dependencies=[require_roles(*MANAGEMENT)])
async def update_branch(branch_id: int, body: BranchUpdate, db: DB) -> Branch:
    branch = await get_or_404(db, Branch, branch_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(branch, k, v)
    try:
        await db.commit()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Branch name already exists") from None
    return branch

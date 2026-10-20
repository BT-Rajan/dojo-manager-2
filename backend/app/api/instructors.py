from fastapi import APIRouter, status
from sqlalchemy import select

from app.core.deps import (
    ANY_ROLE,
    DB,
    STAFF,
    CurrentUser,
    apply_updates,
    ensure_branch,
    ensure_exists,
    get_scoped_or_404,
    require_roles,
    scope_to_branches,
)
from app.models import BeltRank, Instructor, User
from app.schemas.dojo import InstructorIn, InstructorOut, InstructorUpdate

router = APIRouter(prefix="/instructors", tags=["instructors"])


@router.get("", response_model=list[InstructorOut], dependencies=[require_roles(*ANY_ROLE)])
async def list_instructors(
    user: CurrentUser, db: DB, branch_id: int | None = None, active: bool | None = None
) -> list[Instructor]:
    stmt = scope_to_branches(
        select(Instructor).order_by(Instructor.full_name), Instructor.branch_id, user, branch_id
    )
    if active is not None:
        stmt = stmt.where(Instructor.is_active == active)
    return list(await db.scalars(stmt))


@router.get(
    "/{instructor_id}", response_model=InstructorOut, dependencies=[require_roles(*ANY_ROLE)]
)
async def get_instructor(instructor_id: int, user: CurrentUser, db: DB) -> Instructor:
    return await get_scoped_or_404(db, Instructor, instructor_id, user)


@router.post(
    "",
    response_model=InstructorOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_roles(*STAFF)],
)
async def create_instructor(body: InstructorIn, user: CurrentUser, db: DB) -> Instructor:
    ensure_branch(user, body.branch_id)
    await ensure_exists(db, BeltRank, body.belt_rank_id, "belt_rank_id")
    await ensure_exists(db, User, body.user_id, "user_id")
    instructor = Instructor(**body.model_dump())
    db.add(instructor)
    await db.commit()
    return instructor


@router.patch(
    "/{instructor_id}", response_model=InstructorOut, dependencies=[require_roles(*STAFF)]
)
async def update_instructor(
    instructor_id: int, body: InstructorUpdate, user: CurrentUser, db: DB
) -> Instructor:
    instructor = await get_scoped_or_404(db, Instructor, instructor_id, user)
    data = body.model_dump(exclude_unset=True)
    if "branch_id" in data:
        ensure_branch(user, data["branch_id"])
    await ensure_exists(db, BeltRank, data.get("belt_rank_id"), "belt_rank_id")
    await ensure_exists(db, User, data.get("user_id"), "user_id")
    apply_updates(instructor, data)
    await db.commit()
    return instructor

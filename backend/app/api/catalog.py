"""Academy-wide reference data: programmes, belt ranks and membership plans."""

from fastapi import APIRouter, Query, status
from sqlalchemy import or_, select

from app.core.deps import (
    ANY_ROLE,
    DB,
    MANAGEMENT,
    CurrentUser,
    apply_updates,
    ensure_branch,
    ensure_exists,
    get_or_404,
    require_roles,
)
from app.models import BeltRank, Branch, MembershipPlan, Program
from app.schemas.dojo import (
    BeltIn,
    BeltOut,
    BeltUpdate,
    PlanIn,
    PlanOut,
    PlanUpdate,
    ProgramIn,
    ProgramOut,
    ProgramUpdate,
)

router = APIRouter(tags=["catalog"], dependencies=[require_roles(*ANY_ROLE)])
manage = [require_roles(*MANAGEMENT)]


# ---------------------------------------------------------------- programs
@router.get("/programs", response_model=list[ProgramOut])
async def list_programs(db: DB, active: bool | None = None) -> list[Program]:
    stmt = select(Program).order_by(Program.name)
    if active is not None:
        stmt = stmt.where(Program.is_active == active)
    return list(await db.scalars(stmt))


@router.post("/programs", response_model=ProgramOut, status_code=201, dependencies=manage)
async def create_program(body: ProgramIn, db: DB) -> Program:
    program = Program(**body.model_dump())
    db.add(program)
    await db.commit()
    return program


@router.patch("/programs/{program_id}", response_model=ProgramOut, dependencies=manage)
async def update_program(program_id: int, body: ProgramUpdate, db: DB) -> Program:
    program = await get_or_404(db, Program, program_id)
    apply_updates(program, body.model_dump(exclude_unset=True))
    await db.commit()
    return program


# ---------------------------------------------------------------- belts
@router.get("/belts", response_model=list[BeltOut])
async def list_belts(db: DB) -> list[BeltRank]:
    return list(await db.scalars(select(BeltRank).order_by(BeltRank.sort_order)))


@router.post("/belts", response_model=BeltOut, status_code=201, dependencies=manage)
async def create_belt(body: BeltIn, db: DB) -> BeltRank:
    belt = BeltRank(**body.model_dump())
    db.add(belt)
    await db.commit()
    return belt


@router.patch("/belts/{belt_id}", response_model=BeltOut, dependencies=manage)
async def update_belt(belt_id: int, body: BeltUpdate, db: DB) -> BeltRank:
    belt = await get_or_404(db, BeltRank, belt_id)
    apply_updates(belt, body.model_dump(exclude_unset=True))
    await db.commit()
    return belt


# ---------------------------------------------------------------- membership plans
@router.get("/plans", response_model=list[PlanOut])
async def list_plans(
    user: CurrentUser, db: DB, branch_id: int | None = Query(None), active: bool | None = None
) -> list[MembershipPlan]:
    """Plans offered at a branch: academy-wide plans plus that branch's own plans."""
    stmt = select(MembershipPlan).order_by(MembershipPlan.name)
    if branch_id is not None:
        ensure_branch(user, branch_id)
        stmt = stmt.where(
            or_(MembershipPlan.branch_id.is_(None), MembershipPlan.branch_id == branch_id)
        )
    elif not user.sees_all_branches:
        stmt = stmt.where(
            or_(
                MembershipPlan.branch_id.is_(None),
                MembershipPlan.branch_id.in_(user.branch_ids or [-1]),
            )
        )
    if active is not None:
        stmt = stmt.where(MembershipPlan.is_active == active)
    return list(await db.scalars(stmt))


@router.post(
    "/plans", response_model=PlanOut, status_code=status.HTTP_201_CREATED, dependencies=manage
)
async def create_plan(body: PlanIn, db: DB) -> MembershipPlan:
    await ensure_exists(db, Branch, body.branch_id, "branch_id")
    await ensure_exists(db, Program, body.program_id, "program_id")
    plan = MembershipPlan(**body.model_dump())
    db.add(plan)
    await db.commit()
    return plan


@router.patch("/plans/{plan_id}", response_model=PlanOut, dependencies=manage)
async def update_plan(plan_id: int, body: PlanUpdate, db: DB) -> MembershipPlan:
    plan = await get_or_404(db, MembershipPlan, plan_id)
    data = body.model_dump(exclude_unset=True)
    await ensure_exists(db, Program, data.get("program_id"), "program_id")
    apply_updates(plan, data)
    await db.commit()
    return plan

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.core.deps import (
    ANY_ROLE,
    DB,
    MANAGEMENT,
    STAFF,
    CurrentUser,
    apply_updates,
    ensure_branch,
    ensure_exists,
    get_scoped_or_404,
    require_roles,
    scope_to_branches,
)
from app.core.security import hash_password
from app.models import BeltRank, Branch, Instructor, Role, User, UserSession
from app.schemas.coach import (
    PortalAccessOut,
    PortalAccountIn,
    PortalAccountUpdate,
    PortalPasswordIn,
)
from app.schemas.dojo import InstructorIn, InstructorOut, InstructorUpdate
from app.services.audit import audit

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


# ---------------------------------------------------------------- coach portal logins
def _access(inst: Instructor, login: User | None) -> dict:
    return {
        "instructor_id": inst.id,
        "full_name": inst.full_name,
        "branch_id": inst.branch_id,
        "is_active": inst.is_active,
        "user_id": login.id if login else None,
        "username": login.username if login else None,
        "user_active": login.is_active if login else None,
        "last_login_at": login.last_login_at if login else None,
    }


@router.get(
    "/portal-access",
    response_model=list[PortalAccessOut],
    dependencies=[require_roles(*MANAGEMENT)],
)
async def list_portal_access(user: CurrentUser, db: DB, branch_id: int | None = None) -> list:
    """Each coach with their portal login, if they have one."""
    stmt = scope_to_branches(
        select(Instructor, User)
        .outerjoin(User, User.id == Instructor.user_id)
        .order_by(Instructor.full_name),
        Instructor.branch_id,
        user,
        branch_id,
    )
    return [_access(inst, login) for inst, login in (await db.execute(stmt)).all()]


async def _portal_login(db: DB, inst: Instructor) -> User:
    login = await db.get(User, inst.user_id) if inst.user_id else None
    if login is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This coach has no portal login")
    return login


@router.post(
    "/{instructor_id}/portal-account",
    response_model=PortalAccessOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_roles(*MANAGEMENT)],
)
async def create_portal_account(
    instructor_id: int, body: PortalAccountIn, actor: CurrentUser, db: DB
) -> dict:
    """Give a coach a portal login: an instructor-role user for the coach's branch."""
    inst = await get_scoped_or_404(db, Instructor, instructor_id, actor)
    if inst.user_id is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This coach already has a portal login")
    login = User(
        username=body.username,
        full_name=inst.full_name,
        email=body.email,
        role=Role.INSTRUCTOR,
        password_hash=await hash_password(body.password),
        branches=[await db.get(Branch, inst.branch_id)],
    )
    db.add(login)
    try:
        await db.flush()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Username or email already exists") from None
    inst.user_id = login.id
    audit(db, actor, "create_portal_login", "instructor", inst.id, user_id=login.id)
    await db.commit()
    return _access(inst, login)


@router.patch(
    "/{instructor_id}/portal-account",
    response_model=PortalAccessOut,
    dependencies=[require_roles(*MANAGEMENT)],
)
async def update_portal_account(
    instructor_id: int, body: PortalAccountUpdate, actor: CurrentUser, db: DB
) -> dict:
    """Turn a coach's portal login on or off. Turning it off signs the coach out."""
    inst = await get_scoped_or_404(db, Instructor, instructor_id, actor)
    login = await _portal_login(db, inst)
    if login.id == actor.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot disable yourself")
    login.is_active = body.is_active
    if not body.is_active:
        await db.execute(delete(UserSession).where(UserSession.user_id == login.id))
    audit(db, actor, "update_portal_login", "instructor", inst.id, is_active=body.is_active)
    await db.commit()
    return _access(inst, login)


@router.post(
    "/{instructor_id}/portal-account/reset-password",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_roles(*MANAGEMENT)],
)
async def reset_portal_password(
    instructor_id: int, body: PortalPasswordIn, actor: CurrentUser, db: DB
) -> None:
    inst = await get_scoped_or_404(db, Instructor, instructor_id, actor)
    login = await _portal_login(db, inst)
    if login.role != Role.INSTRUCTOR:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only instructor logins can be reset here")
    login.password_hash = await hash_password(body.password)
    await db.execute(delete(UserSession).where(UserSession.user_id == login.id))
    audit(db, actor, "reset_portal_password", "instructor", inst.id, user_id=login.id)
    await db.commit()


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
    if "branch_id" in data and instructor.user_id:
        # A coach's portal login follows them to their new branch.
        login = await db.get(User, instructor.user_id)
        if login is not None and login.role == Role.INSTRUCTOR:
            login.branches = [await db.get(Branch, instructor.branch_id)]
    await db.commit()
    return instructor

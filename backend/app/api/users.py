from fastapi import APIRouter, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import DB, CurrentUser, Page, get_or_404, require_roles
from app.core.security import hash_password
from app.models.org import Branch, Role, User, UserSession
from app.schemas.org import PasswordReset, UserCreate, UserOut, UserUpdate
from app.services.audit import audit

router = APIRouter(prefix="/users", tags=["users"], dependencies=[require_roles(Role.OWNER)])


async def _load_branches(db: AsyncSession, ids: list[int]) -> list[Branch]:
    ids = sorted(set(ids))
    if not ids:
        return []
    branches = list(await db.scalars(select(Branch).where(Branch.id.in_(ids))))
    if len(branches) != len(ids):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown branch id")
    return branches


@router.get("", response_model=list[UserOut])
async def list_users(db: DB, page: Page) -> list[User]:
    return list(await db.scalars(page.apply(select(User).order_by(User.full_name))))


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(body: UserCreate, actor: CurrentUser, db: DB) -> User:
    user = User(
        username=body.username,
        full_name=body.full_name,
        email=body.email,
        role=body.role,
        password_hash=await hash_password(body.password),
        branches=await _load_branches(db, body.branch_ids),
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Username or email already exists") from None
    audit(db, actor, "create", "user", user.id, role=user.role)
    await db.commit()
    return user


@router.get("/{user_id}", response_model=UserOut)
async def get_user(user_id: int, db: DB) -> User:
    return await get_or_404(db, User, user_id)


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(user_id: int, body: UserUpdate, actor: CurrentUser, db: DB) -> User:
    user = await get_or_404(db, User, user_id)
    data = body.model_dump(exclude_unset=True)
    demoting = data.get("role", user.role) != Role.OWNER or data.get("is_active") is False
    if user.id == actor.id and demoting:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot demote or disable yourself")
    branch_ids = data.pop("branch_ids", None)
    if branch_ids is not None:
        user.branches = await _load_branches(db, branch_ids)
    for k, v in data.items():
        setattr(user, k, v)
    if data.get("is_active") is False:
        await db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    try:
        await db.flush()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already exists") from None
    changed = sorted(data) + (["branches"] if branch_ids is not None else [])
    audit(db, actor, "update", "user", user.id, fields=changed)
    await db.commit()
    return user


@router.post("/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(user_id: int, body: PasswordReset, actor: CurrentUser, db: DB) -> None:
    user = await get_or_404(db, User, user_id)
    user.password_hash = await hash_password(body.password)
    await db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    audit(db, actor, "reset_password", "user", user.id)
    await db.commit()

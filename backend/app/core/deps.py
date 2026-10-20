from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Query, Request, status
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import hash_token
from app.models.org import Role, User, UserSession

DB = Annotated[AsyncSession, Depends(get_db)]


def utcnow() -> datetime:
    """Naive UTC timestamp (MySQL DATETIME has no time zone)."""
    return datetime.now(UTC).replace(tzinfo=None)


async def get_current_user(request: Request, db: DB) -> User:
    token = request.cookies.get(get_settings().session_cookie_name)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    row = await db.scalar(select(UserSession).where(UserSession.token_hash == hash_token(token)))
    if row is None or row.expires_at <= utcnow() or not row.user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
    request.state.session_id = row.id
    return row.user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: Role):
    allowed = frozenset(roles)

    async def _check(user: CurrentUser) -> User:
        if user.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
        return user

    return Depends(_check)


# Common role groups
STAFF = (Role.OWNER, Role.MANAGER, Role.BRANCH_ADMIN)
ANY_ROLE = (Role.OWNER, Role.MANAGER, Role.BRANCH_ADMIN, Role.INSTRUCTOR)
MANAGEMENT = (Role.OWNER, Role.MANAGER)


def can_access_branch(user: User, branch_id: int | None) -> bool:
    return user.sees_all_branches or (branch_id is not None and branch_id in user.branch_ids)


def ensure_branch(user: User, branch_id: int | None) -> None:
    """Branch isolation: staff only ever touch data for branches they are assigned to."""
    if not can_access_branch(user, branch_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No access to this branch")


def scope_to_branches(
    stmt: Select[Any], column: InstrumentedAttribute[Any], user: User, branch_id: int | None
) -> Select[Any]:
    """Filter ``stmt`` to ``branch_id`` (after an access check) or to the user's branches."""
    if branch_id is not None:
        ensure_branch(user, branch_id)
        return stmt.where(column == branch_id)
    if user.sees_all_branches:
        return stmt
    return stmt.where(column.in_(user.branch_ids or [-1]))


async def get_or_404(db: AsyncSession, model: type, obj_id: int, *, options: Iterable = ()):
    obj = await db.get(model, obj_id, options=list(options))
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{model.__name__} not found")
    return obj


async def get_scoped_or_404(db: AsyncSession, model: type, obj_id: int, user: User, *, options=()):
    """Fetch a branch-owned row; rows in other branches look exactly like missing rows."""
    obj = await db.get(model, obj_id, options=list(options))
    if obj is None or not can_access_branch(user, obj.branch_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{model.__name__} not found")
    return obj


class Pagination:
    def __init__(
        self,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> None:
        self.limit = limit
        self.offset = offset

    def apply(self, stmt: Select[Any]) -> Select[Any]:
        return stmt.limit(self.limit).offset(self.offset)


Page = Annotated[Pagination, Depends()]


async def ensure_exists(db: AsyncSession, model: type, obj_id: int | None, field: str) -> None:
    """Validate a foreign key from a request body (422 rather than a database error)."""
    if obj_id is not None and await db.get(model, obj_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unknown {field}")


def apply_updates(obj: Any, data: dict[str, Any]) -> None:
    for k, v in data.items():
        setattr(obj, k, v)


def like_pattern(term: str) -> str:
    """Escape LIKE wildcards in user input and return a prefix pattern."""
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"{escaped}%"

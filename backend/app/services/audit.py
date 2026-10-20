import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import utcnow
from app.models.org import AuditLog, User


def audit(
    db: AsyncSession,
    user: User | None,
    action: str,
    entity: str,
    entity_id: int | None = None,
    **detail: Any,
) -> None:
    """Record a sensitive action. Added to the caller's transaction; committed with it."""
    db.add(
        AuditLog(
            user_id=user.id if user else None,
            action=action,
            entity=entity,
            entity_id=entity_id,
            detail=json.dumps(detail, default=str) if detail else None,
            created_at=utcnow(),
        )
    )

from fastapi import HTTPException, status
from sqlalchemy import update
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import utcnow
from app.models import MovementReason, StockLevel, StockMovement, User


async def move_stock(
    db: AsyncSession,
    *,
    branch_id: int,
    changes: dict[int, int],
    reason: MovementReason,
    ref_type: str,
    ref_id: int,
    user: User,
) -> None:
    """Apply ``{item_id: delta}`` to a branch's stock and write the ledger.

    Items are processed in id order so concurrent movements lock rows consistently (no
    deadlocks). A decrement that would go negative fails the whole operation with 409.
    """
    now = utcnow()
    for item_id in sorted(changes):
        delta = changes[item_id]
        if delta == 0:
            continue
        if delta > 0:
            stmt = mysql_insert(StockLevel).values(
                branch_id=branch_id, item_id=item_id, quantity=delta
            )
            await db.execute(
                stmt.on_duplicate_key_update(quantity=StockLevel.quantity + stmt.inserted.quantity)
            )
        else:
            result = await db.execute(
                update(StockLevel)
                .where(
                    StockLevel.branch_id == branch_id,
                    StockLevel.item_id == item_id,
                    StockLevel.quantity >= -delta,
                )
                .values(quantity=StockLevel.quantity + delta)
            )
            if result.rowcount != 1:
                raise HTTPException(
                    status.HTTP_409_CONFLICT, f"Insufficient stock for item {item_id}"
                )
        db.add(
            StockMovement(
                branch_id=branch_id,
                item_id=item_id,
                delta=delta,
                reason=reason,
                ref_type=ref_type,
                ref_id=ref_id,
                created_by=user.id,
                created_at=now,
            )
        )

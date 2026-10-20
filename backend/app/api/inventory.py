from datetime import timedelta
from decimal import Decimal

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.core.deps import (
    DB,
    MANAGEMENT,
    STAFF,
    CurrentUser,
    Page,
    apply_updates,
    can_access_branch,
    ensure_branch,
    get_or_404,
    get_scoped_or_404,
    require_roles,
    scope_to_branches,
    utcnow,
)
from app.models import (
    Branch,
    CountStatus,
    GoodsReceipt,
    GoodsReceiptLine,
    InventoryItem,
    Member,
    MovementReason,
    Payment,
    PaymentCategory,
    PurchaseRequest,
    PurchaseRequestLine,
    PurchaseStatus,
    StockCount,
    StockCountLine,
    StockLevel,
    StockMovement,
    StockTransfer,
    StockTransferLine,
    TransferStatus,
    VendorType,
)
from app.schemas.inventory import (
    CountIn,
    CountOut,
    CountUpdate,
    DecisionIn,
    ItemIn,
    ItemOut,
    ItemUpdate,
    MovementOut,
    PurchaseRequestIn,
    PurchaseRequestOut,
    ReceiptIn,
    ReceiptOut,
    SaleIn,
    SaleOut,
    StockOut,
    TransferIn,
    TransferOut,
)
from app.services.audit import audit
from app.services.stock import move_stock

router = APIRouter(prefix="/inventory", tags=["inventory"], dependencies=[require_roles(*STAFF)])
manage = [require_roles(*MANAGEMENT)]


async def _check_items(db: DB, item_ids) -> dict[int, InventoryItem]:
    ids = set(item_ids)
    items = {
        i.id: i for i in await db.scalars(select(InventoryItem).where(InventoryItem.id.in_(ids)))
    }
    if len(items) != len(ids):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown item_id")
    return items


async def _ref(db: DB, prefix: str, branch_id: int, obj_id: int) -> str:
    branch = await get_or_404(db, Branch, branch_id)
    return f"{prefix}-{branch.code}-{obj_id:05d}"


# ---------------------------------------------------------------- items & stock
@router.get("/items", response_model=list[ItemOut])
async def list_items(db: DB, active: bool | None = True) -> list[InventoryItem]:
    stmt = select(InventoryItem).order_by(InventoryItem.name, InventoryItem.size)
    if active is not None:
        stmt = stmt.where(InventoryItem.is_active == active)
    return list(await db.scalars(stmt))


@router.post("/items", response_model=ItemOut, status_code=201, dependencies=manage)
async def create_item(body: ItemIn, db: DB) -> InventoryItem:
    item = InventoryItem(**body.model_dump())
    db.add(item)
    await db.commit()
    return item


@router.patch("/items/{item_id}", response_model=ItemOut, dependencies=manage)
async def update_item(item_id: int, body: ItemUpdate, db: DB) -> InventoryItem:
    item = await get_or_404(db, InventoryItem, item_id)
    apply_updates(item, body.model_dump(exclude_unset=True))
    await db.commit()
    return item


@router.get("/stock", response_model=list[StockOut])
async def stock(user: CurrentUser, db: DB, branch_id: int, low_only: bool = False) -> list[dict]:
    """Current stock for every active item at a branch (items never stocked show 0)."""
    ensure_branch(user, branch_id)
    qty = func.coalesce(StockLevel.quantity, 0)
    stmt = (
        select(InventoryItem, qty)
        .outerjoin(
            StockLevel,
            (StockLevel.item_id == InventoryItem.id) & (StockLevel.branch_id == branch_id),
        )
        .where(InventoryItem.is_active.is_(True))
        .order_by(InventoryItem.name, InventoryItem.size)
    )
    if low_only:
        stmt = stmt.where(qty <= InventoryItem.reorder_level)
    return [
        {
            "branch_id": branch_id,
            "item": item,
            "quantity": q,
            "below_reorder": q <= item.reorder_level,
        }
        for item, q in (await db.execute(stmt)).all()
    ]


@router.get("/movements", response_model=list[MovementOut])
async def movements(
    user: CurrentUser, db: DB, page: Page, branch_id: int | None = None, item_id: int | None = None
) -> list[StockMovement]:
    stmt = scope_to_branches(select(StockMovement), StockMovement.branch_id, user, branch_id)
    if item_id is not None:
        stmt = stmt.where(StockMovement.item_id == item_id)
    return list(await db.scalars(page.apply(stmt.order_by(StockMovement.id.desc()))))


# ---------------------------------------------------------------- purchase requests
@router.get("/purchase-requests", response_model=list[PurchaseRequestOut])
async def list_purchase_requests(
    user: CurrentUser,
    db: DB,
    page: Page,
    branch_id: int | None = None,
    status: PurchaseStatus | None = None,
) -> list[PurchaseRequest]:
    stmt = scope_to_branches(select(PurchaseRequest), PurchaseRequest.branch_id, user, branch_id)
    if status is not None:
        stmt = stmt.where(PurchaseRequest.status == status)
    return list(await db.scalars(page.apply(stmt.order_by(PurchaseRequest.id.desc()))))


@router.post("/purchase-requests", response_model=PurchaseRequestOut, status_code=201)
async def create_purchase_request(
    body: PurchaseRequestIn, user: CurrentUser, db: DB
) -> PurchaseRequest:
    ensure_branch(user, body.branch_id)
    await _check_items(db, [ln.item_id for ln in body.lines])
    pr = PurchaseRequest(
        **body.model_dump(exclude={"lines"}),
        requested_by=user.id,
        lines=[PurchaseRequestLine(**ln.model_dump()) for ln in body.lines],
    )
    db.add(pr)
    await db.flush()
    pr.ref_no = await _ref(db, "PR", pr.branch_id, pr.id)
    await db.commit()
    return pr


@router.post("/purchase-requests/{pr_id}/submit", response_model=PurchaseRequestOut)
async def submit_purchase_request(pr_id: int, user: CurrentUser, db: DB) -> PurchaseRequest:
    pr = await get_scoped_or_404(db, PurchaseRequest, pr_id, user)
    if pr.status != PurchaseStatus.DRAFT:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only drafts can be submitted")
    pr.status = PurchaseStatus.SUBMITTED
    pr.submitted_at = utcnow()
    await db.commit()
    return pr


@router.post(
    "/purchase-requests/{pr_id}/decision", response_model=PurchaseRequestOut, dependencies=manage
)
async def decide_purchase_request(
    pr_id: int, body: DecisionIn, user: CurrentUser, db: DB
) -> PurchaseRequest:
    """Operations-manager approval. No order is placed without it."""
    pr = await get_scoped_or_404(db, PurchaseRequest, pr_id, user)
    await db.refresh(pr, with_for_update=True)
    if pr.status != PurchaseStatus.SUBMITTED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Request is not awaiting a decision")
    if not body.approve and not body.note:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Give a reason for rejecting")
    if body.approve and pr.vendor_type == VendorType.LOCAL:
        # Local-vendor purchases are limited to one per branch per calendar month.
        month_start = pr.submitted_at.date().replace(day=1)
        next_month = (month_start + timedelta(days=32)).replace(day=1)
        taken = await db.scalar(
            select(func.count()).where(
                PurchaseRequest.branch_id == pr.branch_id,
                PurchaseRequest.id != pr.id,
                PurchaseRequest.vendor_type == VendorType.LOCAL,
                PurchaseRequest.status.in_(
                    (PurchaseStatus.APPROVED, PurchaseStatus.ORDERED, PurchaseStatus.RECEIVED)
                ),
                PurchaseRequest.submitted_at >= month_start,
                PurchaseRequest.submitted_at < next_month,
            )
        )
        if taken:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "This branch already has a local purchase this month"
            )
    pr.status = PurchaseStatus.APPROVED if body.approve else PurchaseStatus.REJECTED
    pr.decided_by = user.id
    pr.decided_at = utcnow()
    pr.decision_note = body.note
    audit(db, user, "approve" if body.approve else "reject", "purchase_request", pr.id)
    await db.commit()
    return pr


@router.post("/purchase-requests/{pr_id}/ordered", response_model=PurchaseRequestOut)
async def mark_ordered(pr_id: int, user: CurrentUser, db: DB) -> PurchaseRequest:
    pr = await get_scoped_or_404(db, PurchaseRequest, pr_id, user)
    if pr.status != PurchaseStatus.APPROVED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only approved requests can be ordered")
    pr.status = PurchaseStatus.ORDERED
    pr.ordered_at = utcnow()
    await db.commit()
    return pr


# ---------------------------------------------------------------- receipts
@router.get("/receipts", response_model=list[ReceiptOut])
async def list_receipts(
    user: CurrentUser, db: DB, page: Page, branch_id: int | None = None
) -> list[GoodsReceipt]:
    stmt = scope_to_branches(select(GoodsReceipt), GoodsReceipt.branch_id, user, branch_id)
    return list(await db.scalars(page.apply(stmt.order_by(GoodsReceipt.id.desc()))))


@router.post("/receipts", response_model=ReceiptOut, status_code=201)
async def receive_goods(body: ReceiptIn, user: CurrentUser, db: DB) -> GoodsReceipt:
    """Check a vendor delivery against the approved request; stock what actually arrived."""
    ensure_branch(user, body.branch_id)
    await _check_items(db, [ln.item_id for ln in body.lines])
    expected: dict[int, int] = {}
    pr = None
    if body.purchase_request_id is not None:
        pr = await get_scoped_or_404(db, PurchaseRequest, body.purchase_request_id, user)
        await db.refresh(pr, with_for_update=True)
        if pr.status not in (PurchaseStatus.APPROVED, PurchaseStatus.ORDERED):
            raise HTTPException(status.HTTP_409_CONFLICT, "Purchase request is not approved")
        expected = {ln.item_id: ln.quantity for ln in pr.lines}

    lines = []
    for ln in body.lines:
        exp = ln.qty_expected if ln.qty_expected is not None else expected.get(ln.item_id, 0)
        lines.append(
            GoodsReceiptLine(item_id=ln.item_id, qty_expected=exp, qty_received=ln.qty_received)
        )
    # Items on the request that did not arrive at all are recorded as zero received.
    for item_id, qty in expected.items():
        if item_id not in {ln.item_id for ln in body.lines}:
            lines.append(GoodsReceiptLine(item_id=item_id, qty_expected=qty, qty_received=0))

    receipt = GoodsReceipt(
        branch_id=body.branch_id,
        purchase_request_id=body.purchase_request_id,
        vendor_invoice_no=body.vendor_invoice_no,
        notes=body.notes,
        received_by=user.id,
        received_at=utcnow(),
        has_discrepancy=any(ln.qty_expected != ln.qty_received for ln in lines),
        lines=lines,
    )
    db.add(receipt)
    await db.flush()
    receipt.ref_no = await _ref(db, "GRN", receipt.branch_id, receipt.id)
    await move_stock(
        db,
        branch_id=body.branch_id,
        changes={ln.item_id: ln.qty_received for ln in lines},
        reason=MovementReason.RECEIPT,
        ref_type="receipt",
        ref_id=receipt.id,
        user=user,
    )
    if pr is not None:
        pr.status = PurchaseStatus.RECEIVED
    await db.commit()
    return receipt


# ---------------------------------------------------------------- transfers
@router.get("/transfers", response_model=list[TransferOut])
async def list_transfers(
    user: CurrentUser, db: DB, page: Page, status: TransferStatus | None = None
) -> list[StockTransfer]:
    stmt = select(StockTransfer)
    if not user.sees_all_branches:
        ids = user.branch_ids or [-1]
        stmt = stmt.where(
            StockTransfer.from_branch_id.in_(ids) | StockTransfer.to_branch_id.in_(ids)
        )
    if status is not None:
        stmt = stmt.where(StockTransfer.status == status)
    return list(await db.scalars(page.apply(stmt.order_by(StockTransfer.id.desc()))))


@router.post("/transfers", response_model=TransferOut, status_code=201)
async def send_transfer(body: TransferIn, user: CurrentUser, db: DB) -> StockTransfer:
    """Sending branch signs out the items; they leave its stock immediately."""
    ensure_branch(user, body.from_branch_id)
    if body.from_branch_id == body.to_branch_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Branches must differ")
    await get_or_404(db, Branch, body.to_branch_id)
    await _check_items(db, [ln.item_id for ln in body.lines])
    transfer = StockTransfer(
        from_branch_id=body.from_branch_id,
        to_branch_id=body.to_branch_id,
        notes=body.notes,
        sent_by=user.id,
        sent_at=utcnow(),
        lines=[StockTransferLine(**ln.model_dump()) for ln in body.lines],
    )
    db.add(transfer)
    await db.flush()
    transfer.ref_no = await _ref(db, "TRF", transfer.from_branch_id, transfer.id)
    await move_stock(
        db,
        branch_id=body.from_branch_id,
        changes={ln.item_id: -ln.quantity for ln in body.lines},
        reason=MovementReason.TRANSFER_OUT,
        ref_type="transfer",
        ref_id=transfer.id,
        user=user,
    )
    await db.commit()
    return transfer


async def _open_transfer(db: DB, transfer_id: int, user, branch_attr: str) -> StockTransfer:
    transfer = await db.get(StockTransfer, transfer_id)
    if transfer is None or not (
        can_access_branch(user, transfer.from_branch_id)
        or can_access_branch(user, transfer.to_branch_id)
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transfer not found")
    ensure_branch(user, getattr(transfer, branch_attr))
    await db.refresh(transfer, with_for_update=True)
    if transfer.status != TransferStatus.IN_TRANSIT:
        raise HTTPException(status.HTTP_409_CONFLICT, "Transfer is not in transit")
    return transfer


@router.post("/transfers/{transfer_id}/receive", response_model=TransferOut)
async def receive_transfer(transfer_id: int, user: CurrentUser, db: DB) -> StockTransfer:
    """Receiving branch signs for the items; ownership transfers at this point."""
    transfer = await _open_transfer(db, transfer_id, user, "to_branch_id")
    await move_stock(
        db,
        branch_id=transfer.to_branch_id,
        changes={ln.item_id: ln.quantity for ln in transfer.lines},
        reason=MovementReason.TRANSFER_IN,
        ref_type="transfer",
        ref_id=transfer.id,
        user=user,
    )
    transfer.status = TransferStatus.RECEIVED
    transfer.received_by = user.id
    transfer.received_at = utcnow()
    await db.commit()
    return transfer


@router.post("/transfers/{transfer_id}/cancel", response_model=TransferOut)
async def cancel_transfer(transfer_id: int, user: CurrentUser, db: DB) -> StockTransfer:
    transfer = await _open_transfer(db, transfer_id, user, "from_branch_id")
    await move_stock(
        db,
        branch_id=transfer.from_branch_id,
        changes={ln.item_id: ln.quantity for ln in transfer.lines},
        reason=MovementReason.TRANSFER_CANCELLED,
        ref_type="transfer",
        ref_id=transfer.id,
        user=user,
    )
    transfer.status = TransferStatus.CANCELLED
    await db.commit()
    return transfer


# ---------------------------------------------------------------- sales
@router.post("/sales", response_model=SaleOut, status_code=201)
async def sell_item(body: SaleIn, user: CurrentUser, db: DB) -> dict:
    """Front-desk equipment sale: takes the stock and records the payment together."""
    ensure_branch(user, body.branch_id)
    item = await get_or_404(db, InventoryItem, body.item_id)
    if not item.is_active:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Item is not for sale")
    if body.member_id is not None:
        member = await get_scoped_or_404(db, Member, body.member_id, user)
        if member.branch_id != body.branch_id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Member is at another branch"
            )
    price = body.unit_price if body.unit_price is not None else item.unit_price
    if price != item.unit_price and user.role not in MANAGEMENT:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only managers can change prices")
    amount = (price * body.quantity).quantize(Decimal("0.001"))
    now = utcnow()
    payment = Payment(
        branch_id=body.branch_id,
        member_id=body.member_id,
        amount=amount,
        method=body.method,
        category=PaymentCategory.EQUIPMENT,
        notes=f"{body.quantity} x {item.name}" + (f" ({item.size})" if item.size else ""),
        paid_at=now,
        created_at=now,
        received_by=user.id,
    )
    db.add(payment)
    await db.flush()
    await move_stock(
        db,
        branch_id=body.branch_id,
        changes={item.id: -body.quantity},
        reason=MovementReason.SALE,
        ref_type="payment",
        ref_id=payment.id,
        user=user,
    )
    remaining = await db.scalar(
        select(StockLevel.quantity).where(
            StockLevel.branch_id == body.branch_id, StockLevel.item_id == item.id
        )
    )
    await db.commit()
    return {"payment_id": payment.id, "amount": amount, "remaining_stock": remaining}


# ---------------------------------------------------------------- monthly counts
@router.get("/counts", response_model=list[CountOut])
async def list_counts(user: CurrentUser, db: DB, branch_id: int | None = None) -> list[StockCount]:
    stmt = scope_to_branches(select(StockCount), StockCount.branch_id, user, branch_id)
    return list(await db.scalars(stmt.order_by(StockCount.period.desc())))


@router.post("/counts", response_model=CountOut, status_code=201)
async def record_count(body: CountIn, user: CurrentUser, db: DB) -> StockCount:
    """Record a physical count; the system quantity is snapshotted alongside each line."""
    ensure_branch(user, body.branch_id)
    await _check_items(db, [ln.item_id for ln in body.lines])
    system = dict(
        (
            await db.execute(
                select(StockLevel.item_id, StockLevel.quantity).where(
                    StockLevel.branch_id == body.branch_id,
                    StockLevel.item_id.in_([ln.item_id for ln in body.lines]),
                )
            )
        ).all()
    )
    count = StockCount(
        branch_id=body.branch_id,
        period=body.period,
        counted_by=user.id,
        lines=[
            StockCountLine(
                item_id=ln.item_id,
                system_qty=system.get(ln.item_id, 0),
                counted_qty=ln.counted_qty,
                reason=ln.reason,
            )
            for ln in body.lines
        ],
    )
    db.add(count)
    await db.commit()
    return count


@router.patch("/counts/{count_id}", response_model=CountOut)
async def recount(count_id: int, body: CountUpdate, user: CurrentUser, db: DB) -> StockCount:
    """Update recounted quantities or variance reasons while the count is still a draft."""
    count = await get_scoped_or_404(db, StockCount, count_id, user)
    if count.status != CountStatus.DRAFT:
        raise HTTPException(status.HTTP_409_CONFLICT, "Count already approved")
    by_item = {ln.item_id: ln for ln in count.lines}
    if any(ln.item_id not in by_item for ln in body.lines):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Item is not on this count")
    for ln in body.lines:
        by_item[ln.item_id].counted_qty = ln.counted_qty
        by_item[ln.item_id].reason = ln.reason
    await db.commit()
    return count


@router.post("/counts/{count_id}/approve", response_model=CountOut, dependencies=manage)
async def approve_count(count_id: int, user: CurrentUser, db: DB) -> StockCount:
    """Manager approval applies each variance to stock as a count adjustment."""
    count = await get_scoped_or_404(db, StockCount, count_id, user)
    await db.refresh(count, with_for_update=True)
    if count.status != CountStatus.DRAFT:
        raise HTTPException(status.HTTP_409_CONFLICT, "Count already approved")
    unexplained = [
        ln.item_id for ln in count.lines if ln.counted_qty != ln.system_qty and not ln.reason
    ]
    if unexplained:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Variance needs a reason: items {unexplained}"
        )
    await move_stock(
        db,
        branch_id=count.branch_id,
        changes={ln.item_id: ln.counted_qty - ln.system_qty for ln in count.lines},
        reason=MovementReason.COUNT_ADJUSTMENT,
        ref_type="count",
        ref_id=count.id,
        user=user,
    )
    count.status = CountStatus.APPROVED
    count.approved_by = user.id
    count.approved_at = utcnow()
    audit(db, user, "approve", "stock_count", count.id)
    await db.commit()
    return count

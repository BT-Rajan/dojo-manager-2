from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import Field, StringConstraints, computed_field, field_validator

from app.models.dojo import PaymentMethod
from app.models.inventory import (
    CountStatus,
    ItemCategory,
    MovementReason,
    PurchaseStatus,
    TransferStatus,
    VendorType,
)
from app.schemas.common import InModel, LongText, Money, OutModel, ShortText

Qty = Annotated[int, Field(ge=1, le=100_000)]
Sku = Annotated[str, StringConstraints(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9_.\-]+$")]


def _unique_items(lines):
    ids = [ln.item_id for ln in lines]
    if len(ids) != len(set(ids)):
        raise ValueError("Each item may appear only once")
    return lines


class ItemIn(InModel):
    sku: Sku
    name: Annotated[str, StringConstraints(min_length=1, max_length=120)]
    category: ItemCategory
    size: Annotated[str, StringConstraints(max_length=20)] | None = None
    unit_price: Money
    reorder_level: Annotated[int, Field(ge=0, le=100_000)] = 0
    is_active: bool = True


class ItemUpdate(InModel):
    name: Annotated[str, StringConstraints(min_length=1, max_length=120)] | None = None
    category: ItemCategory | None = None
    size: Annotated[str, StringConstraints(max_length=20)] | None = None
    unit_price: Money | None = None
    reorder_level: Annotated[int, Field(ge=0, le=100_000)] | None = None
    is_active: bool | None = None


class ItemOut(OutModel):
    id: int
    sku: str
    name: str
    category: ItemCategory
    size: str | None
    unit_price: Decimal
    reorder_level: int
    is_active: bool


class StockOut(OutModel):
    branch_id: int
    item: ItemOut
    quantity: int
    below_reorder: bool


class MovementOut(OutModel):
    id: int
    branch_id: int
    item_id: int
    delta: int
    reason: MovementReason
    ref_type: str | None
    ref_id: int | None
    created_by: int | None
    created_at: datetime


# ---------------------------------------------------------------- purchase requests
class PRLineIn(InModel):
    item_id: int
    quantity: Qty
    unit_cost: Money | None = None


class PurchaseRequestIn(InModel):
    branch_id: int
    vendor_name: Annotated[str, StringConstraints(min_length=1, max_length=150)]
    vendor_type: VendorType
    notes: LongText | None = None
    lines: Annotated[list[PRLineIn], Field(min_length=1, max_length=200)]

    _unique = field_validator("lines")(_unique_items)


class DecisionIn(InModel):
    approve: bool
    note: ShortText | None = None


class PRLineOut(OutModel):
    id: int
    item_id: int
    quantity: int
    unit_cost: Decimal | None


class PurchaseRequestOut(OutModel):
    id: int
    ref_no: str | None
    branch_id: int
    vendor_name: str
    vendor_type: VendorType
    status: PurchaseStatus
    notes: str | None
    requested_by: int | None
    submitted_at: datetime | None
    decided_by: int | None
    decided_at: datetime | None
    decision_note: str | None
    ordered_at: datetime | None
    lines: list[PRLineOut]


# ---------------------------------------------------------------- receipts
class ReceiptLineIn(InModel):
    item_id: int
    qty_received: Annotated[int, Field(ge=0, le=100_000)]
    qty_expected: Annotated[int, Field(ge=0, le=100_000)] | None = None


class ReceiptIn(InModel):
    branch_id: int
    purchase_request_id: int | None = None
    vendor_invoice_no: Annotated[str, StringConstraints(max_length=60)] | None = None
    notes: LongText | None = None
    lines: Annotated[list[ReceiptLineIn], Field(min_length=1, max_length=200)]

    _unique = field_validator("lines")(_unique_items)


class ReceiptLineOut(OutModel):
    item_id: int
    qty_expected: int
    qty_received: int


class ReceiptOut(OutModel):
    id: int
    ref_no: str | None
    branch_id: int
    purchase_request_id: int | None
    vendor_invoice_no: str | None
    has_discrepancy: bool
    notes: str | None
    received_by: int | None
    received_at: datetime
    lines: list[ReceiptLineOut]


# ---------------------------------------------------------------- transfers
class TransferLineIn(InModel):
    item_id: int
    quantity: Qty


class TransferIn(InModel):
    from_branch_id: int
    to_branch_id: int
    notes: LongText | None = None
    lines: Annotated[list[TransferLineIn], Field(min_length=1, max_length=200)]

    _unique = field_validator("lines")(_unique_items)


class TransferLineOut(OutModel):
    item_id: int
    quantity: int


class TransferOut(OutModel):
    id: int
    ref_no: str | None
    from_branch_id: int
    to_branch_id: int
    status: TransferStatus
    notes: str | None
    sent_by: int | None
    sent_at: datetime
    received_by: int | None
    received_at: datetime | None
    lines: list[TransferLineOut]


# ---------------------------------------------------------------- sales
class SaleIn(InModel):
    branch_id: int
    item_id: int
    quantity: Qty = 1
    member_id: int | None = None
    method: PaymentMethod
    unit_price: Money | None = None  # defaults to the item price; overriding needs a manager


class SaleOut(OutModel):
    payment_id: int
    amount: Decimal
    remaining_stock: int


# ---------------------------------------------------------------- counts
class CountLineIn(InModel):
    item_id: int
    counted_qty: Annotated[int, Field(ge=0, le=100_000)]
    reason: ShortText | None = None


class CountIn(InModel):
    branch_id: int
    period: Annotated[str, StringConstraints(pattern=r"^20[0-9]{2}-(0[1-9]|1[0-2])$")]
    lines: Annotated[list[CountLineIn], Field(min_length=1, max_length=1000)]

    _unique = field_validator("lines")(_unique_items)


class CountUpdate(InModel):
    lines: Annotated[list[CountLineIn], Field(min_length=1, max_length=1000)]

    _unique = field_validator("lines")(_unique_items)


class CountLineOut(OutModel):
    item_id: int
    system_qty: int
    counted_qty: int
    reason: str | None

    @computed_field
    @property
    def variance(self) -> int:
        return self.counted_qty - self.system_qty


class CountOut(OutModel):
    id: int
    branch_id: int
    period: str
    status: CountStatus
    counted_by: int | None
    approved_by: int | None
    approved_at: datetime | None
    lines: list[CountLineOut]

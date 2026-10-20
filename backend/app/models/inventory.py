"""Inventory: purchase request -> approval -> receipt -> inter-branch transfer -> monthly count.

``stock_levels`` holds the current quantity per branch and item; every change is also written
to the append-only ``stock_movements`` ledger.
"""

import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, db_enum
from app.models.dojo import KD


class ItemCategory(enum.StrEnum):
    UNIFORM = "uniform"
    BELT = "belt"
    PROTECTIVE_GEAR = "protective_gear"
    TRAINING_EQUIPMENT = "training_equipment"
    MERCHANDISE = "merchandise"
    OTHER = "other"


class MovementReason(enum.StrEnum):
    RECEIPT = "receipt"
    TRANSFER_OUT = "transfer_out"
    TRANSFER_IN = "transfer_in"
    TRANSFER_CANCELLED = "transfer_cancelled"
    SALE = "sale"
    COUNT_ADJUSTMENT = "count_adjustment"


class VendorType(enum.StrEnum):
    LOCAL = "local"
    INTERNATIONAL = "international"


class PurchaseStatus(enum.StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    ORDERED = "ordered"
    RECEIVED = "received"


class TransferStatus(enum.StrEnum):
    IN_TRANSIT = "in_transit"
    RECEIVED = "received"
    CANCELLED = "cancelled"


class CountStatus(enum.StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"


class InventoryItem(TimestampMixin, Base):
    __tablename__ = "inventory_items"
    __table_args__ = (UniqueConstraint("name", "size"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[ItemCategory] = mapped_column(db_enum(ItemCategory))
    size: Mapped[str | None] = mapped_column(String(20))
    unit_price: Mapped[Decimal] = mapped_column(KD)
    reorder_level: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")


class StockLevel(Base):
    __tablename__ = "stock_levels"
    __table_args__ = (CheckConstraint("quantity >= 0", name="non_negative"),)

    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"), primary_key=True)
    quantity: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class StockMovement(Base):
    __tablename__ = "stock_movements"
    __table_args__ = (Index("ix_stock_movements_branch_item", "branch_id", "item_id", "id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"))
    item_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"))
    delta: Mapped[int] = mapped_column(Integer)
    reason: Mapped[MovementReason] = mapped_column(db_enum(MovementReason))
    ref_type: Mapped[str | None] = mapped_column(String(30))
    ref_id: Mapped[int | None] = mapped_column(Integer)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime)


class PurchaseRequest(TimestampMixin, Base):
    __tablename__ = "purchase_requests"
    __table_args__ = (Index("ix_purchase_requests_branch_status", "branch_id", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ref_no: Mapped[str | None] = mapped_column(String(30), unique=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"))
    vendor_name: Mapped[str] = mapped_column(String(150))
    vendor_type: Mapped[VendorType] = mapped_column(db_enum(VendorType))
    status: Mapped[PurchaseStatus] = mapped_column(
        db_enum(PurchaseStatus), default=PurchaseStatus.DRAFT, server_default="draft"
    )
    notes: Mapped[str | None] = mapped_column(Text)
    requested_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime)
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)
    decision_note: Mapped[str | None] = mapped_column(String(255))
    ordered_at: Mapped[datetime | None] = mapped_column(DateTime)

    lines: Mapped[list["PurchaseRequestLine"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan", order_by="PurchaseRequestLine.id"
    )


class PurchaseRequestLine(Base):
    __tablename__ = "purchase_request_lines"
    __table_args__ = (
        UniqueConstraint("request_id", "item_id"),
        CheckConstraint("quantity > 0", name="positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("purchase_requests.id", ondelete="CASCADE"))
    item_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_cost: Mapped[Decimal | None] = mapped_column(KD)


class GoodsReceipt(TimestampMixin, Base):
    __tablename__ = "goods_receipts"

    id: Mapped[int] = mapped_column(primary_key=True)
    ref_no: Mapped[str | None] = mapped_column(String(30), unique=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), index=True)
    purchase_request_id: Mapped[int | None] = mapped_column(ForeignKey("purchase_requests.id"))
    vendor_invoice_no: Mapped[str | None] = mapped_column(String(60))
    has_discrepancy: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    notes: Mapped[str | None] = mapped_column(Text)
    received_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    received_at: Mapped[datetime] = mapped_column(DateTime)

    lines: Mapped[list["GoodsReceiptLine"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan", order_by="GoodsReceiptLine.id"
    )


class GoodsReceiptLine(Base):
    __tablename__ = "goods_receipt_lines"
    __table_args__ = (UniqueConstraint("receipt_id", "item_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_id: Mapped[int] = mapped_column(ForeignKey("goods_receipts.id", ondelete="CASCADE"))
    item_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"))
    qty_expected: Mapped[int] = mapped_column(Integer)
    qty_received: Mapped[int] = mapped_column(Integer)


class StockTransfer(TimestampMixin, Base):
    __tablename__ = "stock_transfers"
    __table_args__ = (CheckConstraint("from_branch_id <> to_branch_id", name="distinct_branches"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ref_no: Mapped[str | None] = mapped_column(String(30), unique=True)
    from_branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), index=True)
    to_branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), index=True)
    status: Mapped[TransferStatus] = mapped_column(
        db_enum(TransferStatus), default=TransferStatus.IN_TRANSIT, server_default="in_transit"
    )
    notes: Mapped[str | None] = mapped_column(Text)
    sent_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    sent_at: Mapped[datetime] = mapped_column(DateTime)
    received_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    received_at: Mapped[datetime | None] = mapped_column(DateTime)

    lines: Mapped[list["StockTransferLine"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan", order_by="StockTransferLine.id"
    )


class StockTransferLine(Base):
    __tablename__ = "stock_transfer_lines"
    __table_args__ = (
        UniqueConstraint("transfer_id", "item_id"),
        CheckConstraint("quantity > 0", name="positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    transfer_id: Mapped[int] = mapped_column(ForeignKey("stock_transfers.id", ondelete="CASCADE"))
    item_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"))
    quantity: Mapped[int] = mapped_column(Integer)


class StockCount(TimestampMixin, Base):
    __tablename__ = "stock_counts"
    __table_args__ = (UniqueConstraint("branch_id", "period"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"))
    period: Mapped[str] = mapped_column(String(7))  # YYYY-MM
    status: Mapped[CountStatus] = mapped_column(
        db_enum(CountStatus), default=CountStatus.DRAFT, server_default="draft"
    )
    counted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)

    lines: Mapped[list["StockCountLine"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan", order_by="StockCountLine.id"
    )


class StockCountLine(Base):
    __tablename__ = "stock_count_lines"
    __table_args__ = (UniqueConstraint("count_id", "item_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    count_id: Mapped[int] = mapped_column(ForeignKey("stock_counts.id", ondelete="CASCADE"))
    item_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"))
    system_qty: Mapped[int] = mapped_column(Integer)
    counted_qty: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str | None] = mapped_column(String(255))

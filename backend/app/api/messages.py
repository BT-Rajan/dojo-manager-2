"""WhatsApp messages to a member's family, and the family's message choices, from the staff
side."""

from datetime import datetime

from fastapi import APIRouter
from sqlalchemy import or_, select

from app.core.deps import DB, STAFF, CurrentUser, get_scoped_or_404, require_roles
from app.models import Guardian, GuardianLink, Member, MessageLog, MessagingOptIn
from app.schemas.common import InModel, OutModel
from app.services.audit import audit
from app.services.bookings import contact
from app.services.messaging import opted_in, service_messages_on, set_service_messages

router = APIRouter(tags=["messages"], dependencies=[require_roles(*STAFF)])


class MessageOut(OutModel):
    id: int
    to: str
    category: str
    kind: str
    text: str
    status: str
    at: datetime


class ChoicesOut(OutModel):
    mobile: str | None
    service_on: bool
    broadcasts_on: bool
    history: list[dict]


class ChoicesIn(InModel):
    service_on: bool | None = None
    broadcasts_on: bool | None = None


async def _family_mobiles(db: DB, member: Member) -> set[str]:
    mobiles = set(
        await db.scalars(
            select(Guardian.mobile)
            .join(GuardianLink, GuardianLink.guardian_id == Guardian.id)
            .where(GuardianLink.member_id == member.id)
        )
    )
    if member.portal_mobile:
        mobiles.add(member.portal_mobile)
    return mobiles


@router.get("/members/{member_id}/messages", response_model=list[MessageOut])
async def member_messages(member_id: int, user: CurrentUser, db: DB, limit: int = 50):
    """Messages about this member, plus sign-in-free messages to their family's mobiles."""
    member = await get_scoped_or_404(db, Member, member_id, user)
    mobiles = await _family_mobiles(db, member)
    stmt = (
        select(MessageLog)
        .where(
            or_(MessageLog.member_id == member.id, MessageLog.to.in_(mobiles or {""})),
            MessageLog.kind != "sign_in_code",
        )
        .order_by(MessageLog.at.desc(), MessageLog.id.desc())
        .limit(min(max(limit, 1), 200))
    )
    return list(await db.scalars(stmt))


async def _choices(db: DB, member: Member) -> dict:
    mobile, _ = await contact(db, member)
    history = await db.scalars(
        select(MessagingOptIn)
        .where(MessagingOptIn.member_id == member.id)
        .order_by(MessagingOptIn.at.desc(), MessagingOptIn.id.desc())
        .limit(20)
    )
    return {
        "mobile": mobile or None,
        "service_on": await service_messages_on(db, mobile) if mobile else True,
        "broadcasts_on": await opted_in(db, member.id),
        "history": [{"opted_in": h.opted_in, "source": h.source, "at": h.at} for h in history],
    }


@router.get("/members/{member_id}/message-choices", response_model=ChoicesOut)
async def message_choices(member_id: int, user: CurrentUser, db: DB) -> dict:
    return await _choices(db, await get_scoped_or_404(db, Member, member_id, user))


@router.post("/members/{member_id}/message-choices", response_model=ChoicesOut)
async def set_message_choices(member_id: int, body: ChoicesIn, user: CurrentUser, db: DB):
    """Record what the family asked for at the desk."""
    member = await get_scoped_or_404(db, Member, member_id, user)
    mobile, _ = await contact(db, member)
    if body.service_on is not None and mobile:
        await set_service_messages(db, mobile, body.service_on, user.id)
    if body.broadcasts_on is not None:
        db.add(
            MessagingOptIn(
                member_id=member.id,
                opted_in=body.broadcasts_on,
                source="desk",
                recorded_by=user.id,
            )
        )
    audit(db, user, "message_choices", "member", member.id, **body.model_dump(exclude_none=True))
    await db.commit()
    return await _choices(db, member)

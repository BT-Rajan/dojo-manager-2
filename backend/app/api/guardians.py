"""Families for the member portal: parents and guardians linked to members. A guardian signs
in to the portal with their mobile number and sees every member they are linked to."""

from fastapi import APIRouter, HTTPException, status
from pydantic import EmailStr
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import DB, STAFF, CurrentUser, get_scoped_or_404, require_roles
from app.core.mobile import normalize_kuwait_mobile
from app.models import Guardian, GuardianLink, Member, Relationship
from app.schemas.common import InModel, Name, OutModel
from app.services.audit import audit

router = APIRouter(tags=["guardians"], dependencies=[require_roles(*STAFF)])


class GuardianLinkIn(InModel):
    full_name: Name
    full_name_ar: Name | None = None
    mobile: str
    email: EmailStr | None = None
    relationship: Relationship = Relationship.GUARDIAN
    is_primary: bool = False


class GuardianLinkUpdate(InModel):
    full_name: Name | None = None
    full_name_ar: Name | None = None
    mobile: str | None = None
    email: EmailStr | None = None
    relationship: Relationship | None = None
    is_primary: bool | None = None


class GuardianLinkOut(OutModel):
    guardian_id: int
    member_id: int
    full_name: str
    full_name_ar: str | None = None
    mobile: str
    email: str | None
    relationship: Relationship
    is_primary: bool
    # Other members this guardian is linked to (siblings in the same family).
    other_member_ids: list[int]


def _mobile(value: str) -> str:
    try:
        return normalize_kuwait_mobile(value)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None


async def _out(db: AsyncSession, link: GuardianLink) -> dict:
    g = link.guardian
    others = await db.scalars(
        select(GuardianLink.member_id).where(
            GuardianLink.guardian_id == g.id, GuardianLink.member_id != link.member_id
        )
    )
    return {
        "guardian_id": g.id,
        "member_id": link.member_id,
        "full_name": g.full_name,
        "full_name_ar": g.full_name_ar,
        "mobile": g.mobile,
        "email": g.email,
        "relationship": link.relationship,
        "is_primary": link.is_primary,
        "other_member_ids": sorted(others),
    }


async def _only_primary(db: AsyncSession, link: GuardianLink) -> None:
    await db.execute(
        update(GuardianLink)
        .where(
            GuardianLink.member_id == link.member_id,
            GuardianLink.guardian_id != link.guardian_id,
        )
        .values(is_primary=False)
    )


async def link_guardian(
    db: AsyncSession,
    member: Member,
    *,
    full_name: str,
    mobile: str,
    email: str | None = None,
    full_name_ar: str | None = None,
    relationship: Relationship = Relationship.GUARDIAN,
    is_primary: bool = False,
) -> GuardianLink:
    """Link a guardian (found by mobile, or created) to ``member``. One family, one number:
    a second child registered with the same parent mobile joins the same family."""
    guardian = await db.scalar(select(Guardian).where(Guardian.mobile == mobile).limit(1))
    if guardian is None:
        guardian = Guardian(
            full_name=full_name, full_name_ar=full_name_ar, mobile=mobile, email=email
        )
        db.add(guardian)
        await db.flush()
    elif await db.get(GuardianLink, (guardian.id, member.id)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This guardian is already linked")
    link = GuardianLink(
        guardian_id=guardian.id,
        member_id=member.id,
        relationship=relationship,
        is_primary=is_primary,
    )
    db.add(link)
    await db.flush()
    await db.refresh(link, ["guardian"])
    if is_primary:
        await _only_primary(db, link)
    return link


async def _link_or_404(db: AsyncSession, guardian_id: int, member_id: int) -> GuardianLink:
    link = await db.get(GuardianLink, (guardian_id, member_id))
    if link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Guardian not linked to this member")
    return link


@router.get("/members/{member_id}/guardians", response_model=list[GuardianLinkOut])
async def list_guardians(member_id: int, user: CurrentUser, db: DB) -> list[dict]:
    await get_scoped_or_404(db, Member, member_id, user)
    links = await db.scalars(
        select(GuardianLink)
        .where(GuardianLink.member_id == member_id)
        .order_by(GuardianLink.is_primary.desc(), GuardianLink.guardian_id)
    )
    return [await _out(db, link) for link in links]


@router.post(
    "/members/{member_id}/guardians",
    response_model=GuardianLinkOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_guardian(member_id: int, body: GuardianLinkIn, user: CurrentUser, db: DB) -> dict:
    member = await get_scoped_or_404(db, Member, member_id, user)
    link = await link_guardian(
        db,
        member,
        full_name=body.full_name,
        full_name_ar=body.full_name_ar,
        mobile=_mobile(body.mobile),
        email=body.email,
        relationship=body.relationship,
        is_primary=body.is_primary,
    )
    audit(db, user, "link_guardian", "member", member.id, guardian_id=link.guardian_id)
    await db.commit()
    return await _out(db, link)


@router.patch("/members/{member_id}/guardians/{guardian_id}", response_model=GuardianLinkOut)
async def update_guardian(
    member_id: int, guardian_id: int, body: GuardianLinkUpdate, user: CurrentUser, db: DB
) -> dict:
    """Change the link, or the guardian's own details (which apply to the whole family)."""
    await get_scoped_or_404(db, Member, member_id, user)
    link = await _link_or_404(db, guardian_id, member_id)
    data = body.model_dump(exclude_unset=True)
    g = link.guardian
    if "mobile" in data:
        mobile = _mobile(data["mobile"])
        clash = await db.scalar(
            select(Guardian.id).where(Guardian.mobile == mobile, Guardian.id != g.id)
        )
        if clash is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Another guardian has this mobile")
        g.mobile = mobile
    for field in ("full_name", "full_name_ar", "email"):
        if field in data:
            setattr(g, field, data[field])
    if data.get("relationship") is not None:
        link.relationship = data["relationship"]
    if data.get("is_primary") is not None:
        link.is_primary = data["is_primary"]
        if link.is_primary:
            await _only_primary(db, link)
    audit(db, user, "update_guardian", "guardian", g.id, fields=sorted(data))
    await db.commit()
    await db.refresh(link, ["guardian"])
    return await _out(db, link)


@router.delete("/members/{member_id}/guardians/{guardian_id}", status_code=204)
async def unlink_guardian(member_id: int, guardian_id: int, user: CurrentUser, db: DB) -> None:
    """Unlink; a guardian left with no members is removed (and can no longer sign in)."""
    await get_scoped_or_404(db, Member, member_id, user)
    link = await _link_or_404(db, guardian_id, member_id)
    await db.delete(link)
    await db.flush()
    remaining = await db.scalar(
        select(GuardianLink.member_id).where(GuardianLink.guardian_id == guardian_id).limit(1)
    )
    if remaining is None:
        guardian = await db.get(Guardian, guardian_id)
        if guardian is not None:
            await db.delete(guardian)
    audit(db, user, "unlink_guardian", "member", member_id, guardian_id=guardian_id)
    await db.commit()


__all__ = ["link_guardian", "router"]

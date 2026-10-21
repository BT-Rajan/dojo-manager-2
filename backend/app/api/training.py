"""Progress towards the next belt, from the staff side: skills at each belt (the curriculum),
skill check-offs, coach evaluations, monthly progress notes, and photo consent."""

from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, status
from pydantic import StringConstraints
from sqlalchemy import delete, select

from app.core.clock import today as academy_today
from app.core.deps import (
    ANY_ROLE,
    DB,
    MANAGEMENT,
    STAFF,
    CurrentUser,
    get_or_404,
    get_scoped_or_404,
    require_roles,
    utcnow,
)
from app.models import (
    RULES_VERSION,
    BeltRank,
    BeltSkill,
    Evaluation,
    Instructor,
    MediaConsent,
    Member,
    MessageCategory,
    NoteStatus,
    ProgressNote,
    Role,
    RulesAgreement,
    SkillCheck,
    Track,
)
from app.schemas.common import InModel, Name, OutModel
from app.services.audit import audit
from app.services.bookings import contact
from app.services.messaging import send_message
from app.services.progress import progress

router = APIRouter(tags=["training"])
any_role = [require_roles(*ANY_ROLE)]

LongNote = Annotated[str, StringConstraints(min_length=1, max_length=2000)]


# ---------------------------------------------------------------- schemas
class SkillIn(InModel):
    track: Track
    category: Annotated[str, StringConstraints(min_length=1, max_length=40)]
    name: Annotated[str, StringConstraints(min_length=1, max_length=120)]


class SkillUpdate(InModel):
    category: Annotated[str, StringConstraints(min_length=1, max_length=40)] | None = None
    name: Annotated[str, StringConstraints(min_length=1, max_length=120)] | None = None
    is_active: bool | None = None


class SkillOut(OutModel):
    id: int
    belt_rank_id: int
    track: Track
    category: str
    name: str
    sort_order: int
    is_active: bool


class SkillCheckIn(InModel):
    checked: bool


class EvaluationIn(InModel):
    eval_date: date | None = None
    instructor_id: int | None = None
    notes: Annotated[str, StringConstraints(max_length=2000)] | None = None
    ready_for_test: bool = False


class ProgressNoteIn(InModel):
    month: date
    instructor_id: int | None = None
    worked_on: LongNote
    next_steps: LongNote


class ProgressNoteOut(OutModel):
    id: int
    member_id: int
    month: date
    instructor_id: int | None
    worked_on: str
    next_steps: str
    status: NoteStatus
    sent_at: datetime | None


class ConsentIn(InModel):
    internal_records: bool
    social_media: bool
    website_marketing: bool
    signed_by_name: Name


class ConsentOut(OutModel):
    id: int
    internal_records: bool
    social_media: bool
    website_marketing: bool
    signed_by_name: str
    signed_at: datetime
    from_portal: bool
    notes: str | None


class RulesOut(OutModel):
    rules_version: str
    signed_by_name: str
    signed_at: datetime
    from_portal: bool


class CheckOut(OutModel):
    code: str
    en: str
    ar: str
    have: int
    need: int
    ok: bool


class BeltBrief(OutModel):
    id: int
    name: str
    color: str
    name_ar: str | None = None


class ProgressSkill(OutModel):
    id: int
    track: Track
    category: str
    name: str
    checked_on: date | None


class ProgressOut(OutModel):
    belt: BeltBrief | None
    stripes: int
    next: BeltBrief | None
    since: date | None
    classes: int
    seminars: int
    checks: list[CheckOut]
    eligible: bool
    skills: list[ProgressSkill]
    done: int
    total: int
    tests: list[dict]
    evaluations: list[dict]
    notes: list[ProgressNoteOut]
    consent: ConsentOut | None
    consent_history: list[ConsentOut]
    rules_signed: RulesOut | None
    rules_version: str


# ---------------------------------------------------------------- curriculum (admin)
@router.get("/belts/{belt_id}/skills", response_model=list[SkillOut], dependencies=any_role)
async def list_skills(belt_id: int, db: DB, include_inactive: bool = False) -> list[BeltSkill]:
    stmt = select(BeltSkill).where(BeltSkill.belt_rank_id == belt_id)
    if not include_inactive:
        stmt = stmt.where(BeltSkill.is_active.is_(True))
    return list(await db.scalars(stmt.order_by(BeltSkill.track, BeltSkill.sort_order)))


@router.post(
    "/belts/{belt_id}/skills",
    response_model=SkillOut,
    status_code=201,
    dependencies=[require_roles(*MANAGEMENT)],
)
async def add_skill(belt_id: int, body: SkillIn, db: DB) -> BeltSkill:
    await get_or_404(db, BeltRank, belt_id)
    last = await db.scalar(
        select(BeltSkill.sort_order)
        .where(BeltSkill.belt_rank_id == belt_id, BeltSkill.track == body.track)
        .order_by(BeltSkill.sort_order.desc())
        .limit(1)
    )
    skill = BeltSkill(belt_rank_id=belt_id, **body.model_dump(), sort_order=(last or 0) + 1)
    db.add(skill)
    await db.commit()
    return skill


@router.patch(
    "/skills/{skill_id}", response_model=SkillOut, dependencies=[require_roles(*MANAGEMENT)]
)
async def update_skill(skill_id: int, body: SkillUpdate, db: DB) -> BeltSkill:
    skill = await get_or_404(db, BeltSkill, skill_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(skill, k, v)
    await db.commit()
    return skill


# ---------------------------------------------------------------- a member's progress
async def consent_rows(db: DB, member_id: int) -> list[MediaConsent]:
    return list(
        await db.scalars(
            select(MediaConsent)
            .where(MediaConsent.member_id == member_id)
            .order_by(MediaConsent.signed_at.desc(), MediaConsent.id.desc())
        )
    )


async def rules_signed(db: DB, member_id: int) -> RulesAgreement | None:
    return await db.scalar(
        select(RulesAgreement)
        .where(RulesAgreement.member_id == member_id, RulesAgreement.rules_version == RULES_VERSION)
        .order_by(RulesAgreement.signed_at.desc())
        .limit(1)
    )


@router.get("/members/{member_id}/progress", response_model=ProgressOut, dependencies=any_role)
async def member_progress(member_id: int, user: CurrentUser, db: DB) -> dict:
    member = await get_scoped_or_404(db, Member, member_id, user)
    p = await progress(db, member, academy_today())
    notes = list(
        await db.scalars(
            select(ProgressNote)
            .where(ProgressNote.member_id == member.id)
            .order_by(ProgressNote.month.desc(), ProgressNote.id.desc())
        )
    )
    consents = await consent_rows(db, member.id)
    empty = {
        "belt": None,
        "stripes": member.stripes,
        "next": None,
        "since": None,
        "classes": 0,
        "seminars": 0,
        "checks": [],
        "eligible": False,
        "skills": [],
        "done": 0,
        "total": 0,
        "tests": [],
        "evaluations": [],
    }
    return (p or empty) | {
        "notes": notes,
        "consent": consents[0] if consents else None,
        "consent_history": consents,
        "rules_signed": await rules_signed(db, member.id),
        "rules_version": RULES_VERSION,
    }


@router.put("/members/{member_id}/skills/{skill_id}", status_code=204, dependencies=any_role)
async def check_skill(
    member_id: int, skill_id: int, body: SkillCheckIn, user: CurrentUser, db: DB
) -> None:
    """Tick (or untick) a skill the student has shown."""
    await get_scoped_or_404(db, Member, member_id, user)
    await get_or_404(db, BeltSkill, skill_id)
    existing = await db.get(SkillCheck, (member_id, skill_id))
    if body.checked and existing is None:
        db.add(
            SkillCheck(
                member_id=member_id,
                skill_id=skill_id,
                checked_on=academy_today(),
                checked_by=user.id,
            )
        )
    elif not body.checked and existing is not None:
        await db.execute(
            delete(SkillCheck).where(
                SkillCheck.member_id == member_id, SkillCheck.skill_id == skill_id
            )
        )
    await db.commit()


async def _coach_id(db: DB, user, instructor_id: int | None, member: Member) -> int | None:
    """Coaches sign their own evaluations and notes; staff may name the coach."""
    if user.role == Role.INSTRUCTOR:
        own = await db.scalar(select(Instructor.id).where(Instructor.user_id == user.id))
        return own
    if instructor_id is not None:
        inst = await db.get(Instructor, instructor_id)
        if inst is None or inst.branch_id != member.branch_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown instructor_id")
    return instructor_id


@router.post("/members/{member_id}/evaluations", status_code=201, dependencies=any_role)
async def add_evaluation(member_id: int, body: EvaluationIn, user: CurrentUser, db: DB) -> dict:
    member = await get_scoped_or_404(db, Member, member_id, user)
    ev = Evaluation(
        member_id=member.id,
        belt_rank_id=member.belt_rank_id,
        eval_date=body.eval_date or academy_today(),
        instructor_id=await _coach_id(db, user, body.instructor_id, member),
        notes=body.notes or None,
        ready_for_test=body.ready_for_test,
        recorded_by=user.id,
    )
    db.add(ev)
    await db.commit()
    return {"id": ev.id}


@router.delete("/evaluations/{evaluation_id}", status_code=204, dependencies=any_role)
async def delete_evaluation(evaluation_id: int, user: CurrentUser, db: DB) -> None:
    ev = await get_or_404(db, Evaluation, evaluation_id)
    await get_scoped_or_404(db, Member, ev.member_id, user)
    if user.role == Role.INSTRUCTOR and ev.recorded_by != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Coaches remove only their own")
    await db.delete(ev)
    await db.commit()


@router.post(
    "/members/{member_id}/progress-notes",
    response_model=ProgressNoteOut,
    status_code=201,
    dependencies=any_role,
)
async def add_progress_note(
    member_id: int, body: ProgressNoteIn, user: CurrentUser, db: DB
) -> ProgressNote:
    member = await get_scoped_or_404(db, Member, member_id, user)
    note = ProgressNote(
        member_id=member.id,
        month=body.month.replace(day=1),
        instructor_id=await _coach_id(db, user, body.instructor_id, member),
        worked_on=body.worked_on,
        next_steps=body.next_steps,
        created_by=user.id,
    )
    db.add(note)
    await db.commit()
    return note


NOTE_TEXT = (
    "{member} — progress for {month}. Worked on: {worked_on} Next: {next_steps} — Elite Academy",
    "{member} — تقرير شهر {month}. ما عملنا عليه: {worked_on} الخطوة التالية: {next_steps} "
    "— أكاديمية إيليت",
)


@router.post(
    "/progress-notes/{note_id}/send", response_model=ProgressNoteOut, dependencies=any_role
)
async def send_progress_note(note_id: int, user: CurrentUser, db: DB) -> ProgressNote:
    """Send the monthly note: the family sees it in the portal and gets it by WhatsApp (a
    service message, which families can turn off)."""
    note = await get_or_404(db, ProgressNote, note_id)
    member = await get_scoped_or_404(db, Member, note.member_id, user)
    if note.status == NoteStatus.SENT:
        raise HTTPException(status.HTTP_409_CONFLICT, "Already sent")
    note.status = NoteStatus.SENT
    note.sent_at = utcnow()
    mobile, lang = await contact(db, member)
    if mobile:
        en, ar = NOTE_TEXT
        text = (ar if lang == "ar" else en).format(
            member=f"{member.first_name} {member.last_name}",
            month=f"{note.month:%m/%Y}",
            worked_on=note.worked_on,
            next_steps=note.next_steps,
        )
        await send_message(
            db,
            mobile,
            text,
            category=MessageCategory.SERVICE,
            kind="progress_note",
            member_id=member.id,
        )
    audit(db, user, "progress_note_sent", "member", member.id, note_id=note.id)
    await db.commit()
    return note


@router.post(
    "/members/{member_id}/consent",
    response_model=ConsentOut,
    status_code=201,
    dependencies=[require_roles(*STAFF)],
)
async def record_consent(member_id: int, body: ConsentIn, user: CurrentUser, db: DB):
    """Consent recorded at the desk (from the signed form)."""
    member = await get_scoped_or_404(db, Member, member_id, user)
    consent = MediaConsent(
        member_id=member.id,
        **body.model_dump(),
        signed_at=utcnow(),
        recorded_by=user.id,
        notes="Recorded at the front desk",
    )
    db.add(consent)
    member.media_consent = body.social_media or body.website_marketing
    audit(db, user, "consent_recorded", "member", member.id)
    await db.commit()
    return consent


__all__ = ["consent_rows", "router", "rules_signed"]

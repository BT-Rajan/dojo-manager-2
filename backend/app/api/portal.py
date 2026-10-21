"""Member and parent portal API. Families sign in with their mobile number and a 4-digit code
sent by WhatsApp; no passwords.

Security:
- the same answer whether or not the number is registered (no account discovery);
- codes are stored only as keyed hashes, expire after 5 minutes and allow 5 attempts;
- at most 3 codes per number per 15 minutes and 10 per address per hour;
- the portal has its own cookie and session table: a portal session never reaches the staff
  API, and a signed-in family only ever sees its own members."""

import hashlib
import hmac
import secrets
from datetime import timedelta
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import today as academy_today
from app.core.config import get_settings
from app.core.deps import DB, utcnow
from app.core.mobile import normalize_kuwait_mobile
from app.core.ratelimit import SlidingWindowLimiter
from app.core.security import hash_token, new_session_token
from app.models import (
    BeltRank,
    Branch,
    ClassSession,
    MembershipPlan,
    PortalCode,
    PortalSession,
    Program,
    RenewalPayment,
)
from app.schemas.portal import (
    BookIn,
    BookOut,
    CompleteIn,
    FamilyMemberOut,
    FreezeIn,
    MemberDetailOut,
    PortalMe,
    RenewalOut,
    RenewIn,
    RenewOut,
    SendCodeIn,
    SendCodeOut,
    VerifyIn,
)
from app.services import portal as ps
from app.services.audit import audit
from app.services.messaging import last_message_to, send_message

router = APIRouter(prefix="/portal", tags=["portal"])

ip_limiter = SlidingWindowLimiter(10, 3600)
number_limiter = SlidingWindowLimiter(3, 900)

TEXT = {
    "bad_number": (
        "Please enter an 8-digit Kuwaiti number.",
        "يرجى إدخال رقم كويتي من 8 أرقام.",
    ),
    "bad_code": (
        "That code doesn't match. Check the latest message and try again.",
        "الرمز غير صحيح. تحقق من آخر رسالة وحاول مجدداً.",
    ),
    "expired": (
        "That code has expired. We've sent you a new one.",
        "انتهت صلاحية الرمز. أرسلنا لك رمزاً جديداً.",
    ),
    "too_many": (
        "Too many attempts. Please wait 15 minutes, or WhatsApp your branch.",
        "محاولات كثيرة. يرجى الانتظار 15 دقيقة أو مراسلة الفرع عبر واتساب.",
    ),
    "sms": (
        "Your Elite Academy sign-in code is {code}. It expires in 5 minutes.",
        "رمز الدخول إلى أكاديمية إيليت هو {code}. صالح لمدة 5 دقائق.",
    ),
}


def tr(key: str, lang: str, **kw) -> str:
    en, ar = TEXT[key]
    return (ar if lang == "ar" else en).format(**kw)


@lru_cache
def _code_key() -> bytes:
    secret = get_settings().portal_secret
    return secret.get_secret_value().encode() if secret else secrets.token_bytes(32)


def hash_code(mobile: str, code: str) -> str:
    return hmac.new(_code_key(), f"{mobile}:{code}".encode(), hashlib.sha256).hexdigest()


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _show_test_messages() -> bool:
    s = get_settings()
    return s.messaging_backend == "console" and s.environment != "production"


# ---------------------------------------------------------------- session
async def get_portal_session(request: Request, db: DB) -> PortalSession:
    token = request.cookies.get(get_settings().portal_cookie_name)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    row = await db.scalar(
        select(PortalSession).where(PortalSession.token_hash == hash_token(token))
    )
    if row is None or row.expires_at <= utcnow():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
    return row


Family = Annotated[PortalSession, Depends(get_portal_session)]


# ---------------------------------------------------------------- sign-in
async def _issue_code(db: AsyncSession, mobile: str, lang: str) -> bool:
    """Send a new code if the number belongs to a family; silently nothing otherwise."""
    profile, _ = await ps.find_account(db, mobile)
    if profile is None:
        return False
    code = f"{secrets.randbelow(10000):04d}"
    # Only the newest code works.
    await db.execute(
        delete(PortalCode).where(PortalCode.mobile == mobile, PortalCode.used_at.is_(None))
    )
    db.add(PortalCode(mobile=mobile, code_hash=hash_code(mobile, code)))
    await send_message(db, mobile, tr("sms", lang, code=code), kind="sign_in_code")
    return True


def _test_message(mobile: str) -> str | None:
    if not _show_test_messages():
        return None
    msg = last_message_to(mobile, "sign_in_code")
    return msg["text"] if msg else None


@router.post("/send-code", response_model=SendCodeOut)
async def send_code(body: SendCodeIn, request: Request, db: DB) -> dict:
    try:
        mobile = normalize_kuwait_mobile(body.mobile)
    except ValueError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, tr("bad_number", body.lang)
        ) from None
    ip_key, num_key = f"ip:{_client_ip(request)}", f"num:{mobile}"
    if ip_limiter.is_blocked(ip_key) or number_limiter.is_blocked(num_key):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, tr("too_many", body.lang))
    ip_limiter.hit(ip_key)
    number_limiter.hit(num_key)
    sent = await _issue_code(db, mobile, body.lang)
    audit(db, None, "portal_code_requested", "mobile", None, mobile=mobile[-4:])
    await db.commit()
    return {"mobile": mobile, "test_message": _test_message(mobile) if sent else None}


@router.post("/verify", response_model=PortalMe)
async def verify(body: VerifyIn, request: Request, response: Response, db: DB) -> dict:
    s = get_settings()
    try:
        mobile = normalize_kuwait_mobile(body.mobile)
    except ValueError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, tr("bad_number", body.lang)
        ) from None
    record = await db.scalar(
        select(PortalCode)
        .where(PortalCode.mobile == mobile, PortalCode.used_at.is_(None))
        .order_by(PortalCode.id.desc())
        .limit(1)
        .with_for_update()
    )
    if record is None or record.attempts >= s.portal_code_max_attempts:
        key = "too_many" if record else "bad_code"
        raise HTTPException(status.HTTP_400_BAD_REQUEST, tr(key, body.lang))
    now = utcnow()
    if (now - record.created_at).total_seconds() > s.portal_code_ttl_seconds:
        # Send a fresh code (it replaces this one), within the same limits as asking for one.
        num_key = f"num:{mobile}"
        sent = False
        if not number_limiter.is_blocked(num_key):
            number_limiter.hit(num_key)
            sent = await _issue_code(db, mobile, body.lang)
        if not sent:
            record.used_at = now
        await db.commit()
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            {
                "message": tr("expired", body.lang),
                "test_message": _test_message(mobile) if sent else None,
            },
        )
    if not hmac.compare_digest(record.code_hash, hash_code(mobile, body.code)):
        record.attempts += 1
        audit(db, None, "portal_code_failed", "mobile", None, mobile=mobile[-4:])
        await db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, tr("bad_code", body.lang))

    record.used_at = now
    profile, kind = await ps.find_account(db, mobile)
    if profile is None:
        await db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, tr("bad_code", body.lang))
    token = new_session_token()
    session = PortalSession(
        token_hash=hash_token(token),
        mobile=mobile,
        guardian_id=profile.id if kind == "guardian" else None,
        member_id=profile.id if kind == "member" else None,
        created_at=now,
        expires_at=now + timedelta(hours=s.portal_session_ttl_hours),
        ip_address=_client_ip(request)[:45],
        user_agent=(request.headers.get("user-agent") or "")[:255],
    )
    db.add(session)
    await db.execute(delete(PortalSession).where(PortalSession.expires_at <= now))
    number_limiter.reset(f"num:{mobile}")
    audit(db, None, "portal_login", kind, profile.id)
    await db.commit()
    response.set_cookie(
        s.portal_cookie_name,
        token,
        max_age=s.portal_session_ttl_hours * 3600,
        httponly=True,
        secure=s.cookie_secure,
        samesite="lax",
        path="/",
    )
    return {"kind": kind, "name": await ps.profile_name(db, session), "mobile": mobile}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, db: DB) -> None:
    s = get_settings()
    token = request.cookies.get(s.portal_cookie_name)
    if token:
        row = await db.scalar(
            select(PortalSession).where(PortalSession.token_hash == hash_token(token))
        )
        if row is not None:
            kind = "guardian" if row.guardian_id else "member"
            audit(db, None, "portal_logout", kind, row.guardian_id or row.member_id)
            await db.delete(row)
            await db.commit()
    response.delete_cookie(s.portal_cookie_name, path="/", secure=s.cookie_secure, httponly=True)


@router.get("/me", response_model=PortalMe)
async def me(session: Family, db: DB) -> dict:
    return {
        "kind": "guardian" if session.guardian_id else "member",
        "name": await ps.profile_name(db, session),
        "mobile": session.mobile,
    }


# ---------------------------------------------------------------- family
async def _class_title(db: AsyncSession, s: ClassSession) -> str:
    if s.title:
        return s.title
    program = await db.get(Program, s.program_id)
    return program.name if program else "Class"


@router.get("/family", response_model=list[FamilyMemberOut])
async def family(session: Family, db: DB) -> list[dict]:
    """Each member's belt, membership and next class."""
    today = academy_today()
    belts = list(await db.scalars(select(BeltRank).order_by(BeltRank.sort_order)))
    rows = []
    for m in await ps.family(db, session):
        branch = await db.get(Branch, m.branch_id)
        info = await ps.member_status(db, m, today)
        nxt = await ps.next_class(db, m)
        rank = None
        if m.belt_rank_id:
            idx = next((i for i, b in enumerate(belts) if b.id == m.belt_rank_id), None)
            if idx is not None:
                rank = {
                    "belt": belts[idx],
                    "stripes": m.stripes,
                    "next_belt": belts[idx + 1] if idx + 1 < len(belts) else None,
                }
        ms = info.membership
        rows.append(
            {
                "id": m.id,
                "first_name": m.first_name,
                "last_name": m.last_name,
                "branch_id": m.branch_id,
                "branch_name": branch.name,
                "branch_code": branch.code,
                "rank": rank,
                "next_class": {
                    "session_id": nxt.id,
                    "session_date": nxt.session_date,
                    "start_time": nxt.start_time,
                    "end_time": nxt.end_time,
                    "title": await _class_title(db, nxt),
                }
                if nxt
                else None,
                "membership": {
                    "id": ms.id,
                    "plan_name": ms.plan.name,
                    "start_date": ms.start_date,
                    "end_date": ms.end_date,
                    "status": ms.status,
                }
                if ms
                else None,
                "status": info.code,
                "expiring": info.code in ("expiring", "expired"),
            }
        )
    return rows


# ---------------------------------------------------------------- one member's page
def _membership_brief(ms) -> dict | None:
    if ms is None:
        return None
    return {
        "id": ms.id,
        "plan_name": ms.plan.name,
        "start_date": ms.start_date,
        "end_date": ms.end_date,
        "status": ms.status,
    }


@router.get("/members/{member_id}", response_model=MemberDetailOut)
async def member_page(member_id: int, session: Family, db: DB) -> dict:
    """Membership, this week's classes (regular, booked, or bookable) and recent attendance."""
    member = await ps.member_for(db, session, member_id)
    branch = await db.get(Branch, member.branch_id)
    info = await ps.member_status(db, member, academy_today())
    classes = []
    for r in await ps.upcoming(db, member):
        s = r["session"]
        classes.append(
            {
                "session_id": s.id,
                "session_date": s.session_date,
                "start_time": s.start_time,
                "end_time": s.end_time,
                "title": await _class_title(db, s),
                "regular": r["regular"],
                "booking": {"status": r["booking"].status} if r["booking"] else None,
                "can_book": r["can_book"],
            }
        )
    attended = [
        {
            "session_date": s.session_date,
            "start_time": s.start_time,
            "title": await _class_title(db, s),
            "status": a.status,
        }
        for s, a in await ps.recent_attendance(db, member)
    ]
    current = await ps.current_membership(db, member)
    plan = await ps.renewal_option(db, member)
    # Freezes are about the membership running now (else the latest one).
    running = info.membership or current
    pending = await ps.pending_freeze_for(db, member)
    return {
        "member": {
            "id": member.id,
            "first_name": member.first_name,
            "last_name": member.last_name,
            "branch_name": branch.name,
            "branch_code": branch.code,
        },
        "status": info.code,
        # The latest membership, so a renewal shows its new end date straight away.
        "membership": _membership_brief(current),
        "classes": classes,
        "attendance": attended,
        "renewal": {"plan_name": plan.name, "price": plan.price} if plan else None,
        "receipts": await ps.receipts(db, member),
        "freeze": {
            "can_request": not running.freeze_used and pending is None,
            "pending": pending is not None,
            "used": running.freeze_used,
        }
        if running
        else None,
    }


@router.post("/members/{member_id}/book", response_model=BookOut)
async def book_class(member_id: int, body: BookIn, session: Family, db: DB) -> dict:
    member = await ps.member_for(db, session, member_id)
    row = await ps.book(db, session, member, body.session_id, body.lang)
    await db.commit()
    return {"status": row.status}


@router.post("/members/{member_id}/cancel", response_model=BookOut)
async def cancel_class(member_id: int, body: BookIn, session: Family, db: DB) -> dict:
    member = await ps.member_for(db, session, member_id)
    row = await ps.cancel(db, session, member, body.session_id, body.lang)
    await db.commit()
    return {"status": row.status, "late_cancellation": row.late_cancellation}


# ---------------------------------------------------------------- renewals and freezes
async def _renewal_for(db: AsyncSession, session: PortalSession, reference: str) -> RenewalPayment:
    """A renewal started by this family (found by its reference, never by id alone)."""
    payment = await db.scalar(select(RenewalPayment).where(RenewalPayment.reference == reference))
    if payment is None or (
        payment.guardian_id != session.guardian_id or payment.by_member_id != session.member_id
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Renewal not found")
    return payment


async def _renewal_out(db: AsyncSession, payment: RenewalPayment) -> dict:
    from app.models import Membership
    from app.services.payments import get_gateway

    plan = await db.get(MembershipPlan, payment.plan_id)
    ms = await db.get(Membership, payment.membership_id) if payment.membership_id else None
    gateway = get_gateway()
    test = None
    if gateway.name == "test" and payment.status == "pending":
        test = {o: gateway.signature(payment.reference, o) for o in ("approve", "decline")}
    return {
        "reference": payment.reference,
        "member_id": payment.member_id,
        "plan_name": plan.name,
        "amount": payment.amount,
        "method": payment.method,
        "status": payment.status,
        "end_date": ms.end_date if ms else None,
        "test_outcomes": test,
    }


@router.post("/members/{member_id}/renew", response_model=RenewOut)
async def renew(member_id: int, body: RenewIn, session: Family, db: DB) -> dict:
    """Start an online renewal; the family is sent to the payment page."""
    from app.services.payments import get_gateway

    member = await ps.member_for(db, session, member_id)
    payment = await ps.start_renewal(db, session, member, body.method)
    await ps.remember_language(db, session, body.lang)
    await db.commit()
    return {"reference": payment.reference, "pay_url": get_gateway().start(payment)}


@router.get("/renewals/{reference}", response_model=RenewalOut)
async def renewal(reference: str, session: Family, db: DB) -> dict:
    return await _renewal_out(db, await _renewal_for(db, session, reference))


@router.post("/renewals/{reference}/complete", response_model=RenewalOut)
async def complete_renewal(reference: str, body: CompleteIn, session: Family, db: DB) -> dict:
    """The payment page's answer. Only a correctly signed answer counts; a repeat changes
    nothing."""
    from app.services.payments import get_gateway

    payment = await _renewal_for(db, session, reference)
    paid, gateway_ref = get_gateway().verify(payment, body.outcome, body.sig)
    payment = await ps.complete_renewal(db, payment, paid, gateway_ref)
    if payment.status == "paid":
        audit(db, None, "online_renewal", "member", payment.member_id, reference=reference)
    await db.commit()
    return await _renewal_out(db, payment)


@router.post("/members/{member_id}/freeze", status_code=status.HTTP_201_CREATED)
async def request_freeze(member_id: int, body: FreezeIn, session: Family, db: DB) -> dict:
    member = await ps.member_for(db, session, member_id)
    req = await ps.request_freeze(db, member, body.start_date, body.weeks, body.reason)
    await ps.remember_language(db, session, body.lang)
    audit(db, None, "freeze_requested", "member", member.id, request_id=req.id)
    await db.commit()
    return {"id": req.id, "status": req.status}

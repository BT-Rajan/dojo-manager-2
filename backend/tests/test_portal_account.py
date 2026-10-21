import re
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.api.portal import ip_limiter, number_limiter
from app.core.clock import today
from app.core.db import get_sessionmaker
from app.models import MessageCategory, MessageLog
from app.services.messaging import clear_outbox, send_message
from tests.conftest import make_client
from tests.factories import make_member, make_program

MUM = "55551111"


@pytest.fixture(autouse=True)
def _fresh_limits():
    yield
    ip_limiter._hits.clear()
    number_limiter._hits.clear()
    clear_outbox()


async def _sign_in(mobile=MUM):
    c = make_client()
    r = await c.post("/api/portal/send-code", json={"mobile": mobile})
    code = re.search(r"\b(\d{4})\b", r.json()["test_message"]).group(1)
    r = await c.post("/api/portal/verify", json={"mobile": mobile, "code": code})
    assert r.status_code == 200, r.text
    return c


async def _family(owner, branch_id):
    kid = dict(
        guardian_name="Mariam Ali",
        guardian_phone=MUM,
        date_of_birth=str(today().replace(year=today().year - 9)),
    )
    a = await make_member(
        owner, branch_id, first="Yousef", first_name_ar="يوسف", last_name_ar="علي", **kid
    )
    b = await make_member(owner, branch_id, first="Noor", **kid)
    return a, b


async def _book_a_class(owner, c, branch_id, member, lang="en"):
    p = await make_program(owner, name="Kids Kajukenbo")
    await owner.patch(f"/api/programs/{p['id']}", json={"name_ar": "كاجوكينبو للأطفال"})
    plan = (
        await owner.post("/api/plans", json={"name": "M", "duration_days": 30, "price": "65.000"})
    ).json()
    await owner.post(
        "/api/memberships",
        json={"member_id": member["id"], "plan_id": plan["id"], "start_date": today().isoformat()},
    )
    sess = (
        await owner.post(
            "/api/sessions",
            json={
                "branch_id": branch_id,
                "program_id": p["id"],
                "session_date": (today() + timedelta(days=1)).isoformat(),
                "start_time": "17:00",
                "end_time": "18:00",
            },
        )
    ).json()
    r = await c.post(
        f"/api/portal/members/{member['id']}/book", json={"session_id": sess["id"], "lang": lang}
    )
    assert r.status_code == 200, r.text
    return sess


async def test_account_details_and_message_choices(owner, branches):
    prm = branches["promenade"]
    a, b = await _family(owner, prm)
    c = await _sign_in()
    await _book_a_class(owner, c, prm, a)

    acc = (await c.get("/api/portal/account")).json()
    assert sorted(m["first_name"] for m in acc["family"]) == ["Noor", "Yousef"]
    assert acc["mobile"] == "+96555551111" and acc["email"] is None
    assert acc["service_on"] is True and acc["broadcasts_on"] is False
    # Sign-in codes are never listed; the booking confirmation is.
    assert [m["text"] for m in acc["recent"]] == [acc["recent"][0]["text"]]
    assert "booked" in acc["recent"][0]["text"]

    bad = await c.post(
        "/api/portal/account", json={"email": "nope", "service": True, "broadcasts": False}
    )
    assert bad.status_code == 422
    r = await c.post(
        "/api/portal/account",
        json={"email": "mariam@example.com", "service": False, "broadcasts": True},
    )
    acc = r.json()
    assert acc["email"] == "mariam@example.com"
    assert acc["service_on"] is False and acc["broadcasts_on"] is True

    # Service messages are now skipped; news reaches opted-in members only.
    async with get_sessionmaker()() as db:
        await send_message(
            db, "+96555551111", "Test day soon", category=MessageCategory.SERVICE, member_id=a["id"]
        )
        await send_message(
            db,
            "+96555551111",
            "Summer camp!",
            category=MessageCategory.MARKETING,
            member_id=a["id"],
        )
        await send_message(
            db, "+96599999999", "Offer", category=MessageCategory.MARKETING, member_id=None
        )
        await db.commit()
        rows = {
            m.text: m.status
            for m in await db.scalars(select(MessageLog).where(MessageLog.kind == ""))
        }
    assert rows == {"Test day soon": "skipped", "Summer camp!": "sent", "Offer": "skipped"}
    texts = [m["text"] for m in (await c.get("/api/portal/account")).json()["recent"]]
    assert "Summer camp!" in texts and "Test day soon" not in texts

    # The desk sees the same choices and the messages, and can record a change.
    choices = (await owner.get(f"/api/members/{b['id']}/message-choices")).json()
    assert choices["service_on"] is False and choices["broadcasts_on"] is True
    assert choices["history"][0]["source"] == "portal"
    r = await owner.post(f"/api/members/{b['id']}/message-choices", json={"broadcasts_on": False})
    assert r.json()["broadcasts_on"] is False and r.json()["history"][0]["source"] == "desk"
    log = (await owner.get(f"/api/members/{a['id']}/messages")).json()
    assert any("booked" in m["text"] for m in log)
    assert all(m["kind"] != "sign_in_code" for m in log)
    await c.aclose()


async def test_arabic_names_in_the_portal_and_messages(owner, branches):
    prm = branches["promenade"]
    await owner.patch(f"/api/branches/{prm}", json={"name_ar": "البروميناد"})
    a, _ = await _family(owner, prm)
    c = await _sign_in()
    sess = await _book_a_class(owner, c, prm, a, lang="ar")
    fam = {m["id"]: m for m in (await c.get("/api/portal/family")).json()}
    assert fam[a["id"]]["first_name_ar"] == "يوسف"
    assert fam[a["id"]]["branch_name_ar"] == "البروميناد"
    assert fam[a["id"]]["next_class"]["title_ar"] == "كاجوكينبو للأطفال"
    page = (await c.get(f"/api/portal/members/{a['id']}")).json()
    assert page["member"]["last_name_ar"] == "علي"
    assert page["classes"][0]["session_id"] == sess["id"]
    async with get_sessionmaker()() as db:
        msg = await db.scalar(
            select(MessageLog).where(MessageLog.kind == "booking_confirmed").limit(1)
        )
    assert "يوسف علي" in msg.text and "كاجوكينبو للأطفال" in msg.text
    await c.aclose()


async def test_guardian_arabic_name(owner, branches):
    prm = branches["promenade"]
    a, _ = await _family(owner, prm)
    gid = (await owner.get(f"/api/members/{a['id']}/guardians")).json()[0]["guardian_id"]
    r = await owner.patch(
        f"/api/members/{a['id']}/guardians/{gid}", json={"full_name_ar": "مريم علي"}
    )
    assert r.json()["full_name_ar"] == "مريم علي"
    c = await _sign_in()
    me = (await c.get("/api/portal/me")).json()
    assert me["name"] == "Mariam Ali" and me["name_ar"] == "مريم علي"
    await c.aclose()

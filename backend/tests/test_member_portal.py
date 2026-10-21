import re
from datetime import timedelta

import pytest
from sqlalchemy import update

from app.api.portal import ip_limiter, number_limiter
from app.core.clock import today
from app.core.db import get_sessionmaker
from app.models import PortalCode
from app.models.base import utcnow
from app.services.messaging import clear_outbox
from tests.conftest import make_client
from tests.factories import make_member, make_plan, make_program

MUM = "55551111"


@pytest.fixture(autouse=True)
def _fresh_limits():
    yield
    ip_limiter._hits.clear()
    number_limiter._hits.clear()
    clear_outbox()


async def _child(owner, branch_id, first="Yousef", parent_phone=MUM, **kw):
    return await make_member(
        owner,
        branch_id,
        first=first,
        last="Ali",
        guardian_name="Mariam Ali",
        guardian_phone=parent_phone,
        date_of_birth=str(today().replace(year=today().year - 9)),
        **kw,
    )


async def _sign_in(mobile=MUM):
    """A portal client signed in with the code from the (console) WhatsApp message."""
    c = make_client()
    r = await c.post("/api/portal/send-code", json={"mobile": mobile})
    assert r.status_code == 200, r.text
    code = re.search(r"\b(\d{4})\b", r.json()["test_message"]).group(1)
    r = await c.post("/api/portal/verify", json={"mobile": mobile, "code": code})
    assert r.status_code == 200, r.text
    return c


async def test_parent_signs_in_and_sees_only_their_family(owner, branches):
    prm = branches["promenade"]
    a = await _child(owner, prm, "Yousef")
    b = await _child(owner, prm, "Noor")
    await _child(owner, prm, "Other", parent_phone="99887766")

    c = await _sign_in()
    me = (await c.get("/api/portal/me")).json()
    assert me == {"kind": "guardian", "name": "Mariam Ali", "mobile": "+96555551111"}
    family = (await c.get("/api/portal/family")).json()
    assert sorted(m["id"] for m in family) == sorted([a["id"], b["id"]])
    assert family[0]["branch_name"] == "Promenade"
    # The portal session is not a staff session.
    assert (await c.get("/api/members")).status_code == 401
    r = await c.post("/api/portal/logout")
    assert r.status_code == 204
    assert (await c.get("/api/portal/family")).status_code == 401
    await c.aclose()


async def test_unknown_number_gets_the_same_answer(anon):
    r = await anon.post("/api/portal/send-code", json={"mobile": "6123 4567"})
    assert r.status_code == 200
    assert r.json() == {"mobile": "+96561234567", "test_message": None}
    r = await anon.post("/api/portal/verify", json={"mobile": "61234567", "code": "1234"})
    assert r.status_code == 400
    r = await anon.post("/api/portal/send-code", json={"mobile": "1234"})
    assert r.status_code == 422 and "8-digit" in r.json()["detail"]
    r = await anon.post("/api/portal/send-code", json={"mobile": "1234", "lang": "ar"})
    assert "كويتي" in r.json()["detail"]


async def test_arabic_digits_and_formats_are_accepted(owner, branches, anon):
    await _child(owner, branches["promenade"])
    for typed in ("+965 5555 1111", "٥٥٥٥١١١١", "00965-55551111"):
        r = await anon.post("/api/portal/send-code", json={"mobile": typed})
        assert r.json()["mobile"] == "+96555551111"
        number_limiter._hits.clear()


async def test_wrong_codes_lock_after_five_attempts(owner, branches, anon):
    await _child(owner, branches["promenade"])
    r = await anon.post("/api/portal/send-code", json={"mobile": MUM})
    code = re.search(r"\b(\d{4})\b", r.json()["test_message"]).group(1)
    wrong = f"{(int(code) + 1) % 10000:04d}"
    for _ in range(5):
        r = await anon.post("/api/portal/verify", json={"mobile": MUM, "code": wrong})
        assert r.status_code == 400 and "doesn't match" in r.json()["detail"]
    r = await anon.post("/api/portal/verify", json={"mobile": MUM, "code": code})
    assert r.status_code == 400 and "Too many" in r.json()["detail"]


async def test_three_codes_per_number_then_wait(owner, branches, anon):
    await _child(owner, branches["promenade"])
    for _ in range(3):
        assert (await anon.post("/api/portal/send-code", json={"mobile": MUM})).status_code == 200
    r = await anon.post("/api/portal/send-code", json={"mobile": MUM})
    assert r.status_code == 429


async def test_expired_code_sends_a_new_one(owner, branches, anon):
    await _child(owner, branches["promenade"])
    r = await anon.post("/api/portal/send-code", json={"mobile": MUM})
    old = re.search(r"\b(\d{4})\b", r.json()["test_message"]).group(1)
    async with get_sessionmaker()() as db:
        await db.execute(update(PortalCode).values(created_at=utcnow() - timedelta(minutes=6)))
        await db.commit()
    r = await anon.post("/api/portal/verify", json={"mobile": MUM, "code": old})
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "expired" in detail["message"]
    new = re.search(r"\b(\d{4})\b", detail["test_message"]).group(1)
    r = await anon.post("/api/portal/verify", json={"mobile": MUM, "code": new})
    assert r.status_code == 200


async def test_adult_member_signs_in_with_own_mobile(owner, branches):
    prm = branches["promenade"]
    adult = await make_member(owner, prm, first="Fahad", phone="9666 1234")
    # A child's own phone does not open the portal: their parent signs in.
    await make_member(
        owner,
        prm,
        first="Kid",
        phone="96661235",
        date_of_birth=str(today().replace(year=today().year - 10)),
    )
    c = await _sign_in("96661234")
    me = (await c.get("/api/portal/me")).json()
    assert me["kind"] == "member" and me["name"] == "Fahad Ali"
    assert [m["id"] for m in (await c.get("/api/portal/family")).json()] == [adult["id"]]
    await c.aclose()
    anon = make_client()
    r = await anon.post("/api/portal/send-code", json={"mobile": "96661235"})
    assert r.json()["test_message"] is None
    await anon.aclose()


async def test_family_card_status_and_next_class(owner, branches):
    prm = branches["promenade"]
    child = await _child(owner, prm)
    plan = await make_plan(owner, days=30)
    c = await _sign_in()
    row = (await c.get("/api/portal/family")).json()[0]
    assert row["status"] == "none" and row["membership"] is None and row["next_class"] is None

    start = today() - timedelta(days=27)
    r = await owner.post(
        "/api/memberships",
        json={"member_id": child["id"], "plan_id": plan["id"], "start_date": start.isoformat()},
    )
    assert r.status_code == 201, r.text
    row = (await c.get("/api/portal/family")).json()[0]
    assert row["status"] == "expiring" and row["expiring"] is True
    assert row["membership"]["plan_name"] == plan["name"]

    p = await make_program(owner)
    day = today() + timedelta(days=2)
    sess = (
        await owner.post(
            "/api/sessions",
            json={
                "branch_id": prm,
                "program_id": p["id"],
                "session_date": day.isoformat(),
                "start_time": "17:00",
                "end_time": "18:00",
            },
        )
    ).json()
    await owner.post(
        f"/api/sessions/{sess['id']}/attendance",
        json={"entries": [{"member_id": child["id"], "status": "booked"}]},
    )
    row = (await c.get("/api/portal/family")).json()[0]
    assert row["next_class"]["session_id"] == sess["id"]
    assert row["next_class"]["title"] == p["name"]
    await c.aclose()


async def test_staff_manage_family_links(owner, promenade_admin, bedaya_admin, branches):
    prm = branches["promenade"]
    a = await _child(owner, prm, "Yousef")
    b = await _child(owner, prm, "Noor")
    # Registering both children with the same parent mobile made one family.
    links = (await promenade_admin.get(f"/api/members/{a['id']}/guardians")).json()
    assert len(links) == 1 and links[0]["other_member_ids"] == [b["id"]]
    gid = links[0]["guardian_id"]
    # Branch isolation applies.
    assert (await bedaya_admin.get(f"/api/members/{a['id']}/guardians")).status_code == 404

    body = {"full_name": "Khalid Ali", "mobile": "6000 1111", "relationship": "father"}
    r = await promenade_admin.post(
        f"/api/members/{a['id']}/guardians", json=body | {"is_primary": True}
    )
    assert r.status_code == 201, r.text
    dad = r.json()["guardian_id"]
    links = (await promenade_admin.get(f"/api/members/{a['id']}/guardians")).json()
    assert [(link["guardian_id"], link["is_primary"]) for link in links] == [
        (dad, True),
        (gid, False),
    ]
    r = await promenade_admin.post(f"/api/members/{a['id']}/guardians", json=body)
    assert r.status_code == 409
    bad = body | {"mobile": "123"}
    assert (
        await promenade_admin.post(f"/api/members/{b['id']}/guardians", json=bad)
    ).status_code == 422

    # Dad can now sign in and sees only Yousef.
    c = await _sign_in("60001111")
    assert [m["id"] for m in (await c.get("/api/portal/family")).json()] == [a["id"]]
    await c.aclose()

    r = await promenade_admin.patch(f"/api/members/{a['id']}/guardians/{dad}", json={"mobile": MUM})
    assert r.status_code == 409
    # Unlinking the last member removes the guardian; they can no longer get a code.
    assert (
        await promenade_admin.delete(f"/api/members/{a['id']}/guardians/{dad}")
    ).status_code == 204
    anon = make_client()
    r = await anon.post("/api/portal/send-code", json={"mobile": "60001111"})
    assert r.json()["test_message"] is None
    await anon.aclose()


async def test_changing_phone_updates_sign_in(owner, branches):
    m = await make_member(owner, branches["promenade"], first="Adult", phone="2222 3333")
    r = await owner.patch(f"/api/members/{m['id']}", json={"phone": "9000 2222"})
    assert r.status_code == 200
    c = await _sign_in("90002222")
    assert (await c.get("/api/portal/me")).json()["kind"] == "member"
    await c.aclose()

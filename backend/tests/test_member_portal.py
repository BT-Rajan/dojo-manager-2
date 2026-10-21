import re
from datetime import date, timedelta

import pytest
from sqlalchemy import select, update

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
    assert me == {
        "kind": "guardian",
        "name": "Mariam Ali",
        "name_ar": None,
        "mobile": "+96555551111",
    }
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


# ---------------------------------------------------------------- phase 2: classes and bookings
async def _messages(kind=None):
    from app.models import MessageLog

    async with get_sessionmaker()() as db:
        stmt = select(MessageLog).order_by(MessageLog.id)
        if kind:
            stmt = stmt.where(MessageLog.kind == kind)
        return list(await db.scalars(stmt))


async def _session(owner, branch_id, program_id, day, start="17:00", end="18:00", capacity=20):
    r = await owner.post(
        "/api/sessions",
        json={
            "branch_id": branch_id,
            "program_id": program_id,
            "session_date": day.isoformat(),
            "start_time": start,
            "end_time": end,
            "capacity": capacity,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _member_with_plan(owner, branch_id, program_id=None, **kw):
    child = await _child(owner, branch_id, **kw)
    body = {"name": "Monthly", "duration_days": 30, "price": "65.000"}
    if program_id:
        body["program_id"] = program_id
    plan = (await owner.post("/api/plans", json=body)).json()
    r = await owner.post(
        "/api/memberships",
        json={"member_id": child["id"], "plan_id": plan["id"], "start_date": today().isoformat()},
    )
    assert r.status_code == 201, r.text
    return child


async def test_book_and_cancel_from_the_portal(owner, branches):
    prm = branches["promenade"]
    p = await make_program(owner)
    child = await _member_with_plan(owner, prm)
    soon = await _session(owner, prm, p["id"], today() + timedelta(days=2))
    far = await _session(owner, prm, p["id"], today() + timedelta(days=9))
    await _session(owner, branches["bedaya"], p["id"], today() + timedelta(days=2))
    c = await _sign_in()

    page = (await c.get(f"/api/portal/members/{child['id']}")).json()
    assert page["status"] == "active" and page["membership"]["plan_name"] == "Monthly"
    assert [(r["session_id"], r["can_book"]) for r in page["classes"]] == [(soon["id"], True)]

    url = f"/api/portal/members/{child['id']}"
    r = await c.post(f"{url}/book", json={"session_id": soon["id"], "lang": "ar"})
    assert r.status_code == 200 and r.json()["status"] == "booked"
    sent = await _messages("booking_confirmed")
    assert sent[-1].to == "+96555551111" and "تم حجز" in sent[-1].text
    assert (await c.post(f"{url}/book", json={"session_id": soon["id"]})).status_code == 409
    # More than 7 days ahead, or at another branch, cannot be booked.
    assert (await c.post(f"{url}/book", json={"session_id": far["id"]})).status_code == 422

    page = (await c.get(url)).json()
    assert page["classes"][0]["booking"] == {"status": "booked"}
    family = (await c.get("/api/portal/family")).json()
    assert family[0]["next_class"]["session_id"] == soon["id"]

    r = await c.post(f"{url}/cancel", json={"session_id": soon["id"]})
    assert r.json() == {"status": "cancelled", "late_cancellation": False}
    assert (await c.post(f"{url}/cancel", json={"session_id": soon["id"]})).status_code == 409
    # It can be booked again after cancelling.
    r = await c.post(f"{url}/book", json={"session_id": soon["id"]})
    assert r.json()["status"] == "booked"
    await c.aclose()


async def test_late_cancellation_is_recorded(owner, branches):
    from datetime import datetime

    from app.core.clock import academy_tz

    prm = branches["promenade"]
    p = await make_program(owner)
    child = await _member_with_plan(owner, prm)
    now = datetime.now(academy_tz())
    if now.hour >= 22:
        pytest.skip("needs a class later today")
    start = f"{now.hour + 1:02d}:00"
    end = f"{now.hour + 1:02d}:50"
    sess = await _session(owner, prm, p["id"], today(), start, end)
    c = await _sign_in()
    url = f"/api/portal/members/{child['id']}"
    await c.post(f"{url}/book", json={"session_id": sess["id"]})
    r = await c.post(f"{url}/cancel", json={"session_id": sess["id"]})
    assert r.json()["late_cancellation"] is True
    await c.aclose()


async def test_full_class_waiting_list_and_promotion(owner, branches):
    prm = branches["promenade"]
    p = await make_program(owner)
    child = await _member_with_plan(owner, prm)
    other = await make_member(owner, prm, first="Other", phone="66001122")
    sess = await _session(owner, prm, p["id"], today() + timedelta(days=1), capacity=1)
    r = await owner.post(
        f"/api/sessions/{sess['id']}/attendance",
        json={"entries": [{"member_id": other["id"], "status": "booked"}]},
    )
    assert r.status_code == 200
    c = await _sign_in()
    url = f"/api/portal/members/{child['id']}"
    r = await c.post(f"{url}/book", json={"session_id": sess["id"]})
    assert r.json()["status"] == "waitlisted"
    assert "waiting list" in (await _messages("waitlisted"))[-1].text
    roster = (await owner.get(f"/api/sessions/{sess['id']}/attendance")).json()
    assert [(row["member_id"], row["status"]) for row in roster] == [
        (other["id"], "booked"),
        (child["id"], "waitlisted"),
    ]
    assert roster[1]["source"] == "portal"

    # The desk removes the other booking: the place goes to the waiting list.
    assert (
        await owner.delete(f"/api/sessions/{sess['id']}/attendance/{other['id']}")
    ).status_code == 204
    page = (await c.get(url)).json()
    assert page["classes"][0]["booking"] == {"status": "booked"}
    msg = (await _messages("waitlist_place"))[-1]
    assert msg.to == "+96555551111" and "place opened" in msg.text
    await c.aclose()


async def test_regular_class_and_membership_rules(owner, promenade_admin, branches):
    prm = branches["promenade"]
    kids = await make_program(owner, name="Kids Kajukenbo")
    adults = await make_program(owner, name="Adult BJJ")
    # The plan covers only the kids programme.
    child = await _member_with_plan(owner, prm, program_id=kids["id"])
    day = today() + timedelta(days=3)
    sched = (
        await owner.post(
            "/api/schedules",
            json={
                "branch_id": prm,
                "program_id": kids["id"],
                "weekday": day.isoweekday(),
                "start_time": "16:00",
                "end_time": "17:00",
                "capacity": 1,
            },
        )
    ).json()
    url = f"/api/members/{child['id']}/enrollments"
    r = await promenade_admin.post(url, json={"schedule_id": sched["id"]})
    assert r.status_code == 201, r.text
    assert (await promenade_admin.post(url, json={"schedule_id": sched["id"]})).status_code == 409
    gen = {"branch_id": prm, "date_from": day.isoformat(), "date_to": day.isoformat()}
    await owner.post("/api/sessions/generate", json=gen)
    params = {"date_from": day.isoformat(), "date_to": day.isoformat(), "branch_id": prm}
    regular_sess = (await owner.get("/api/sessions", params=params)).json()[0]
    # The regular member takes the only place.
    assert regular_sess["booked"] == 1
    adult_sess = await _session(owner, prm, adults["id"], day, "18:00", "19:00")

    c = await _sign_in()
    purl = f"/api/portal/members/{child['id']}"
    page = (await c.get(purl)).json()
    assert [(r["session_id"], r["regular"], r["can_book"]) for r in page["classes"]] == [
        (regular_sess["id"], True, False)
    ]
    assert (
        await c.post(f"{purl}/book", json={"session_id": regular_sess["id"]})
    ).status_code == 409
    r = await c.post(f"{purl}/book", json={"session_id": adult_sess["id"]})
    assert r.status_code == 422 and "doesn't cover" in r.json()["detail"]
    family = (await c.get("/api/portal/family")).json()
    assert family[0]["next_class"]["session_id"] == regular_sess["id"]

    # The class roster lists the regular before anyone has checked in.
    roster = (await owner.get(f"/api/sessions/{regular_sess['id']}/attendance")).json()
    assert roster[0]["id"] is None and roster[0]["is_regular"] is True
    # A full class sends a desk booking over capacity back.
    other = await make_member(owner, prm, first="Other", phone="66001122")
    r = await owner.post(
        f"/api/sessions/{regular_sess['id']}/attendance",
        json={"entries": [{"member_id": other["id"], "status": "booked"}]},
    )
    assert r.status_code == 409

    enrollments = (await promenade_admin.get(url)).json()
    r = await promenade_admin.post(f"/api/enrollments/{enrollments[0]['id']}/end", json={})
    assert r.status_code == 200 and r.json()["is_active"] is True  # ends today, still today
    await c.aclose()


async def test_portal_cannot_reach_another_family(owner, branches):
    prm = branches["promenade"]
    p = await make_program(owner)
    mine = await _member_with_plan(owner, prm)
    theirs = await _member_with_plan(owner, prm, first="Stranger", parent_phone="99887766")
    sess = await _session(owner, prm, p["id"], today() + timedelta(days=1))
    c = await _sign_in()
    assert (await c.get(f"/api/portal/members/{theirs['id']}")).status_code == 404
    r = await c.post(f"/api/portal/members/{theirs['id']}/book", json={"session_id": sess["id"]})
    assert r.status_code == 404
    assert (await c.get(f"/api/portal/members/{mine['id']}")).status_code == 200
    await c.aclose()


async def test_recent_attendance_shows_visits(owner, branches):
    prm = branches["promenade"]
    p = await make_program(owner)
    child = await _member_with_plan(owner, prm)
    past = await _session(owner, prm, p["id"], today() - timedelta(days=2))
    await owner.post(
        f"/api/sessions/{past['id']}/attendance",
        json={"entries": [{"member_id": child["id"], "status": "present"}]},
    )
    c = await _sign_in()
    page = (await c.get(f"/api/portal/members/{child['id']}")).json()
    assert [a["session_date"] for a in page["attendance"]] == [past["session_date"]]
    await c.aclose()


# ---------------------------------------------------------------- phase 3: renewals and freezes
async def _paid_member(owner, branch_id, days=30, **kw):
    child = await _child(owner, branch_id, **kw)
    plan = (
        await owner.post(
            "/api/plans", json={"name": "Monthly", "duration_days": days, "price": "65.000"}
        )
    ).json()
    r = await owner.post(
        "/api/memberships",
        json={
            "member_id": child["id"],
            "plan_id": plan["id"],
            "start_date": today().isoformat(),
            "payment": {"method": "cash"},
        },
    )
    assert r.status_code == 201, r.text
    return child, plan, r.json()


async def test_online_renewal_round_trip(owner, branches):
    prm = branches["promenade"]
    child, plan, first = await _paid_member(owner, prm)
    c = await _sign_in()
    url = f"/api/portal/members/{child['id']}"
    page = (await c.get(url)).json()
    assert page["renewal"] == {"plan_name": "Monthly", "price": "65.000"}
    assert len(page["receipts"]) == 1 and page["receipts"][0]["method"] == "cash"
    assert page["receipts"][0]["lines"][0]["description"] == "Monthly"

    # A declined payment changes nothing.
    r = (await c.post(f"{url}/renew", json={"method": "knet"})).json()
    assert r["pay_url"] == f"/portal/pay/{r['reference']}"
    info = (await c.get(f"/api/portal/renewals/{r['reference']}")).json()
    assert info["status"] == "pending" and info["amount"] == "65.000"
    sig = info["test_outcomes"]["decline"]
    done = await c.post(
        f"/api/portal/renewals/{r['reference']}/complete", json={"outcome": "decline", "sig": sig}
    )
    assert done.json()["status"] == "failed"

    r = (await c.post(f"{url}/renew", json={"method": "card", "lang": "ar"})).json()
    ref = r["reference"]
    info = (await c.get(f"/api/portal/renewals/{ref}")).json()
    # A forged answer is not a payment.
    bad = await c.post(
        f"/api/portal/renewals/{ref}/complete", json={"outcome": "approve", "sig": "x" * 32}
    )
    assert bad.json()["status"] == "failed"
    r = (await c.post(f"{url}/renew", json={"method": "card", "lang": "ar"})).json()
    ref = r["reference"]
    sig = (await c.get(f"/api/portal/renewals/{ref}")).json()["test_outcomes"]["approve"]
    done = await c.post(
        f"/api/portal/renewals/{ref}/complete", json={"outcome": "approve", "sig": sig}
    )
    body = done.json()
    assert body["status"] == "paid" and body["test_outcomes"] is None
    # The new period starts the day after the current one ends.
    assert body["end_date"] == (today() + timedelta(days=59)).isoformat()
    again = await c.post(
        f"/api/portal/renewals/{ref}/complete", json={"outcome": "approve", "sig": sig}
    )
    assert again.json()["status"] == "paid"
    memberships = (await owner.get(f"/api/members/{child['id']}/memberships")).json()
    assert len(memberships) == 2
    payments = (await owner.get("/api/payments", params={"member_id": child["id"]})).json()
    renewal = [p for p in payments if p["method"] == "card"]
    assert len(renewal) == 1 and renewal[0]["category"] == "renewal"
    assert renewal[0]["reference"] == f"TEST-{ref}"
    msg = (await _messages("renewal_paid"))[-1]
    assert msg.to == "+96555551111" and "تم تجديد" in msg.text
    # The receipt number in the message is the payment's receipt.
    assert f"PRM-R{renewal[0]['id']:06d}" in msg.text
    page = (await c.get(url)).json()
    assert len(page["receipts"]) == 2
    assert page["membership"]["end_date"] == body["end_date"]

    # Another family cannot see or complete it.
    await _child(owner, prm, "Stranger", parent_phone="99887766")
    other = await _sign_in("99887766")
    assert (await other.get(f"/api/portal/renewals/{ref}")).status_code == 404
    await other.aclose()
    await c.aclose()


async def test_no_online_renewal_when_plan_withdrawn_or_test_gateway_in_production(
    owner, branches, monkeypatch
):
    from app.core.config import get_settings

    child, plan, _ = await _paid_member(owner, branches["promenade"])
    c = await _sign_in()
    url = f"/api/portal/members/{child['id']}"
    monkeypatch.setattr(get_settings(), "environment", "production")
    assert (await c.get(url)).json()["renewal"] is None
    monkeypatch.undo()
    await owner.patch(f"/api/plans/{plan['id']}", json={"is_active": False})
    assert (await c.get(url)).json()["renewal"] is None
    r = await c.post(f"{url}/renew", json={"method": "knet"})
    assert r.status_code == 422 and "can't be renewed online" in r.json()["detail"]
    await c.aclose()


async def test_freeze_request_and_decision(owner, manager, promenade_admin, branches):
    prm = branches["promenade"]
    child, plan, ms = await _paid_member(owner, prm)
    c = await _sign_in()
    url = f"/api/portal/members/{child['id']}"
    body = {"start_date": today().isoformat(), "weeks": 2, "reason": "Travelling"}
    assert (await c.post(f"{url}/freeze", json=body | {"weeks": 5})).status_code == 422
    past = (today() - timedelta(days=1)).isoformat()
    assert (await c.post(f"{url}/freeze", json=body | {"start_date": past})).status_code == 422
    r = await c.post(f"{url}/freeze", json=body)
    assert r.status_code == 201, r.text
    assert (await c.post(f"{url}/freeze", json=body)).status_code == 409
    page = (await c.get(url)).json()
    assert page["freeze"] == {"can_request": False, "pending": True, "used": False}

    reqs = (
        await promenade_admin.get("/api/membership-requests", params={"status": "pending"})
    ).json()
    assert len(reqs) == 1 and reqs[0]["from_portal"] is True
    assert reqs[0]["reason"] == "(Requested in the portal) Travelling"
    rid = reqs[0]["id"]
    # Front desk cannot decide; the operations manager does.
    decision = f"/api/membership-requests/{rid}/decision"
    assert (await promenade_admin.post(decision, json={"approve": True})).status_code == 403
    r = await manager.post(decision, json={"approve": True, "note": "OK"})
    assert r.status_code == 200 and r.json()["status"] == "approved"
    assert (await manager.post(decision, json={"approve": False})).status_code == 409

    memberships = (await owner.get(f"/api/members/{child['id']}/memberships")).json()
    assert memberships[0]["end_date"] == (today() + timedelta(days=29 + 14)).isoformat()
    page = (await c.get(url)).json()
    assert page["status"] == "frozen"
    assert page["freeze"] == {"can_request": False, "pending": False, "used": True}
    family = (await c.get("/api/portal/family")).json()
    assert family[0]["status"] == "frozen"
    # Frozen: no classes to book this week.
    p = await make_program(owner)
    await _session(owner, prm, p["id"], today() + timedelta(days=1))
    assert (await c.get(url)).json()["classes"] == []
    # Once per membership.
    later = (today() + timedelta(days=20)).isoformat()
    r = await c.post(f"{url}/freeze", json=body | {"start_date": later})
    assert r.status_code == 409 and "already been frozen" in r.json()["detail"]
    await c.aclose()


async def test_rejected_freeze_changes_nothing(owner, manager, branches):
    child, plan, ms = await _paid_member(owner, branches["promenade"])
    c = await _sign_in()
    url = f"/api/portal/members/{child['id']}"
    start = (today() + timedelta(days=3)).isoformat()
    await c.post(f"{url}/freeze", json={"start_date": start, "weeks": 1, "reason": "Exams"})
    rid = (await manager.get("/api/membership-requests")).json()[0]["id"]
    r = await manager.post(f"/api/membership-requests/{rid}/decision", json={"approve": False})
    assert r.json()["status"] == "rejected"
    page = (await c.get(url)).json()
    assert page["status"] == "active"
    assert page["freeze"] == {"can_request": True, "pending": False, "used": False}
    await c.aclose()


async def test_freeze_applies_to_the_membership_running_at_its_start(owner, manager, branches):
    child, plan, first = await _paid_member(owner, branches["promenade"])
    # Renewed in advance: a second membership starts after the first ends.
    r = await owner.post("/api/memberships", json={"member_id": child["id"], "plan_id": plan["id"]})
    second = r.json()
    c = await _sign_in()
    url = f"/api/portal/members/{child['id']}"
    start = (today() + timedelta(days=5)).isoformat()
    await c.post(f"{url}/freeze", json={"start_date": start, "weeks": 1, "reason": "Trip"})
    req = (await manager.get("/api/membership-requests")).json()[0]
    assert req["membership_id"] == first["id"]
    page = (await c.get(url)).json()
    assert page["freeze"]["pending"] is True and page["freeze"]["can_request"] is False
    await manager.post(f"/api/membership-requests/{req['id']}/decision", json={"approve": True})
    memberships = {
        m["id"]: m for m in (await owner.get(f"/api/members/{child['id']}/memberships")).json()
    }
    assert memberships[first["id"]]["end_date"] == (today() + timedelta(days=36)).isoformat()
    # The membership bought for afterwards moves back by the same week.
    moved = (date.fromisoformat(second["end_date"]) + timedelta(days=7)).isoformat()
    assert memberships[second["id"]]["end_date"] == moved
    await c.aclose()

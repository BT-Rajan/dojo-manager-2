import re
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.api.portal import ip_limiter, number_limiter
from app.core.clock import today
from app.core.db import get_sessionmaker
from app.models import BeltRank, BeltSkill, MessageLog, Role
from app.seed import seed_reference
from app.services.messaging import clear_outbox
from tests.conftest import create_user, login, make_client
from tests.factories import make_belt, make_instructor, make_member, make_program

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


async def _setup(owner, branch_id):
    white = await make_belt(owner, "White", 1, color="#f5f5f5")
    yellow = await make_belt(
        owner,
        "Yellow",
        2,
        color="#facc15",
        seminars_required=1,
        min_classes=1,
        min_weeks=0,
        min_evaluations=1,
        name_ar="الحزام الأصفر",
    )
    child = await make_member(
        owner,
        branch_id,
        first="Yousef",
        guardian_name="Mariam Ali",
        guardian_phone=MUM,
        date_of_birth=str(today().replace(year=today().year - 9)),
        belt_rank_id=white["id"],
        joined_on=(today() - timedelta(days=30)).isoformat(),
    )
    return white, yellow, child


async def test_progress_from_coach_work_to_the_portal(owner, branches):
    prm = branches["promenade"]
    white, yellow, child = await _setup(owner, prm)
    s1 = (
        await owner.post(
            f"/api/belts/{white['id']}/skills",
            json={"track": "kickboxing", "category": "Strikes", "name": "Jab"},
        )
    ).json()
    await owner.post(
        f"/api/belts/{white['id']}/skills",
        json={"track": "jiujitsu", "category": "Ground Movement", "name": "Shrimp"},
    )
    c = await _sign_in()
    url = f"/api/portal/members/{child['id']}"
    prog = (await c.get(url)).json()["progress"][0]
    assert prog["belt"]["name"] == "White" and prog["next"]["name_ar"] == "الحزام الأصفر"
    assert (prog["done"], prog["total"]) == (0, 2)
    assert [ch["ok"] for ch in prog["checks"]] == [False, True, False, False, False]

    # The coach's work: a skill, a class, a seminar and a ready evaluation.
    coach_rec = await make_instructor(owner, prm, "Coach Tareq")
    await owner.post(
        f"/api/instructors/{coach_rec['id']}/portal-account",
        json={"username": "tareq", "password": "correct-horse-battery"},
    )
    coach = await login("tareq")
    r = await coach.put(f"/api/members/{child['id']}/skills/{s1['id']}", json={"checked": True})
    assert r.status_code == 204
    p = await make_program(owner)
    sess = (
        await owner.post(
            "/api/sessions",
            json={
                "branch_id": prm,
                "program_id": p["id"],
                "session_date": (today() - timedelta(days=1)).isoformat(),
                "start_time": "17:00",
                "end_time": "18:00",
            },
        )
    ).json()
    await coach.post(
        f"/api/sessions/{sess['id']}/attendance",
        json={"entries": [{"member_id": child["id"], "status": "present"}]},
    )
    sem = (
        await owner.post(
            "/api/seminars",
            json={"branch_id": prm, "title": "Self-defence", "seminar_date": today().isoformat()},
        )
    ).json()
    await owner.post(f"/api/seminars/{sem['id']}/attendees", json={"member_ids": [child["id"]]})
    r = await coach.post(
        f"/api/members/{child['id']}/evaluations",
        json={"notes": "Great guard work", "ready_for_test": True},
    )
    assert r.status_code == 201
    event = (
        await owner.post(
            "/api/gradings",
            json={
                "branch_id": prm,
                "title": "October grading",
                "event_date": (today() + timedelta(days=10)).isoformat(),
            },
        )
    ).json()
    r = await owner.post(
        f"/api/gradings/{event['id']}/results", json={"entries": [{"member_id": child["id"]}]}
    )
    assert r.status_code == 200, r.text

    prog = (await c.get(url)).json()["progress"][0]
    assert (prog["done"], prog["total"], prog["seminars"]) == (1, 2, 1)
    assert all(ch["ok"] for ch in prog["checks"])
    assert prog["evaluations"][0]["notes"] == "Great guard work"
    assert prog["evaluations"][0]["instructor_name"] == "Coach Tareq"
    assert prog["tests"][0]["title"] == "October grading"

    staff_view = (await owner.get(f"/api/members/{child['id']}/progress")).json()
    assert staff_view["eligible"] is True
    assert [s["name"] for s in staff_view["skills"] if s["checked_on"]] == ["Jab"]

    # Monthly notes reach the family only once sent.
    r = await coach.post(
        f"/api/members/{child['id']}/progress-notes",
        json={"month": today().isoformat(), "worked_on": "Jab and cross.", "next_steps": "Kicks."},
    )
    note = r.json()
    assert note["status"] == "draft"
    assert (await c.get(url)).json()["progress"][0]["notes"] == []
    r = await coach.post(f"/api/progress-notes/{note['id']}/send")
    assert r.json()["status"] == "sent"
    assert (await coach.post(f"/api/progress-notes/{note['id']}/send")).status_code == 409
    notes = (await c.get(url)).json()["progress"][0]["notes"]
    assert notes[0]["worked_on"] == "Jab and cross."
    async with get_sessionmaker()() as db:
        msg = await db.scalar(select(MessageLog).where(MessageLog.kind == "progress_note"))
    assert msg.category == "service" and msg.to == "+96555551111"
    await coach.aclose()
    await c.aclose()


async def test_photo_consent_and_rules(owner, branches):
    _, _, child = await _setup(owner, branches["promenade"])
    c = await _sign_in()
    url = f"/api/portal/members/{child['id']}"
    page = (await c.get(url)).json()
    assert page["consent"] is None and page["rules_signed"] is False
    assert page["signer"] == "Mariam Ali"

    r = await c.post(f"{url}/consent", json={"internal": True, "social": False, "website": True})
    assert r.status_code == 201
    r = await c.post(f"{url}/consent", json={"internal": True, "social": False, "website": False})
    page = (await c.get(url)).json()
    assert page["consent"] == {
        "internal_records": True,
        "social_media": False,
        "website_marketing": False,
    }
    staff = (await owner.get(f"/api/members/{child['id']}/progress")).json()
    assert len(staff["consent_history"]) == 2 and staff["consent"]["from_portal"] is True
    assert staff["consent"]["signed_by_name"] == "Mariam Ali"
    member = (await owner.get(f"/api/members/{child['id']}")).json()
    assert member["media_consent"] is False

    body = {"name": "Mariam Ali", "agree": False}
    r = await c.post(f"{url}/rules", json=body)
    assert r.status_code == 422 and "Tick" in r.json()["detail"]
    r = await c.post(f"{url}/rules", json=body | {"agree": True, "name": "Someone", "lang": "ar"})
    assert r.status_code == 422 and "اسمك" in r.json()["detail"]
    r = await c.post(f"{url}/rules", json=body | {"agree": True, "name": " mariam ali "})
    assert r.status_code == 201
    assert (await c.get(url)).json()["rules_signed"] is True
    staff = (await owner.get(f"/api/members/{child['id']}/progress")).json()
    assert staff["rules_signed"]["from_portal"] is True
    await c.aclose()


async def test_staff_record_consent_and_skills_admin(owner, promenade_admin, branches):
    white, _, child = await _setup(owner, branches["promenade"])
    r = await promenade_admin.post(
        f"/api/members/{child['id']}/consent",
        json={
            "internal_records": True,
            "social_media": True,
            "website_marketing": False,
            "signed_by_name": "Mariam Ali",
        },
    )
    assert r.status_code == 201
    member = (await owner.get(f"/api/members/{child['id']}")).json()
    assert member["media_consent"] is True
    # Only management edits the curriculum.
    body = {"track": "kickboxing", "category": "Strikes", "name": "Jab"}
    assert (
        await promenade_admin.post(f"/api/belts/{white['id']}/skills", json=body)
    ).status_code == 403
    skill = (await owner.post(f"/api/belts/{white['id']}/skills", json=body)).json()
    await owner.patch(f"/api/skills/{skill['id']}", json={"is_active": False})
    assert (await owner.get(f"/api/belts/{white['id']}/skills")).json() == []
    r = await owner.patch(f"/api/belts/{white['id']}", json={"min_classes": 30, "name_ar": "أبيض"})
    assert r.json()["min_classes"] == 30 and r.json()["name_ar"] == "أبيض"


async def test_coach_can_only_remove_own_evaluation(owner, branches):
    prm = branches["promenade"]
    _, _, child = await _setup(owner, prm)
    await create_user("coach2", Role.INSTRUCTOR, [prm])
    coach = await login("coach2")
    ev = (await owner.post(f"/api/members/{child['id']}/evaluations", json={"notes": "x"})).json()
    assert (await coach.delete(f"/api/evaluations/{ev['id']}")).status_code == 403
    assert (await owner.delete(f"/api/evaluations/{ev['id']}")).status_code == 204
    await coach.aclose()


async def test_seed_loads_the_kajukenbo_curriculum(branches):
    async with get_sessionmaker()() as db:
        await seed_reference(db)
        await db.commit()
        assert await db.scalar(select(func.count()).select_from(BeltSkill)) == 215
        yellow = await db.scalar(select(BeltRank).where(BeltRank.sort_order == 2))
        assert (yellow.min_classes, yellow.min_weeks, yellow.min_evaluations) == (24, 12, 2)
        assert yellow.name_ar == "الحزام الأصفر"

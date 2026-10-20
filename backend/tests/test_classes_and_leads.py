from datetime import date, timedelta

from app.models import Role
from tests.conftest import create_user, login
from tests.factories import make_instructor, make_member, make_plan, make_program


def next_weekday(iso: int) -> date:
    d = date.today() + timedelta(days=1)
    while d.isoweekday() != iso:
        d += timedelta(days=1)
    return d


async def _schedule(c, branch_id, program_id, instructor_id=None, weekday=1, capacity=20):
    r = await c.post(
        "/api/schedules",
        json={
            "branch_id": branch_id,
            "program_id": program_id,
            "instructor_id": instructor_id,
            "weekday": weekday,
            "start_time": "16:30",
            "end_time": "17:10",
            "capacity": capacity,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


async def test_schedule_validation(owner, branches):
    p = await make_program(owner)
    body = {
        "branch_id": branches["promenade"],
        "program_id": p["id"],
        "weekday": 8,
        "start_time": "17:00",
        "end_time": "16:00",
    }
    assert (await owner.post("/api/schedules", json=body)).status_code == 422
    body |= {"weekday": 2}
    assert (await owner.post("/api/schedules", json=body)).status_code == 422


async def test_generate_sessions_idempotent_with_leave_cover(owner, branches):
    prm = branches["promenade"]
    p = await make_program(owner)
    coach = await make_instructor(owner, prm, "Coach A")
    cover = await make_instructor(owner, prm, "Coach B")
    await _schedule(owner, prm, p["id"], coach["id"], weekday=1)
    await _schedule(owner, prm, p["id"], coach["id"], weekday=3)
    start = next_weekday(1)
    end = start + timedelta(days=13)
    r = await owner.post(
        "/api/leaves",
        json={
            "instructor_id": coach["id"],
            "start_date": start.isoformat(),
            "end_date": start.isoformat(),
            "type": "sick",
            "cover_instructor_id": cover["id"],
        },
    )
    assert r.status_code == 201
    body = {"branch_id": prm, "date_from": start.isoformat(), "date_to": end.isoformat()}
    assert (await owner.post("/api/sessions/generate", json=body)).json() == {"created": 4}
    assert (await owner.post("/api/sessions/generate", json=body)).json() == {"created": 0}
    sessions = (
        await owner.get(
            "/api/sessions", params={"date_from": start.isoformat(), "date_to": end.isoformat()}
        )
    ).json()
    assert len(sessions) == 4
    assert sessions[0]["instructor_id"] == cover["id"]
    assert {s["instructor_id"] for s in sessions[1:]} == {coach["id"]}


async def test_attendance_capacity_membership_flag_and_isolation(
    owner, promenade_admin, bedaya_admin, branches
):
    prm = branches["promenade"]
    p = await make_program(owner)
    plan = await make_plan(owner)
    sess = (
        await owner.post(
            "/api/sessions",
            json={
                "branch_id": prm,
                "program_id": p["id"],
                "session_date": date.today().isoformat(),
                "start_time": "18:00",
                "end_time": "18:40",
                "capacity": 2,
            },
        )
    ).json()
    m1 = await make_member(promenade_admin, prm, first="A")
    m2 = await make_member(promenade_admin, prm, first="B")
    m3 = await make_member(promenade_admin, prm, first="C")
    await owner.post("/api/memberships", json={"member_id": m1["id"], "plan_id": plan["id"]})

    url = f"/api/sessions/{sess['id']}/attendance"
    r = await promenade_admin.post(
        url,
        json={
            "entries": [
                {"member_id": m1["id"], "status": "present"},
                {"member_id": m2["id"], "status": "booked"},
            ]
        },
    )
    assert r.status_code == 200, r.text
    flags = {a["member_id"]: a["has_active_membership"] for a in r.json()}
    assert flags == {m1["id"]: True, m2["id"]: False}

    r = await promenade_admin.post(
        url, json={"entries": [{"member_id": m3["id"], "status": "booked"}]}
    )
    assert r.status_code == 409  # full
    # Marking someone absent frees the spot; upsert keeps one row per member.
    await promenade_admin.post(url, json={"entries": [{"member_id": m2["id"], "status": "absent"}]})
    r = await promenade_admin.post(
        url, json={"entries": [{"member_id": m3["id"], "status": "booked"}]}
    )
    assert r.status_code == 200 and len(r.json()) == 3

    assert (await bedaya_admin.get(url)).status_code == 404
    hist = (await promenade_admin.get(f"/api/members/{m1['id']}/attendance")).json()
    assert hist[0]["status"] == "present"

    listed = (
        await owner.get(
            "/api/sessions",
            params={"date_from": date.today().isoformat(), "date_to": date.today().isoformat()},
        )
    ).json()
    assert listed[0]["booked"] == 2 and listed[0]["attended"] == 1


async def test_instructor_can_mark_attendance_but_not_edit_classes(owner, branches):
    prm = branches["promenade"]
    await create_user("coach", Role.INSTRUCTOR, [prm])
    coach = await login("coach")
    p = await make_program(owner)
    m = await make_member(owner, prm)
    sess = (
        await owner.post(
            "/api/sessions",
            json={
                "branch_id": prm,
                "program_id": p["id"],
                "session_date": date.today().isoformat(),
                "start_time": "18:00",
                "end_time": "18:40",
            },
        )
    ).json()
    r = await coach.post(
        f"/api/sessions/{sess['id']}/attendance",
        json={"entries": [{"member_id": m["id"], "status": "present"}]},
    )
    assert r.status_code == 200
    r = await coach.patch(f"/api/sessions/{sess['id']}", json={"capacity": 5})
    assert r.status_code == 403
    assert (await coach.get("/api/payments")).status_code == 403
    await coach.aclose()


async def test_cancel_requires_reason(owner, branches):
    p = await make_program(owner)
    sess = (
        await owner.post(
            "/api/sessions",
            json={
                "branch_id": branches["bedaya"],
                "program_id": p["id"],
                "session_date": date.today().isoformat(),
                "start_time": "18:00",
                "end_time": "18:40",
            },
        )
    ).json()
    url = f"/api/sessions/{sess['id']}"
    assert (await owner.patch(url, json={"status": "cancelled"})).status_code == 422
    r = await owner.patch(
        url,
        json={"status": "cancelled", "change_reason": "Instructor sick", "members_notified": True},
    )
    assert r.json()["status"] == "cancelled" and r.json()["members_notified_at"]
    r = await owner.post(
        f"{url}/attendance", json={"entries": [{"member_id": 1, "status": "booked"}]}
    )
    assert r.status_code == 409


async def test_lead_pipeline(owner, promenade_admin, branches):
    prm = branches["promenade"]
    p = await make_program(owner)
    sess = (
        await owner.post(
            "/api/sessions",
            json={
                "branch_id": prm,
                "program_id": p["id"],
                "session_date": (date.today() + timedelta(days=2)).isoformat(),
                "start_time": "18:00",
                "end_time": "18:40",
            },
        )
    ).json()
    r = await promenade_admin.post(
        "/api/leads",
        json={"branch_id": prm, "full_name": "Yousef K", "phone": "55551234", "source": "whatsapp"},
    )
    assert r.status_code == 201
    lead = r.json()
    r = await promenade_admin.post(
        f"/api/leads/{lead['id']}/book-trial", json={"session_id": sess["id"]}
    )
    assert r.json()["status"] == "trial_booked"
    r = await promenade_admin.patch(f"/api/leads/{lead['id']}", json={"status": "lost"})
    assert r.status_code == 422  # needs a reason
    r = await promenade_admin.post(
        f"/api/leads/{lead['id']}/convert", json={"first_name": "Yousef", "last_name": "K"}
    )
    assert r.status_code == 201
    assert r.json()["phone"] == "55551234"
    lead = (await promenade_admin.get(f"/api/leads/{lead['id']}")).json()
    assert lead["status"] == "converted" and lead["converted_member_id"] == r.json()["id"]
    assert (await promenade_admin.get("/api/leads", params={"open_only": True})).json() == []

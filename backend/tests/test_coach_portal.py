from datetime import timedelta

from app.core.clock import today
from app.models import Role
from tests.conftest import PASSWORD, create_user, login
from tests.factories import make_instructor, make_program


async def _session(c, branch_id, program_id, instructor_id, day, start="16:30", end="17:10"):
    r = await c.post(
        "/api/sessions",
        json={
            "branch_id": branch_id,
            "program_id": program_id,
            "instructor_id": instructor_id,
            "session_date": day.isoformat(),
            "start_time": start,
            "end_time": end,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _coach_login(owner, branch_id, name="Coach Tareq", username="tareq"):
    """A coach record with a portal login, and a signed-in client for it."""
    inst = await make_instructor(owner, branch_id, name)
    r = await owner.post(
        f"/api/instructors/{inst['id']}/portal-account",
        json={"username": username, "password": PASSWORD},
    )
    assert r.status_code == 201, r.text
    return inst, await login(username)


async def test_portal_account_lifecycle(owner, manager, promenade_admin, branches):
    prm = branches["promenade"]
    inst = await make_instructor(owner, prm)
    body = {"username": "tareq", "password": PASSWORD}
    # Front-desk admins cannot hand out logins; the operations manager can.
    url = f"/api/instructors/{inst['id']}/portal-account"
    assert (await promenade_admin.post(url, json=body)).status_code == 403
    r = await manager.post(url, json=body)
    assert r.status_code == 201, r.text
    assert r.json()["username"] == "tareq" and r.json()["user_active"] is True
    assert (await manager.post(url, json=body)).status_code == 409

    access = (await manager.get("/api/instructors/portal-access", params={"branch_id": prm})).json()
    assert [a["username"] for a in access] == ["tareq"]

    coach = await login("tareq")
    me = (await coach.get("/api/auth/me")).json()
    assert me["role"] == "instructor" and [b["id"] for b in me["branches"]] == [prm]

    # Disabling signs the coach out; a reset password works once re-enabled.
    r = await manager.patch(url, json={"is_active": False})
    assert r.json()["user_active"] is False
    assert (await coach.get("/api/coach/me")).status_code == 401
    await manager.patch(url, json={"is_active": True})
    new_pw = "another-strong-password"
    r = await manager.post(f"{url}/reset-password", json={"password": new_pw})
    assert r.status_code == 204
    r = await coach.post("/api/auth/login", json={"username": "tareq", "password": new_pw})
    assert r.status_code == 200
    await coach.aclose()


async def test_portal_login_follows_branch_move(owner, branches):
    inst, coach = await _coach_login(owner, branches["promenade"])
    r = await owner.patch(f"/api/instructors/{inst['id']}", json={"branch_id": branches["bedaya"]})
    assert r.status_code == 200
    users = (await owner.get("/api/users")).json()
    tareq = next(u for u in users if u["username"] == "tareq")
    assert [b["id"] for b in tareq["branches"]] == [branches["bedaya"]]
    await coach.aclose()


async def test_coach_today_day_and_week(owner, branches):
    prm = branches["promenade"]
    p = await make_program(owner)
    inst, coach = await _coach_login(owner, prm)
    other = await make_instructor(owner, prm, "Coach Other")
    day = today()
    mine = await _session(owner, prm, p["id"], inst["id"], day, "23:00", "23:50")
    theirs = await _session(owner, prm, p["id"], other["id"], day, "18:00", "18:40")
    later = await _session(owner, prm, p["id"], inst["id"], day + timedelta(days=3))
    # Another branch's class never shows up.
    bdy_coach = await make_instructor(owner, branches["bedaya"], "Coach B")
    await _session(owner, branches["bedaya"], p["id"], bdy_coach["id"], day)

    me = (await coach.get("/api/coach/me")).json()
    assert me["id"] == inst["id"] and me["branch"]["id"] == prm
    assert me["classes_today"] == 1
    # Mine starts at 23:00, so it is next unless the tests run in the last minutes of the day.
    assert me["next_session"]["id"] in (mine["id"], later["id"])
    assert me["leave_today"] is None

    todays = (await coach.get("/api/coach/today")).json()
    assert [s["id"] for s in todays] == [mine["id"]]
    assert todays[0]["coach_role"] == "teaching"

    day_view = (await coach.get("/api/coach/day", params={"day": day.isoformat()})).json()
    assert [s["id"] for s in day_view["sessions"]] == [theirs["id"], mine["id"]]
    assert [s["coach_role"] for s in day_view["sessions"]] == [None, "teaching"]

    params = {"date_from": day.isoformat(), "date_to": (day + timedelta(days=6)).isoformat()}
    week = (await coach.get("/api/coach/sessions", params=params)).json()
    assert [s["id"] for s in week] == [mine["id"], later["id"]]
    params["date_to"] = (day + timedelta(days=120)).isoformat()
    assert (await coach.get("/api/coach/sessions", params=params)).status_code == 422
    await coach.aclose()


async def test_covering_and_covered_classes(owner, branches):
    prm = branches["promenade"]
    p = await make_program(owner)
    inst, coach = await _coach_login(owner, prm)
    cover, cover_client = await _coach_login(owner, prm, "Coach Cover", "cover")
    day = today() + timedelta(days=1)
    sess = await _session(owner, prm, p["id"], inst["id"], day)
    r = await owner.post(
        "/api/leaves",
        json={
            "instructor_id": inst["id"],
            "start_date": day.isoformat(),
            "end_date": day.isoformat(),
            "type": "sick",
            "cover_instructor_id": cover["id"],
        },
    )
    assert r.json()["sessions_reassigned"] == 1
    params = {"date_from": day.isoformat(), "date_to": day.isoformat()}
    mine = (await coach.get("/api/coach/sessions", params=params)).json()
    assert [(s["id"], s["coach_role"]) for s in mine] == [(sess["id"], "covered")]
    theirs = (await cover_client.get("/api/coach/sessions", params=params)).json()
    assert [(s["id"], s["coach_role"]) for s in theirs] == [(sess["id"], "covering")]
    day_view = (await coach.get("/api/coach/day", params={"day": day.isoformat()})).json()
    assert [lv["instructor_id"] for lv in day_view["on_leave"]] == [inst["id"]]
    await coach.aclose()
    await cover_client.aclose()


async def test_timetable_and_access_rules(owner, promenade_admin, bedaya_admin, branches):
    prm = branches["promenade"]
    p = await make_program(owner)
    inst, coach = await _coach_login(owner, prm)
    other = await make_instructor(owner, prm, "Coach Other")
    sched = {
        "branch_id": prm,
        "program_id": p["id"],
        "weekday": 6,
        "start_time": "17:00",
        "end_time": "18:00",
    }
    await owner.post("/api/schedules", json=sched | {"instructor_id": inst["id"]})
    await owner.post("/api/schedules", json=sched | {"instructor_id": other["id"], "weekday": 7})
    rows = (await coach.get("/api/coach/timetable")).json()
    assert [r["weekday"] for r in rows] == [6]

    # A coach cannot open someone else's portal.
    r = await coach.get("/api/coach/me", params={"instructor_id": other["id"]})
    assert r.status_code == 403
    # Staff open a coach's portal by id, only at their own branches.
    r = await promenade_admin.get("/api/coach/me", params={"instructor_id": inst["id"]})
    assert r.status_code == 200 and r.json()["full_name"] == "Coach Tareq"
    assert (await promenade_admin.get("/api/coach/me")).status_code == 422
    r = await bedaya_admin.get("/api/coach/me", params={"instructor_id": inst["id"]})
    assert r.status_code == 404
    # A deactivated coach profile closes the portal.
    await owner.patch(f"/api/instructors/{inst['id']}", json={"is_active": False})
    assert (await coach.get("/api/coach/me")).status_code == 403
    await coach.aclose()


async def test_instructor_without_profile(owner, branches):
    await create_user("loose", Role.INSTRUCTOR, [branches["promenade"]])
    c = await login("loose")
    r = await c.get("/api/coach/me")
    assert r.status_code == 404 and "No coach profile" in r.json()["detail"]
    await c.aclose()


# ---------------------------------------------------------------- phase 2: leave requests
async def test_leave_request_approval_and_cover(owner, promenade_admin, branches):
    prm = branches["promenade"]
    p = await make_program(owner)
    inst, coach = await _coach_login(owner, prm)
    cover = await make_instructor(owner, prm, "Coach Cover")
    day = today() + timedelta(days=2)
    sess = await _session(owner, prm, p["id"], inst["id"], day)
    body = {"start_date": day.isoformat(), "end_date": day.isoformat(), "type": "annual"}

    r = await coach.post("/api/coach/leaves", json=body | {"cover_instructor_id": cover["id"]})
    assert r.status_code == 201, r.text
    leave = r.json()
    assert leave["status"] == "pending" and leave["cover_instructor_id"] == cover["id"]
    # Pending leave changes nothing yet, and a second overlapping request is refused.
    params = {"date_from": day.isoformat(), "date_to": day.isoformat()}
    mine = (await coach.get("/api/coach/sessions", params=params)).json()
    assert mine[0]["coach_role"] == "teaching"
    assert (await coach.post("/api/coach/leaves", json=body)).status_code == 409

    pending = (await promenade_admin.get("/api/leaves", params={"status": "pending"})).json()
    assert [lv["id"] for lv in pending] == [leave["id"]]

    url = f"/api/leaves/{leave['id']}/decision"
    r = await promenade_admin.post(url, json={"approve": True, "note": "Enjoy"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved" and r.json()["sessions_reassigned"] == 1
    assert r.json()["decision_note"] == "Enjoy"
    assert (await promenade_admin.post(url, json={"approve": False})).status_code == 409

    mine = (await coach.get("/api/coach/sessions", params=params)).json()
    assert [(s["id"], s["coach_role"]) for s in mine] == [(sess["id"], "covered")]
    assert mine[0]["instructor_id"] == cover["id"]
    # Approved leave cannot be withdrawn by the coach.
    r = await coach.post(f"/api/coach/leaves/{leave['id']}/withdraw")
    assert r.status_code == 409
    # Removing approved leave hands the class back.
    assert (await promenade_admin.delete(f"/api/leaves/{leave['id']}")).status_code == 204
    mine = (await coach.get("/api/coach/sessions", params=params)).json()
    assert mine[0]["coach_role"] == "teaching"
    await coach.aclose()


async def test_leave_reject_withdraw_and_rules(owner, branches):
    prm = branches["promenade"]
    p = await make_program(owner)
    inst, coach = await _coach_login(owner, prm)
    other_branch = await make_instructor(owner, branches["bedaya"], "Coach Far")
    day = today() + timedelta(days=5)
    body = {"start_date": day.isoformat(), "end_date": day.isoformat(), "type": "sick"}

    # The suggested cover must be another active coach at the same branch.
    r = await coach.post("/api/coach/leaves", json=body | {"cover_instructor_id": inst["id"]})
    assert r.status_code == 422
    r = await coach.post(
        "/api/coach/leaves", json=body | {"cover_instructor_id": other_branch["id"]}
    )
    assert r.status_code == 422
    old = today() - timedelta(days=40)
    r = await coach.post(
        "/api/coach/leaves",
        json=body | {"start_date": old.isoformat(), "end_date": old.isoformat()},
    )
    assert r.status_code == 422

    first = (await coach.post("/api/coach/leaves", json=body)).json()
    r = await owner.post(
        f"/api/leaves/{first['id']}/decision", json={"approve": False, "note": "Busy"}
    )
    assert r.json()["status"] == "rejected" and r.json()["sessions_reassigned"] == 0

    # A rejected request frees the days for a new one, which the coach can withdraw.
    second = (await coach.post("/api/coach/leaves", json=body)).json()
    r = await coach.post(f"/api/coach/leaves/{second['id']}/withdraw")
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    statuses = [lv["status"] for lv in (await coach.get("/api/coach/leaves")).json()]
    assert sorted(statuses) == ["cancelled", "rejected"]

    # Pending leave does not hand out classes when the week is generated.
    await coach.post("/api/coach/leaves", json=body)
    sched = {
        "branch_id": prm,
        "program_id": p["id"],
        "instructor_id": inst["id"],
        "weekday": day.isoweekday(),
        "start_time": "17:00",
        "end_time": "18:00",
    }
    await owner.post("/api/schedules", json=sched)
    gen = {"branch_id": prm, "date_from": day.isoformat(), "date_to": day.isoformat()}
    assert (await owner.post("/api/sessions/generate", json=gen)).json()["created"] == 1
    params = {"date_from": day.isoformat(), "date_to": day.isoformat()}
    mine = (await coach.get("/api/coach/sessions", params=params)).json()
    assert mine[0]["coach_role"] == "teaching"

    # Staff record leave on the Classes page, not through the coach's own request.
    r = await owner.post("/api/coach/leaves", params={"instructor_id": inst["id"]}, json=body)
    assert r.status_code == 403
    await coach.aclose()


async def test_staff_leave_cannot_overlap(owner, branches):
    inst = await make_instructor(owner, branches["promenade"])
    day = today() + timedelta(days=1)
    body = {
        "instructor_id": inst["id"],
        "start_date": day.isoformat(),
        "end_date": (day + timedelta(days=2)).isoformat(),
        "type": "annual",
    }
    r = await owner.post("/api/leaves", json=body)
    assert r.status_code == 201 and r.json()["status"] == "approved"
    assert (await owner.post("/api/leaves", json=body)).status_code == 409

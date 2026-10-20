from datetime import date, datetime, timedelta

from tests.factories import make_belt, make_member, make_program


async def _belts(c):
    white = await make_belt(c, "White", 1)
    yellow = await make_belt(c, "Yellow", 2, seminars_required=2)
    return white, yellow


async def test_grading_promotes_on_finalize(owner, promenade_admin, branches):
    prm = branches["promenade"]
    white, yellow = await _belts(owner)
    a = await make_member(promenade_admin, prm, first="Pass", belt_rank_id=white["id"])
    b = await make_member(promenade_admin, prm, first="Fail", belt_rank_id=white["id"])
    ev = (
        await promenade_admin.post(
            "/api/gradings",
            json={
                "branch_id": prm,
                "title": "Spring grading",
                "event_date": date.today().isoformat(),
            },
        )
    ).json()
    url = f"/api/gradings/{ev['id']}"
    r = await promenade_admin.post(
        f"{url}/results", json={"entries": [{"member_id": a["id"]}, {"member_id": b["id"]}]}
    )
    assert r.status_code == 200
    assert {x["to_rank_id"] for x in r.json()} == {yellow["id"]}
    assert (await promenade_admin.post(f"{url}/finalize")).status_code == 422  # pending

    # A "pass" that does not advance is rejected.
    r = await promenade_admin.post(
        f"{url}/results",
        json={"entries": [{"member_id": a["id"], "outcome": "pass", "to_rank_id": white["id"]}]},
    )
    assert r.status_code == 422
    r = await promenade_admin.post(
        f"{url}/results",
        json={
            "entries": [
                {"member_id": a["id"], "outcome": "pass", "to_rank_id": yellow["id"]},
                {"member_id": b["id"], "outcome": "fail"},
            ]
        },
    )
    assert r.status_code == 200, r.text
    assert (await promenade_admin.post(f"{url}/finalize")).json()["status"] == "completed"
    assert (await promenade_admin.get(f"/api/members/{a['id']}")).json()["belt_rank_id"] == yellow[
        "id"
    ]
    assert (await promenade_admin.get(f"/api/members/{b['id']}")).json()["belt_rank_id"] == white[
        "id"
    ]
    assert (await promenade_admin.post(f"{url}/finalize")).status_code == 409


async def test_seminar_points_and_eligibility(owner, promenade_admin, branches):
    prm = branches["promenade"]
    white, _ = await _belts(owner)
    m = await make_member(
        promenade_admin,
        prm,
        belt_rank_id=white["id"],
        joined_on=(date.today() - timedelta(days=30)).isoformat(),
    )
    for i in range(2):
        s = (
            await promenade_admin.post(
                "/api/seminars",
                json={
                    "branch_id": prm,
                    "title": f"Self-defence {i}",
                    "seminar_date": date.today().isoformat(),
                },
            )
        ).json()
        r = await promenade_admin.post(
            f"/api/seminars/{s['id']}/attendees", json={"member_ids": [m["id"]]}
        )
        assert r.json() == [m["id"]]
    # idempotent
    await promenade_admin.post(f"/api/seminars/{s['id']}/attendees", json={"member_ids": [m["id"]]})
    assert (await promenade_admin.get("/api/seminars")).json()[0]["attendee_count"] == 1

    p = await make_program(owner)
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
    await promenade_admin.post(
        f"/api/sessions/{sess['id']}/attendance",
        json={"entries": [{"member_id": m["id"], "status": "present"}]},
    )
    rows = (
        await promenade_admin.get("/api/gradings-eligibility", params={"branch_id": prm})
    ).json()
    assert rows[0]["seminar_points"] == 2
    assert rows[0]["seminar_requirement_met"] is True
    assert rows[0]["classes_since_promotion"] == 1


async def test_incident_and_complaint_workflow(owner, promenade_admin, bedaya_admin, branches):
    prm = branches["promenade"]
    m = await make_member(promenade_admin, prm)
    r = await promenade_admin.post(
        "/api/incidents",
        json={
            "branch_id": prm,
            "occurred_at": (datetime.now() - timedelta(hours=1)).replace(microsecond=0).isoformat(),
            "type": "injury",
            "member_id": m["id"],
            "description": "Twisted ankle during sparring",
        },
    )
    assert r.status_code == 201, r.text
    inc = r.json()
    assert inc["ref_no"] == f"INC-PRM-{inc['id']:05d}"
    url = f"/api/incidents/{inc['id']}"
    assert (await bedaya_admin.get(url)).status_code == 404
    assert (await promenade_admin.patch(url, json={"status": "closed"})).status_code == 422
    r = await promenade_admin.patch(
        url,
        json={
            "status": "closed",
            "action_taken": "Ice, parent informed",
            "reported_to_manager": True,
        },
    )
    assert r.json()["closed_at"] and r.json()["reported_to_manager_at"]

    r = await promenade_admin.post(
        "/api/complaints",
        json={
            "branch_id": prm,
            "contact_name": "Parent",
            "channel": "whatsapp",
            "description": "Late class",
        },
    )
    c = r.json()
    assert c["ref_no"].startswith("CMP-PRM-")
    r = await promenade_admin.patch(f"/api/complaints/{c['id']}", json={"status": "closed"})
    assert r.status_code == 422
    r = await promenade_admin.patch(
        f"/api/complaints/{c['id']}",
        json={"status": "closed", "outcome": "Apologised; schedule fixed"},
    )
    assert r.json()["closed_on"] == date.today().isoformat()


async def test_followup_logged(promenade_admin, bedaya_admin, branches):
    m = await make_member(promenade_admin, branches["promenade"])
    body = {"member_id": m["id"], "method": "whatsapp", "outcome": "will_renew"}
    r = await promenade_admin.post("/api/followups", json=body)
    assert r.status_code == 201 and r.json()["branch_id"] == branches["promenade"]
    assert (await bedaya_admin.post("/api/followups", json=body)).status_code == 404

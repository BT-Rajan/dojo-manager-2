from datetime import date, timedelta

from tests.factories import make_belt, make_member, make_plan, make_program


async def test_catalog_write_requires_management(owner, promenade_admin):
    r = await promenade_admin.post("/api/programs", json={"name": "X", "discipline": "jiujitsu"})
    assert r.status_code == 403
    await make_program(owner)
    assert len((await promenade_admin.get("/api/programs")).json()) == 1


async def test_member_number_and_age(owner, branches):
    belt = await make_belt(owner)
    dob = date.today().replace(year=date.today().year - 10) - timedelta(days=1)
    m = await make_member(
        owner, branches["promenade"], belt_rank_id=belt["id"], date_of_birth=dob.isoformat()
    )
    assert m["member_no"] == f"PRM-{m['id']:05d}"
    assert m["age"] == 10
    assert m["belt_rank"]["name"] == "White"
    assert m["full_name"] == "Sara Ali"


async def test_member_validation(owner, branches):
    bad = {"branch_id": branches["promenade"], "first_name": "A", "last_name": "B"}
    assert (await owner.post("/api/members", json=bad | {"phone": "abc"})).status_code == 422
    r = await owner.post("/api/members", json=bad | {"phone": "999", "civil_id": "123"})
    assert r.status_code == 422
    r = await owner.post("/api/members", json=bad | {"phone": "999", "is_admin": True})
    assert r.status_code == 422  # unknown fields rejected


async def test_member_branch_isolation(promenade_admin, bedaya_admin, branches):
    m = await make_member(promenade_admin, branches["promenade"])
    assert (await bedaya_admin.get(f"/api/members/{m['id']}")).status_code == 404
    assert (await bedaya_admin.get("/api/members")).json() == []
    r = await bedaya_admin.get("/api/members", params={"branch_id": branches["promenade"]})
    assert r.status_code == 403
    r = await bedaya_admin.post(
        "/api/members",
        json={
            "branch_id": branches["promenade"],
            "first_name": "X",
            "last_name": "Y",
            "phone": "12345",
        },
    )
    assert r.status_code == 403
    r = await promenade_admin.patch(
        f"/api/members/{m['id']}", json={"branch_id": branches["bedaya"]}
    )
    assert r.status_code == 403


async def test_member_search_escapes_wildcards(owner, branches):
    await make_member(owner, branches["promenade"], first="Omar", last="Saleh")
    await make_member(owner, branches["promenade"], first="Noor", last="Hamad")
    r = await owner.get("/api/members", params={"q": "Om"})
    assert [m["first_name"] for m in r.json()] == ["Omar"]
    assert (await owner.get("/api/members", params={"q": "%"})).json() == []


async def test_membership_lifecycle(owner, promenade_admin, branches):
    plan = await make_plan(owner, price="65.000", days=30)
    m = await make_member(promenade_admin, branches["promenade"])
    r = await promenade_admin.post(
        "/api/memberships",
        json={"member_id": m["id"], "plan_id": plan["id"], "payment": {"method": "knet"}},
    )
    assert r.status_code == 201, r.text
    first = r.json()
    assert first["start_date"] == date.today().isoformat()
    assert first["end_date"] == (date.today() + timedelta(days=29)).isoformat()
    assert first["price"] == "65.000"

    # Renewing early continues from the day after the current end date.
    r = await promenade_admin.post(
        "/api/memberships",
        json={"member_id": m["id"], "plan_id": plan["id"], "payment": {"method": "cash"}},
    )
    second = r.json()
    assert second["start_date"] == (date.today() + timedelta(days=30)).isoformat()

    pays = (await promenade_admin.get("/api/payments", params={"member_id": m["id"]})).json()
    assert sorted(p["category"] for p in pays) == ["new", "renewal"]

    # Only managers override prices.
    r = await promenade_admin.post(
        "/api/memberships", json={"member_id": m["id"], "plan_id": plan["id"], "price": "1.000"}
    )
    assert r.status_code == 403


async def test_plan_must_be_offered_at_member_branch(owner, branches):
    plan = await make_plan(owner, branch_id=branches["bedaya"])
    m = await make_member(owner, branches["promenade"])
    r = await owner.post("/api/memberships", json={"member_id": m["id"], "plan_id": plan["id"]})
    assert r.status_code == 422


async def test_expiring_list(owner, branches):
    plan = await make_plan(owner, days=30)
    soon = await make_member(owner, branches["promenade"], first="Soon")
    later = await make_member(owner, branches["promenade"], first="Later")
    renewed = await make_member(owner, branches["promenade"], first="Renewed")
    start_soon = (date.today() - timedelta(days=27)).isoformat()
    for mid, start in ((soon["id"], start_soon), (later["id"], None), (renewed["id"], start_soon)):
        body = {"member_id": mid, "plan_id": plan["id"]}
        if start:
            body["start_date"] = start
        assert (await owner.post("/api/memberships", json=body)).status_code == 201
    await owner.post("/api/memberships", json={"member_id": renewed["id"], "plan_id": plan["id"]})

    rows = (await owner.get("/api/memberships/expiring", params={"days": 5})).json()
    assert [r["member"]["first_name"] for r in rows] == ["Soon"]
    assert rows[0]["days_left"] == 2


async def test_payments_void_and_isolation(owner, manager, promenade_admin, bedaya_admin, branches):
    m = await make_member(promenade_admin, branches["promenade"])
    body = {
        "branch_id": branches["promenade"],
        "member_id": m["id"],
        "amount": "12.500",
        "method": "card",
        "category": "equipment",
    }
    r = await promenade_admin.post("/api/payments", json=body)
    assert r.status_code == 201
    pid = r.json()["id"]
    r = await bedaya_admin.post("/api/payments", json=body | {"branch_id": branches["bedaya"]})
    assert r.status_code == 404  # member not visible from Bedaya
    assert (
        await promenade_admin.post(f"/api/payments/{pid}/void", json={"reason": "dup"})
    ).status_code == 403
    r = await manager.post(f"/api/payments/{pid}/void", json={"reason": "duplicate entry"})
    assert r.json()["is_void"] is True
    assert (await promenade_admin.get("/api/payments")).json() == []
    assert (await owner.post("/api/payments", json=body | {"amount": "0"})).status_code == 422

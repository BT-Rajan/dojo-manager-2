"""Small API helpers shared by tests."""

from httpx import AsyncClient


async def make_program(c: AsyncClient, name="Adult Kajukenbo", discipline="kajukenbo") -> dict:
    r = await c.post("/api/programs", json={"name": name, "discipline": discipline})
    assert r.status_code == 201, r.text
    return r.json()


async def make_belt(c: AsyncClient, name="White", order=1, **kw) -> dict:
    body = {"name": name, "color": name.lower(), "sort_order": order, "phase": "beginner", **kw}
    r = await c.post("/api/belts", json=body)
    assert r.status_code == 201, r.text
    return r.json()


async def make_plan(c: AsyncClient, price="65.000", days=30, branch_id=None) -> dict:
    body = {"name": f"Monthly {price}", "duration_days": days, "price": price}
    if branch_id:
        body["branch_id"] = branch_id
    r = await c.post("/api/plans", json=body)
    assert r.status_code == 201, r.text
    return r.json()


async def make_member(c: AsyncClient, branch_id: int, first="Sara", last="Ali", **kw) -> dict:
    body = {"branch_id": branch_id, "first_name": first, "last_name": last, "phone": "99990000"}
    r = await c.post("/api/members", json=body | kw)
    assert r.status_code == 201, r.text
    return r.json()


async def make_instructor(c: AsyncClient, branch_id: int, name="Coach Tareq") -> dict:
    r = await c.post("/api/instructors", json={"branch_id": branch_id, "full_name": name})
    assert r.status_code == 201, r.text
    return r.json()

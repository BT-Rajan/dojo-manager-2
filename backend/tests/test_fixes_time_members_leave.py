"""Regression tests: Kuwait time, member standing/pagination, leave cover, revenue, low stock."""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import update

from app.core.clock import day_range_utc
from app.core.clock import today as academy_today
from app.core.db import get_sessionmaker
from app.models import Payment
from tests.factories import make_instructor, make_member, make_plan, make_program


async def test_incident_accepts_aware_and_local_times_and_returns_kuwait_time(
    promenade_admin, branches
):
    body = {"branch_id": branches["promenade"], "type": "injury", "description": "Ankle"}
    aware = datetime(2026, 10, 1, 13, 0, tzinfo=UTC).isoformat()  # 16:00 in Kuwait
    r = await promenade_admin.post("/api/incidents", json=body | {"occurred_at": aware})
    assert r.status_code == 201, r.text
    assert r.json()["occurred_at"] == "2026-10-01T16:00:00+03:00"
    # Naive input is Kuwait local time.
    r = await promenade_admin.post(
        "/api/incidents", json=body | {"occurred_at": "2026-10-01T16:00:00"}
    )
    assert r.json()["occurred_at"] == "2026-10-01T16:00:00+03:00"
    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    r = await promenade_admin.post("/api/incidents", json=body | {"occurred_at": future})
    assert r.status_code == 422


def test_kuwait_day_range():
    lo, hi = day_range_utc(date(2026, 10, 20))
    assert (lo, hi) == (datetime(2026, 10, 19, 21, 0), datetime(2026, 10, 20, 21, 0))


async def test_member_standing(owner, branches):
    prm = branches["promenade"]
    plan = await make_plan(owner, days=30)
    lapsed = await make_member(owner, prm, first="Lapsed")
    active = await make_member(owner, prm, first="Active")
    new = await make_member(owner, prm, first="New")
    old_start = (academy_today() - timedelta(days=90)).isoformat()
    await owner.post(
        "/api/memberships",
        json={"member_id": lapsed["id"], "plan_id": plan["id"], "start_date": old_start},
    )
    await owner.post("/api/memberships", json={"member_id": active["id"], "plan_id": plan["id"]})

    assert (await owner.get(f"/api/members/{lapsed['id']}")).json()["standing"] == "lapsed"
    assert (await owner.get(f"/api/members/{active['id']}")).json()["standing"] == "active"
    assert (await owner.get(f"/api/members/{new['id']}")).json()["standing"] == "new"
    r = await owner.get("/api/members", params={"standing": "active"})
    assert [m["first_name"] for m in r.json()] == ["Active"]
    r = await owner.get("/api/members", params={"standing": "lapsed"})
    assert [m["first_name"] for m in r.json()] == ["Lapsed"]


async def test_members_pagination_total_and_sort(owner, branches):
    prm = branches["promenade"]
    for i in range(105):
        await make_member(owner, prm, first=f"M{i:03d}", last="Zed")
    r = await owner.get("/api/members", params={"limit": 50, "offset": 100})
    assert r.headers["x-total-count"] == "105"
    assert [m["first_name"] for m in r.json()] == ["M100", "M101", "M102", "M103", "M104"]
    r = await owner.get("/api/members", params={"limit": 3, "sort": "member_no", "order": "desc"})
    assert [m["first_name"] for m in r.json()] == ["M104", "M103", "M102"]
    assert (await owner.get("/api/members", params={"sort": "phone"})).status_code == 422


async def test_members_sort_by_age_unknown_last(owner, branches):
    prm = branches["promenade"]
    await make_member(owner, prm, first="Unknown")
    await make_member(owner, prm, first="Young", date_of_birth="2018-01-01")
    await make_member(owner, prm, first="Old", date_of_birth="1990-01-01")
    for order, expected in (
        ("asc", ["Young", "Old", "Unknown"]),
        ("desc", ["Old", "Young", "Unknown"]),
    ):
        r = await owner.get("/api/members", params={"sort": "age", "order": order})
        assert [m["first_name"] for m in r.json()] == expected


async def test_leave_after_generation_reassigns_and_restores(owner, branches):
    prm = branches["promenade"]
    p = await make_program(owner)
    coach = await make_instructor(owner, prm, "Coach A")
    cover = await make_instructor(owner, prm, "Coach B")
    day = academy_today() + timedelta(days=3)
    await owner.post(
        "/api/schedules",
        json={
            "branch_id": prm,
            "program_id": p["id"],
            "instructor_id": coach["id"],
            "weekday": day.isoweekday(),
            "start_time": "16:30:00",
            "end_time": "17:10:00",
        },
    )
    await owner.post(
        "/api/sessions/generate",
        json={"branch_id": prm, "date_from": day.isoformat(), "date_to": day.isoformat()},
    )
    r = await owner.post(
        "/api/leaves",
        json={
            "instructor_id": coach["id"],
            "start_date": day.isoformat(),
            "end_date": day.isoformat(),
            "type": "sick",
            "cover_instructor_id": cover["id"],
        },
    )
    assert r.json()["sessions_reassigned"] == 1
    params = {"date_from": day.isoformat(), "date_to": day.isoformat()}
    s = (await owner.get("/api/sessions", params=params)).json()[0]
    assert (s["instructor_id"], s["original_instructor_id"]) == (cover["id"], coach["id"])

    assert (await owner.delete(f"/api/leaves/{r.json()['id']}")).status_code == 204
    s = (await owner.get("/api/sessions", params=params)).json()[0]
    assert (s["instructor_id"], s["original_instructor_id"]) == (coach["id"], None)


async def test_revenue_today_uses_kuwait_day_half_open(owner, promenade_admin, branches):
    prm = branches["promenade"]
    m = await make_member(promenade_admin, prm)
    body = {"branch_id": prm, "member_id": m["id"], "method": "cash", "category": "other"}
    ids = []
    for amount in ("1.000", "2.000", "4.000"):
        ids.append(
            (await promenade_admin.post("/api/payments", json=body | {"amount": amount})).json()[
                "id"
            ]
        )
    start, end = day_range_utc(academy_today())
    async with get_sessionmaker()() as db:
        # 1 KD exactly at the start of today, 2 KD exactly at the start of tomorrow,
        # 4 KD one second before today began (yesterday in Kuwait).
        for pid, at in zip(ids, (start, end, start - timedelta(seconds=1)), strict=True):
            await db.execute(update(Payment).where(Payment.id == pid).values(paid_at=at))
        await db.commit()
    d = (await promenade_admin.get("/api/dashboard", params={"branch_id": prm})).json()
    assert d["revenue_today"] == "1.000"
    pays = (
        await promenade_admin.get(
            "/api/payments",
            params={
                "date_from": academy_today().isoformat(),
                "date_to": academy_today().isoformat(),
            },
        )
    ).json()
    assert [p["amount"] for p in pays] == ["1.000"]
    assert pays[0]["paid_at"].endswith("+03:00")


async def test_low_stock_same_on_dashboard_and_stock_page(owner, branches):
    prm = branches["promenade"]
    for sku, reorder in (("A", 2), ("B", 0)):
        await owner.post(
            "/api/inventory/items",
            json={
                "sku": sku,
                "name": sku,
                "category": "uniform",
                "unit_price": "1.000",
                "reorder_level": reorder,
            },
        )
    page = (
        await owner.get("/api/inventory/stock", params={"branch_id": prm, "low_only": True})
    ).json()
    dash = (await owner.get("/api/dashboard", params={"branch_id": prm})).json()
    assert len(page) == dash["low_stock_items"] == 2
    both = (await owner.get("/api/dashboard")).json()["low_stock_items"]
    assert both == 4  # two items at each of two branches

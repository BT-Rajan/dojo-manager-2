from datetime import date, timedelta

from app.models import Role
from tests.conftest import create_user, login
from tests.factories import make_member, make_plan, make_program


async def test_dashboard_counts_and_role_visibility(owner, promenade_admin, bedaya_admin, branches):
    prm = branches["promenade"]
    plan = await make_plan(owner, price="85.000", days=30)
    active = await make_member(promenade_admin, prm, first="Active")
    expiring = await make_member(promenade_admin, prm, first="Expiring")
    await promenade_admin.post(
        "/api/memberships",
        json={"member_id": active["id"], "plan_id": plan["id"], "payment": {"method": "knet"}},
    )
    await promenade_admin.post(
        "/api/memberships",
        json={
            "member_id": expiring["id"],
            "plan_id": plan["id"],
            "start_date": (date.today() - timedelta(days=27)).isoformat(),
        },
    )
    p = await make_program(owner)
    await owner.post(
        "/api/sessions",
        json={
            "branch_id": prm,
            "program_id": p["id"],
            "session_date": date.today().isoformat(),
            "start_time": "16:30",
            "end_time": "17:10",
        },
    )
    d = (await promenade_admin.get("/api/dashboard")).json()
    assert d["active_members"] == 2
    assert d["expiring_within_5_days"] == 1
    assert d["revenue_today"] == "85.000"
    assert d["today_classes"][0]["program"] == "Adult Kajukenbo"

    empty = (await bedaya_admin.get("/api/dashboard")).json()
    assert empty["active_members"] == 0 and empty["revenue_month"] == "0.000"

    await create_user("coach", Role.INSTRUCTOR, [prm])
    coach = await login("coach")
    d = (await coach.get("/api/dashboard")).json()
    assert "revenue_today" not in d and d["active_members"] == 2
    assert (
        await coach.get("/api/reports/weekly-sales", params={"branch_id": prm})
    ).status_code == 403
    await coach.aclose()


async def test_weekly_reports(owner, promenade_admin, branches):
    prm = branches["promenade"]
    plan = await make_plan(owner, price="55.000")
    m = await make_member(promenade_admin, prm)
    await promenade_admin.post(
        "/api/memberships",
        json={"member_id": m["id"], "plan_id": plan["id"], "payment": {"method": "cash"}},
    )
    await promenade_admin.post(
        "/api/memberships",
        json={"member_id": m["id"], "plan_id": plan["id"], "payment": {"method": "knet"}},
    )
    today = date.today()
    week_start = today - timedelta(days=(today.weekday() - 5) % 7)
    r = (await promenade_admin.get("/api/reports/weekly-sales", params={"branch_id": prm})).json()
    assert r["week_start"] == week_start.isoformat()
    assert r["total"] == "110.000"
    assert r["by_method"] == {"cash": "55.000", "knet": "55.000"}
    assert r["by_category"] == {"new": "55.000", "renewal": "55.000"}

    r = (await promenade_admin.get("/api/reports/weekly-branch", params={"branch_id": prm})).json()
    measures = {x["measure"]: x for x in r["measures"]}
    assert measures["new_members"]["this_week"] == 1
    assert measures["renewals"]["this_week"] == 1
    assert measures["active_members"]["change"] == 1

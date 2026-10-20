from app.models import Role
from tests.conftest import PASSWORD, create_user, login


async def test_health(anon):
    r = await anon.get("/api/health")
    assert r.status_code == 200
    assert r.headers["x-content-type-options"] == "nosniff"


async def test_requires_authentication(anon):
    assert (await anon.get("/api/auth/me")).status_code == 401
    assert (await anon.get("/api/branches")).status_code == 401


async def test_login_sets_httponly_cookie_and_logout_revokes(branches, anon):
    await create_user("alice", Role.OWNER)
    r = await anon.post("/api/auth/login", json={"username": "alice", "password": PASSWORD})
    assert r.status_code == 200
    assert "password_hash" not in r.json()
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert (await anon.get("/api/auth/me")).json()["username"] == "alice"
    assert (await anon.post("/api/auth/logout")).status_code == 204
    assert (await anon.get("/api/auth/me")).status_code == 401


async def test_bad_password_and_unknown_user_look_identical(branches, anon):
    await create_user("bob", Role.OWNER)
    r1 = await anon.post("/api/auth/login", json={"username": "bob", "password": "wrong-password"})
    r2 = await anon.post("/api/auth/login", json={"username": "nobody", "password": "x"})
    assert r1.status_code == r2.status_code == 401
    assert r1.json() == r2.json()


async def test_login_rate_limited(branches, anon):
    await create_user("carol", Role.OWNER)
    for _ in range(10):
        await anon.post("/api/auth/login", json={"username": "carol", "password": "nope"})
    r = await anon.post("/api/auth/login", json={"username": "carol", "password": PASSWORD})
    assert r.status_code == 429


async def test_csrf_header_required(owner):
    owner.headers.pop("X-Requested-With")
    r = await owner.post("/api/branches", json={"name": "X", "code": "X"})
    assert r.status_code == 403


async def test_branch_isolation(branches, promenade_admin, owner):
    r = await promenade_admin.get("/api/branches")
    assert [b["name"] for b in r.json()] == ["Promenade"]
    assert (await promenade_admin.get(f"/api/branches/{branches['bedaya']}")).status_code == 403
    assert len((await owner.get("/api/branches")).json()) == 2


async def test_only_owner_manages_users_and_branches(promenade_admin, owner, branches):
    assert (await promenade_admin.get("/api/users")).status_code == 403
    r = await promenade_admin.post("/api/branches", json={"name": "N", "code": "N"})
    assert r.status_code == 403
    r = await owner.post(
        "/api/users",
        json={
            "username": "coach1",
            "full_name": "Coach One",
            "password": "a-long-password",
            "role": "instructor",
            "branch_ids": [branches["bedaya"]],
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["branches"][0]["code"] == "BDY"
    weak = await owner.post(
        "/api/users", json={"username": "x1", "full_name": "X", "password": "short"}
    )
    assert weak.status_code == 422


async def test_disable_user_revokes_sessions(owner, branches):
    await create_user("dave", Role.BRANCH_ADMIN, [branches["promenade"]])
    dave = await login("dave")
    users = (await owner.get("/api/users")).json()
    dave_id = next(u["id"] for u in users if u["username"] == "dave")
    r = await owner.patch(f"/api/users/{dave_id}", json={"is_active": False})
    assert r.status_code == 200
    assert (await dave.get("/api/auth/me")).status_code == 401
    await dave.aclose()


async def test_change_password(branches):
    await create_user("erin", Role.MANAGER)
    erin = await login("erin")
    r = await erin.post(
        "/api/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "brand-new-password"},
    )
    assert r.status_code == 204
    assert (await erin.get("/api/auth/me")).status_code == 200
    await erin.aclose()

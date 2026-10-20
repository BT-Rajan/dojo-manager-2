import os

os.environ.setdefault("DOJO_ENVIRONMENT", "test")
os.environ["DOJO_DB_NAME"] = os.environ.get("DOJO_TEST_DB_NAME", "dojo_test")
os.environ["DOJO_COOKIE_SECURE"] = "false"

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from app.api.auth import login_limiter  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.db import get_sessionmaker  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base, Branch, Role, User  # noqa: E402

PASSWORD = "correct-horse-battery"


@pytest.fixture(scope="session", autouse=True)
def _schema():
    engine = create_engine(get_settings().database_url("pymysql"))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    engine.dispose()
    yield


@pytest.fixture(autouse=True)
async def _clean():
    yield
    login_limiter._hits.clear()
    async with get_sessionmaker()() as db:
        await db.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for table in reversed(Base.metadata.sorted_tables):
            await db.execute(table.delete())
        await db.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        await db.commit()


def make_client() -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )


@pytest.fixture
async def anon():
    async with make_client() as c:
        yield c


async def create_user(username: str, role: Role, branch_ids: list[int] = ()) -> User:
    async with get_sessionmaker()() as db:
        branches = [await db.get(Branch, b) for b in branch_ids]
        user = User(
            username=username,
            full_name=username.title(),
            role=role,
            password_hash=await hash_password(PASSWORD),
            branches=branches,
        )
        db.add(user)
        await db.commit()
        return user


async def create_branch(name: str, code: str) -> int:
    async with get_sessionmaker()() as db:
        b = Branch(name=name, code=code)
        db.add(b)
        await db.commit()
        return b.id


async def login(username: str) -> AsyncClient:
    c = make_client()
    r = await c.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return c


@pytest.fixture
async def branches() -> dict[str, int]:
    return {
        "promenade": await create_branch("Promenade", "PRM"),
        "bedaya": await create_branch("Bedaya", "BDY"),
    }


@pytest.fixture
async def owner(branches):
    await create_user("owner", Role.OWNER)
    c = await login("owner")
    yield c
    await c.aclose()


@pytest.fixture
async def manager(branches):
    await create_user("manager", Role.MANAGER)
    c = await login("manager")
    yield c
    await c.aclose()


@pytest.fixture
async def promenade_admin(branches):
    await create_user("prm_admin", Role.BRANCH_ADMIN, [branches["promenade"]])
    c = await login("prm_admin")
    yield c
    await c.aclose()


@pytest.fixture
async def bedaya_admin(branches):
    await create_user("bdy_admin", Role.BRANCH_ADMIN, [branches["bedaya"]])
    c = await login("bdy_admin")
    yield c
    await c.aclose()

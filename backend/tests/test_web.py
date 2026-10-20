"""The API process also serves the built frontend (single port, single origin)."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.fixture
async def site(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><div id=root></div>")
    (dist / "assets" / "index-abc123.js").write_text("console.log(1)")
    (tmp_path / "secret.txt").write_text("outside dist")
    app = create_app(frontend_dist=dist)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_index_and_client_routes_get_the_app(site):
    for path in ("/", "/members/12", "/inventory"):
        r = await site.get(path)
        assert r.status_code == 200
        assert "id=root" in r.text
        assert r.headers["cache-control"] == "no-cache"
        csp = r.headers["content-security-policy"]
        assert "script-src 'self'" in csp and "frame-ancestors 'none'" in csp
        assert r.headers["x-frame-options"] == "DENY"


async def test_hashed_assets_cached_forever(site):
    r = await site.get("/assets/index-abc123.js")
    assert r.status_code == 200
    assert "immutable" in r.headers["cache-control"]
    assert (await site.get("/assets/missing.js")).status_code == 404


async def test_api_routes_win_and_unknown_api_is_json_404(site):
    assert (await site.get("/api/health")).json() == {"status": "ok"}
    r = await site.get("/api/nope")
    assert r.status_code == 404 and r.json() == {"detail": "Not Found"}


async def test_no_files_outside_dist(site):
    for path in ("/../secret.txt", "/%2e%2e/secret.txt", "/assets/../../secret.txt"):
        r = await site.get(path)
        assert "outside dist" not in r.text


async def test_without_a_build_only_the_api_is_served(tmp_path):
    app = create_app(frontend_dist=tmp_path / "missing")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        assert (await c.get("/")).status_code == 404
        assert (await c.get("/api/health")).status_code == 200

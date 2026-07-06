"""Static-asset cache headers.

Every ``/static`` response must carry ``Cache-Control: no-store`` (set by the
``no_store_static`` middleware in :mod:`app.main`) so browsers never serve
stale JS/CSS. This retires the manual ``?v=`` cache-buster in index.html.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_static_app_js_is_no_store():
    """A 200 GET of /static/app.js carries Cache-Control: no-store."""
    with TestClient(app) as client:
        resp = client.get("/static/app.js")
        assert resp.status_code == 200
        assert resp.headers.get("cache-control") == "no-store"


def test_spa_shell_is_no_store():
    """The SPA shell at / is no-store too — stale index.html markup must never
    pair with fresh /static JS (DOM-id mismatch)."""
    with TestClient(app) as client:
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.headers.get("cache-control") == "no-store"


def test_static_not_modified_is_no_store():
    """The 304 Not-Modified path also carries the no-store header.

    StaticFiles honours conditional requests via ETag, so a second request with
    the returned ETag short-circuits to 304 — the middleware must still stamp
    the header on that response.
    """
    with TestClient(app) as client:
        first = client.get("/static/app.js")
        etag = first.headers.get("etag")
        assert etag is not None
        second = client.get("/static/app.js", headers={"If-None-Match": etag})
        assert second.status_code == 304
        assert second.headers.get("cache-control") == "no-store"

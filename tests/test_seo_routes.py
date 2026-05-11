"""SEO routes: pricing consolidation and sitemap reachability."""

import pytest

from app import create_app, db
from app import schema_compat


@pytest.fixture
def app():
    app = create_app("testing")
    with app.app_context():
        db.drop_all()
        db.create_all()
        schema_compat.refresh(app)
        yield app


@pytest.fixture
def client(app):
    return app.test_client()


def test_monetization_pricing_redirects_to_canonical(client):
    r = client.get("/monetization/pricing", follow_redirects=False)
    assert r.status_code == 301
    assert r.headers.get("Location", "").endswith("/pricing")


def test_main_pricing_ok(client):
    r = client.get("/pricing", follow_redirects=False)
    assert r.status_code == 200


def test_sitemap_xml_ok(client):
    r = client.get("/sitemap.xml", follow_redirects=False)
    assert r.status_code == 200
    assert b"<urlset" in r.data
    assert b"/pricing" in r.data


def test_robots_txt_has_sitemap(client):
    r = client.get("/robots.txt", follow_redirects=False)
    assert r.status_code == 200
    assert b"Sitemap:" in r.data
    assert b"sitemap.xml" in r.data

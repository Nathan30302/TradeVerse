"""SEO routes: public marketing pages and authenticated pricing."""

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


def test_main_pricing_requires_login(client):
    r = client.get("/pricing", follow_redirects=False)
    assert r.status_code == 302
    assert "/login" in r.headers.get("Location", "")


@pytest.mark.parametrize("path", ["/", "/about", "/features"])
def test_public_marketing_pages_do_not_show_pricing(client, path):
    r = client.get(path, follow_redirects=False)
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'href="/pricing"' not in body
    assert ">Pricing<" not in body
    assert "View Pricing" not in body


def test_sitemap_xml_ok(client):
    r = client.get("/sitemap.xml", follow_redirects=False)
    assert r.status_code == 200
    assert b"<urlset" in r.data
    assert b"/pricing" not in r.data


def test_robots_txt_has_sitemap(client):
    r = client.get("/robots.txt", follow_redirects=False)
    assert r.status_code == 200
    assert b"Sitemap:" in r.data
    assert b"sitemap.xml" in r.data


def test_about_page_has_substantive_content(client):
    """Thin 'Coming Soon' pages are often 'Discovered — currently not indexed' in GSC."""
    r = client.get("/about", follow_redirects=False)
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "Coming Soon" not in body
    assert "trade planner" in body.lower() or "Trade planner" in body
    assert 'name="description"' in body

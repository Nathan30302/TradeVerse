"""Admin token snapshot page — resilient to ORM schema drift (Core queries only)."""

import pytest

from app import create_app, db, schema_compat


@pytest.fixture
def app():
    app = create_app('testing')
    app.config['ADMIN_TOKEN'] = 'test_admin_token_value'
    app.config['OWNER_ADMIN_TOKEN'] = ''
    with app.app_context():
        db.drop_all()
        db.create_all()
        schema_compat.refresh(app)
        yield app


@pytest.fixture
def client(app):
    return app.test_client()


def test_admin_stats_503_when_no_token_configured():
    """Fresh app without ADMIN_TOKEN or OWNER_ADMIN_TOKEN -> 503."""
    app = create_app('testing')
    app.config['ADMIN_TOKEN'] = ''
    app.config['OWNER_ADMIN_TOKEN'] = ''
    with app.app_context():
        db.drop_all()
        db.create_all()
        schema_compat.refresh(app)
    c = app.test_client()
    r = c.get('/admin/stats?admin_token=anything')
    assert r.status_code == 503


def test_admin_stats_401_wrong_token(app, client):
    r = client.get('/admin/stats?admin_token=wrong')
    assert r.status_code == 401


def test_admin_stats_200_empty_db(app, client):
    r = client.get(
        '/admin/stats?admin_token=test_admin_token_value', follow_redirects=True
    )
    assert r.status_code == 200
    assert b'Platform snapshot' in r.data


def test_admin_stats_redirect_strips_token(app, client):
    r = client.get('/admin/stats?admin_token=test_admin_token_value', follow_redirects=False)
    assert r.status_code == 302
    loc = r.headers.get('Location', '')
    assert '/admin/stats' in loc
    assert 'admin_token' not in loc


def test_admin_email_200_after_token_session(app, client):
    client.get('/admin/stats?admin_token=test_admin_token_value', follow_redirects=True)
    r = client.get('/admin/email')
    assert r.status_code == 200
    assert b'Email outreach' in r.data


def test_admin_lock_clears_session(app, client):
    client.get('/admin/stats?admin_token=test_admin_token_value', follow_redirects=True)
    client.get('/admin/lock')
    r = client.get('/admin/stats')
    assert r.status_code == 401


def test_admin_stats_200_with_rows(app, client):
    from app.models.user import User
    from app.models.trade import Trade
    from datetime import datetime

    u = User(username='adm_u1', email='a1@example.com')
    u.set_password('x')
    db.session.add(u)
    db.session.commit()

    t = Trade(
        user_id=u.id,
        symbol='EURUSD',
        trade_type='BUY',
        status='CLOSED',
        lot_size=0.1,
        entry_price=1.1,
        exit_price=1.11,
        entry_date=datetime.utcnow(),
        profit_loss=100.0,
    )
    db.session.add(t)
    db.session.commit()

    r = client.get(
        '/admin/stats?admin_token=test_admin_token_value', follow_redirects=True
    )
    assert r.status_code == 200
    assert b'EURUSD' in r.data

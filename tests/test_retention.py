"""Tests for retention helpers — review queue, streak, grades, sample data."""

from datetime import datetime, timedelta, timezone

import pytest

from app import create_app, db, schema_compat
from app.models.trade import Trade
from app.models.user import User
from app.services.retention import (
    build_dashboard_daily_context,
    count_pending_trade_reviews,
    create_sample_trades,
    get_journaling_streak,
    get_review_queue,
    setup_letter_grade,
    trade_needs_review,
)


@pytest.fixture
def app():
    app = create_app('testing')
    with app.app_context():
        db.drop_all()
        db.create_all()
        schema_compat.refresh(app)
        yield app


@pytest.fixture
def user(app):
    u = User(username='retain', email='retain@example.com')
    u.set_password('password')
    db.session.add(u)
    db.session.commit()
    return u


def _closed_trade(user_id, *, notes='', lessons='', days_ago=1):
    now = datetime.now(timezone.utc) - timedelta(days=days_ago)
    t = Trade(
        user_id=user_id,
        symbol='EURUSD',
        trade_type='BUY',
        lot_size=0.1,
        entry_price=1.1,
        exit_price=1.11,
        entry_date=now,
        exit_date=now + timedelta(hours=2),
        status='CLOSED',
        profit_loss=10.0,
        post_trade_notes=notes or None,
        lessons_learned=lessons or None,
    )
    db.session.add(t)
    db.session.commit()
    return t


def test_trade_needs_review_when_closed_without_notes(app, user):
    reviewed = _closed_trade(user.id, notes='Good entry')
    unreviewed = _closed_trade(user.id)
    assert trade_needs_review(unreviewed) is True
    assert trade_needs_review(reviewed) is False


def test_count_pending_trade_reviews(app, user):
    _closed_trade(user.id, notes='done')
    _closed_trade(user.id)
    _closed_trade(user.id, lessons='learned')
    assert count_pending_trade_reviews(user.id) == 1


def test_get_review_queue_first_trade_id(app, user):
    older = _closed_trade(user.id, days_ago=3)
    newer = _closed_trade(user.id, days_ago=1)
    q = get_review_queue(user.id)
    assert q['trades_count'] == 2
    assert q['first_trade_id'] == newer.id


def test_setup_letter_grade_requires_minimum_trades():
    grade, color = setup_letter_grade(80.0, 2, 2.0)
    assert grade == '—'
    assert color == 'secondary'
    grade, color = setup_letter_grade(85.0, 10, 2.5)
    assert grade in ('A', 'B')
    assert color in ('success', 'primary')


def test_create_sample_trades_idempotent(app, user):
    assert create_sample_trades(user.id) == 3
    assert create_sample_trades(user.id) == 0
    assert Trade.query.filter_by(user_id=user.id).count() == 3


def test_journaling_streak_counts_activity_days(app, user):
    _closed_trade(user.id, notes='reviewed', days_ago=0)
    streak = get_journaling_streak(user.id, 'UTC')
    assert streak >= 1


def test_build_dashboard_daily_context_keys(app, user):
    _closed_trade(user.id)
    ctx = build_dashboard_daily_context(user, user_name='retain')
    assert 'review_queue' in ctx
    assert 'journaling_streak' in ctx
    assert 'morning_briefing' in ctx
    assert 'weekly_focus' in ctx

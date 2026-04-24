import pytest
from datetime import datetime, timezone
from app import create_app, db
from app.models.user import User
from app.models.trade_plan import TradePlan
from app.models.trade import Trade


@pytest.fixture
def app():
    app = create_app('testing')
    with app.app_context():
        # Ensure fresh DB
        db.drop_all()
        db.create_all()
        yield app


@pytest.fixture
def client(app):
    return app.test_client()


def test_plan_execute_creates_trade(app, client):
    # Create test user
    from app import bcrypt
    user = User(username='tester', email='tester@example.com')
    user.set_password('password')
    db.session.add(user)
    db.session.commit()

    # Create a plan
    plan = TradePlan(
        user_id=user.id,
        status='PLANNING',
        symbol='EURUSD',
        direction='BUY',
        planned_entry=1.1000,
        planned_stop_loss=1.0950,
        planned_take_profit=1.1100,
        planned_lot_size=0.1,
        strategy='Price Action'
    )
    db.session.add(plan)
    db.session.commit()

    # Simulate login by setting the Flask-Login session key
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user.id)

    # POST to execute (start) endpoint
    resp = client.post(f'/planner/{plan.id}/start', follow_redirects=False)

    # Expect a redirect to the new trade view
    assert resp.status_code in (302, 303)

    # Verify trade created and plan updated
    created_trade = Trade.query.filter_by(user_id=user.id, symbol='EURUSD').first()
    assert created_trade is not None, "Trade was not created from plan"

    updated_plan = TradePlan.query.first()  # or use db.session.get(TradePlan, plan.id)
    assert updated_plan is not None
    assert updated_plan.executed is True or updated_plan.status == 'EXECUTED'
    assert updated_plan.executed_trade_id == created_trade.id or updated_plan.trade_id == created_trade.id


def test_plan_execute_immediate_close_syncs_trade_and_plan(app, client):
    # Create test user
    from app import bcrypt
    from datetime import datetime

    user = User(username='syncuser', email='sync@example.com')
    user.set_password('password')
    db.session.add(user)
    db.session.commit()

    # Create a plan
    plan = TradePlan(
        user_id=user.id,
        status='PLANNING',
        symbol='EURUSD',
        direction='BUY',
        planned_entry=1.1000,
        planned_stop_loss=1.0950,
        planned_take_profit=1.1100,
        planned_lot_size=0.1,
        strategy='Price Action'
    )
    db.session.add(plan)
    db.session.commit()

    with client.session_transaction() as sess:
        sess['_user_id'] = str(user.id)

    exit_price = 1.1050
    exit_date = datetime.now(timezone.utc).isoformat()
    resp = client.post(
        f'/planner/{plan.id}/start',
        data={
            'trade_type': 'BUY',
            'entry_price': '1.1000',
            'stop_loss': '1.0950',
            'take_profit': '1.1100',
            'lot_size': '0.1',
            'strategy': 'Price Action',
            'pre_trade_plan': 'Test sync',
            'exit_price': str(exit_price),
            'exit_date': exit_date
        },
        follow_redirects=False
    )

    assert resp.status_code in (302, 303)

    created_trade = Trade.query.filter_by(user_id=user.id, symbol='EURUSD').first()
    assert created_trade is not None, 'Trade was not created from plan'
    assert created_trade.status == 'CLOSED', 'Trade should be closed when exit_price is provided'
    assert created_trade.exit_price == exit_price
    assert created_trade.profit_loss is not None

    updated_plan = db.session.get(TradePlan, plan.id)
    assert updated_plan is not None
    assert updated_plan.status == 'REVIEWED', 'Plan should be reviewed when trade closes immediately'
    assert updated_plan.executed_trade_id == created_trade.id or updated_plan.trade_id == created_trade.id
    assert updated_plan.actual_exit == exit_price
    assert updated_plan.actual_pnl == created_trade.profit_loss


def test_plan_view_syncs_with_linked_trade_closure(app, client):
    from app import bcrypt
    from datetime import datetime

    user = User(username='syncview', email='syncview@example.com')
    user.set_password('password')
    db.session.add(user)
    db.session.commit()

    plan = TradePlan(
        user_id=user.id,
        status='PLANNING',
        symbol='EURUSD',
        direction='BUY',
        planned_entry=1.1000,
        planned_stop_loss=1.0950,
        planned_take_profit=1.1100,
        planned_lot_size=0.1,
        strategy='Price Action'
    )
    db.session.add(plan)
    db.session.commit()

    with client.session_transaction() as sess:
        sess['_user_id'] = str(user.id)

    # Execute the plan without closing immediately
    resp = client.post(f'/planner/{plan.id}/start', data={
        'trade_type': 'BUY',
        'entry_price': '1.1000',
        'stop_loss': '1.0950',
        'take_profit': '1.1100',
        'lot_size': '0.1',
        'strategy': 'Price Action',
        'pre_trade_plan': 'Sync test'
    }, follow_redirects=False)
    assert resp.status_code in (302, 303)

    created_trade = Trade.query.filter_by(user_id=user.id, symbol='EURUSD').first()
    assert created_trade is not None
    assert created_trade.status == 'OPEN'

    # Simulate closing the trade in My Trades later
    created_trade.exit_price = 1.1050
    created_trade.exit_date = datetime.now(timezone.utc)
    created_trade.status = 'CLOSED'
    created_trade.calculate_pnl()
    db.session.commit()

    # Reload plan and hit the planner view to trigger sync
    resp = client.get(f'/planner/{plan.id}')
    assert resp.status_code == 200

    synced_plan = db.session.get(TradePlan, plan.id)
    assert synced_plan.status == 'REVIEWED'
    assert synced_plan.actual_pnl == created_trade.profit_loss
    assert synced_plan.executed_trade_id == created_trade.id or synced_plan.trade_id == created_trade.id
    assert synced_plan.reviewed_at is not None

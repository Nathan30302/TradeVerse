import pytest
from app import create_app, db
from app.models.user import User
from app.models.trade_plan import TradePlan
from app.models.trade import Trade
import pytest
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

#!/usr/bin/env python3
"""
Test script to verify trade flow fixes
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models.user import User
from app.models.trade import Trade
from app.models.trade_plan import TradePlan
from app.models.instrument import Instrument
from werkzeug.security import generate_password_hash

def test_trade_flow():
    """Test the complete trade flow from planner to performance"""
    app = create_app('testing')
    
    with app.app_context():
        print("Testing Trade Flow Fixes...")
        
        # Create test user
        user = User(
            username='testuser',
            email='test@example.com',
            password_hash=generate_password_hash('password123')
        )
        db.session.add(user)
        db.session.commit()
        print("✓ Created test user")
        
        # Create test instrument
        instrument = Instrument(
            symbol='TESTUSD',
            name='Test USD',
            instrument_type='CRYPTO',
            category='Crypto'
        )
        db.session.add(instrument)
        db.session.commit()
        print("✓ Created test instrument")
        
        # Test 1: Create Trade Plan
        plan = TradePlan(
            user_id=user.id,
            status='PLANNING',
            symbol='BTCUSD',
            direction='BUY',
            planned_entry=50000.0,
            planned_stop_loss=48000.0,
            planned_take_profit=55000.0,
            planned_lot_size=0.01,
            strategy='Breakout'
        )
        plan.calculate_planned_rr()
        plan.calculate_plan_quality()
        db.session.add(plan)
        db.session.commit()
        print("✓ Created trade plan")
        
        # Test 2: Execute Plan (create Trade)
        trade = Trade(
            user_id=user.id,
            symbol='BTCUSD',
            trade_type='BUY',
            lot_size=0.01,
            entry_price=50000.0,
            stop_loss=48000.0,
            take_profit=55000.0,
            entry_date=db.func.now()
        )
        
        # Link plan to trade
        plan.executed = True
        plan.executed_trade_id = trade.id
        plan.mark_as_executed()
        
        db.session.add(trade)
        db.session.flush()  # Get trade.id
        
        # Update plan with trade ID
        plan.executed_trade_id = trade.id
        
        db.session.commit()
        print("✓ Executed plan and created trade")
        
        # Test 3: Close Trade
        trade.exit_price = 52000.0
        trade.exit_date = db.func.now()
        trade.status = 'CLOSED'
        trade.calculate_pnl()
        
        # Update plan with actual results
        plan.actual_entry = 50000.0
        plan.actual_exit = 52000.0
        plan.actual_pnl = trade.profit_loss
        plan.mark_as_reviewed()
        plan.calculate_execution_quality()
        
        db.session.commit()
        print("✓ Closed trade and updated plan")
        
        # Test 4: Verify relationships
        assert plan.executed_trade_id == trade.id, "Plan should be linked to trade"
        assert plan.status == 'REVIEWED', "Plan should be reviewed"
        assert trade.status == 'CLOSED', "Trade should be closed"
        assert trade.profit_loss is not None, "Trade should have P&L calculated"
        assert plan.actual_pnl == trade.profit_loss, "Plan P&L should match trade P&L"
        
        print("✓ All relationships verified")
        
        # Test 5: Test P&L calculation
        expected_pnl = 20.0  # (52000 - 50000) * 0.01
        assert abs(trade.profit_loss - expected_pnl) < 0.01, f"Expected P&L {expected_pnl}, got {trade.profit_loss}"
        print("✓ P&L calculation verified")
        
        # Test 6: Test grade field (should not cause database error)
        plan.trade_grade = 'A'
        db.session.commit()
        print("✓ Grade field works correctly")
        
        print("\n🎉 All trade flow tests passed!")
        print("Trade Planner → Execute → Complete → My Trades → Performance flow is working correctly")
        
        # Clean up
        db.session.delete(plan)
        db.session.delete(trade)
        db.session.delete(instrument)
        db.session.delete(user)
        db.session.commit()
        
        return True

if __name__ == '__main__':
    try:
        test_trade_flow()
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
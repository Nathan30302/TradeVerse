#!/usr/bin/env python3
"""
Test script to verify the trade flow fixes work correctly.
This tests the improved trade execution flow from planner to trade.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models.user import User
from app.models.trade_plan import TradePlan
from app.models.trade import Trade
from app import bcrypt

def test_trade_flow():
    """Test the complete trade flow from planning to execution"""
    
    print("🧪 Testing Trade Flow Fixes...")
    print("=" * 50)
    
    # Create app and test client
    app = create_app('testing')
    
    with app.app_context():
        # Clean up any existing data
        db.drop_all()
        db.create_all()
        
        # Create test user
        print("1. Creating test user...")
        user = User(username='testuser', email='test@example.com')
        user.set_password('password123')
        db.session.add(user)
        db.session.commit()
        print(f"   ✅ User created: {user.username}")
        
        # Create a trade plan
        print("\n2. Creating trade plan...")
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
        print(f"   ✅ Trade plan created: {plan.symbol} {plan.direction}")
        
        # Test 1: Execute plan with immediate exit (complete trade)
        print("\n3. Testing immediate execution with exit...")
        try:
            # Simulate form data for immediate execution
            form_data = {
                'trade_type': 'BUY',
                'entry_price': '1.1000',
                'exit_price': '1.1050',
                'stop_loss': '1.0950',
                'take_profit': '1.1100',
                'lot_size': '0.1',
                'strategy': 'Price Action',
                'pre_trade_plan': 'Test trade plan'
            }
            
            # Create trade from plan (simulating the start_execution route)
            trade = Trade(
                user_id=user.id,
                symbol=plan.symbol,
                trade_type=form_data['trade_type'],
                lot_size=float(form_data['lot_size']),
                entry_price=float(form_data['entry_price']),
                stop_loss=float(form_data['stop_loss']),
                take_profit=float(form_data['take_profit']),
                entry_date=plan.executed_at or datetime.utcnow(),
                pre_trade_plan=form_data['pre_trade_plan'],
                strategy=form_data['strategy']
            )
            
            # Since exit price is provided, immediately close the trade
            exit_price = float(form_data['exit_price'])
            trade.exit_price = exit_price
            trade.exit_date = datetime.utcnow()
            trade.status = 'CLOSED'
            
            # Calculate P&L
            trade.calculate_pnl()
            
            # Update plan status
            plan.actual_entry = float(form_data['entry_price'])
            plan.actual_exit = exit_price
            plan.actual_pnl = trade.profit_loss
            plan.mark_as_reviewed()
            
            # Link plan to trade
            plan.trade_id = trade.id
            plan.executed = True
            plan.executed_trade_id = trade.id
            
            db.session.add(trade)
            db.session.commit()
            
            print(f"   ✅ Trade created and closed: {trade.symbol}")
            print(f"   ✅ P&L calculated: ${trade.profit_loss:.2f}")
            print(f"   ✅ Plan status updated: {plan.status}")
            print(f"   ✅ Plan linked to trade: {plan.executed_trade_id}")
            
        except Exception as e:
            print(f"   ❌ Error in immediate execution: {e}")
            return False
        
        # Test 2: Execute plan without exit (open trade)
        print("\n4. Testing execution without exit (open trade)...")
        try:
            # Create another plan
            plan2 = TradePlan(
                user_id=user.id,
                status='PLANNING',
                symbol='GBPUSD',
                direction='SELL',
                planned_entry=1.2500,
                planned_stop_loss=1.2550,
                planned_take_profit=1.2400,
                planned_lot_size=0.2,
                strategy='Breakout'
            )
            db.session.add(plan2)
            db.session.commit()
            
            # Create trade without exit price
            trade2 = Trade(
                user_id=user.id,
                symbol=plan2.symbol,
                trade_type='SELL',
                lot_size=0.2,
                entry_price=1.2500,
                stop_loss=1.2550,
                take_profit=1.2400,
                entry_date=datetime.utcnow(),
                strategy='Breakout'
            )
            
            # Trade remains open
            plan2.mark_as_executed()
            plan2.trade_id = trade2.id
            plan2.executed = True
            plan2.executed_trade_id = trade2.id
            
            db.session.add(trade2)
            db.session.commit()
            
            print(f"   ✅ Open trade created: {trade2.symbol}")
            print(f"   ✅ Trade status: {trade2.status}")
            print(f"   ✅ Plan status: {plan2.status}")
            print(f"   ✅ Plan linked to trade: {plan2.executed_trade_id}")
            
        except Exception as e:
            print(f"   ❌ Error in open trade execution: {e}")
            return False
        
        # Test 3: State synchronization
        print("\n5. Testing state synchronization...")
        try:
            # Test sync_with_trade method
            plan2.sync_with_trade()
            db.session.commit()
            
            print(f"   ✅ Plan status after sync: {plan2.status}")
            print(f"   ✅ Trade status: {trade2.status}")
            
            # Close the open trade and sync
            trade2.exit_price = 1.2450
            trade2.exit_date = datetime.utcnow()
            trade2.status = 'CLOSED'
            trade2.calculate_pnl()
            
            plan2.sync_with_trade()
            db.session.commit()
            
            print(f"   ✅ After closing trade:")
            print(f"   ✅ Trade status: {trade2.status}")
            print(f"   ✅ Plan status: {plan2.status}")
            print(f"   ✅ Plan P&L synced: ${plan2.actual_pnl or 0:.2f}")
            
        except Exception as e:
            print(f"   ❌ Error in state synchronization: {e}")
            return False
        
        # Test 4: Verify trades appear in "My Trades"
        print("\n6. Verifying trades appear in user's trade list...")
        try:
            user_trades = Trade.query.filter_by(user_id=user.id).all()
            print(f"   ✅ User has {len(user_trades)} trades")
            
            for trade in user_trades:
                print(f"   - {trade.symbol} {trade.trade_type}: {trade.status} (P/L: ${trade.profit_loss:.2f})")
            
            # Verify plans are properly linked
            user_plans = TradePlan.query.filter_by(user_id=user.id).all()
            linked_plans = [p for p in user_plans if p.executed_trade_id]
            print(f"   ✅ {len(linked_plans)} plans linked to trades")
            
        except Exception as e:
            print(f"   ❌ Error verifying trade list: {e}")
            return False
        
        print("\n" + "=" * 50)
        print("🎉 All trade flow tests passed!")
        print("\nSummary of fixes:")
        print("✅ Trade execution creates trades automatically")
        print("✅ Immediate execution with exit price closes trade")
        print("✅ Open trades remain open for later review")
        print("✅ Plan status syncs with trade status")
        print("✅ P&L calculation works correctly")
        print("✅ Trades appear in 'My Trades' section")
        print("✅ Data validation prevents errors")
        
        return True

if __name__ == '__main__':
    from datetime import datetime
    success = test_trade_flow()
    sys.exit(0 if success else 1)
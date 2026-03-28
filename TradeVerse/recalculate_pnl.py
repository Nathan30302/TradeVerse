#!/usr/bin/env python3
"""
Recalculate P&L for all existing trades and trade plans
This ensures all historical records use the unified calculation engine
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app import create_app, db
from app.models.trade import Trade
from app.models.trade_plan import TradePlan

def recalculate_all_pnl():
    """Recalculate P&L for all trades and trade plans"""
    app = create_app()
    
    with app.app_context():
        # Recalculate all trades
        trades = Trade.query.filter(Trade.exit_price.isnot(None)).all()
        print(f"\n{'='*80}")
        print("RECALCULATING TRADES")
        print(f"{'='*80}")
        print(f"Found {len(trades)} closed trades to recalculate\n")
        
        updated_trades = 0
        for trade in trades:
            old_pnl = trade.profit_loss
            trade.calculate_pnl()
            new_pnl = trade.profit_loss
            
            if old_pnl != new_pnl:
                print(f"Trade {trade.id} ({trade.symbol}): ${old_pnl:.2f} → ${new_pnl:.2f}")
                updated_trades += 1
        
        # Recalculate all trade plans
        plans = TradePlan.query.filter(
            TradePlan.actual_entry.isnot(None),
            TradePlan.actual_exit.isnot(None)
        ).all()
        
        print(f"\n{'='*80}")
        print("RECALCULATING TRADE PLANS")
        print(f"{'='*80}")
        print(f"Found {len(plans)} reviewed trade plans to recalculate\n")
        
        updated_plans = 0
        for plan in plans:
            old_pnl = plan.actual_pnl
            plan.calculate_pnl()
            new_pnl = plan.actual_pnl
            
            if old_pnl != new_pnl:
                print(f"Plan {plan.id} ({plan.symbol}): ${old_pnl:.2f} → ${new_pnl:.2f}")
                updated_plans += 1
        
        # Commit all changes
        try:
            db.session.commit()
            print(f"\n{'='*80}")
            print(f"✅ SUCCESS: Updated {updated_trades} trades and {updated_plans} plans")
            print(f"{'='*80}\n")
        except Exception as e:
            db.session.rollback()
            print(f"\n❌ ERROR: Failed to commit changes: {e}\n")
            raise

if __name__ == '__main__':
    recalculate_all_pnl()


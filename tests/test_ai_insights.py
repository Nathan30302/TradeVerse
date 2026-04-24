import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models.user import User
from app.models.trade import Trade
from app.services.ai_insights import AIAnalyzer


def test_ai_insights_service():
    app = create_app('testing')

    with app.app_context():
        db.drop_all()
        db.create_all()

        user = User(username='aiuser', email='ai@example.com')
        user.set_password('password')
        db.session.add(user)
        db.session.commit()

        trades = [
            Trade(user_id=user.id, symbol='EURUSD', trade_type='BUY', lot_size=0.1, entry_price=1.1000, exit_price=1.1050, stop_loss=1.0950, take_profit=1.1100, entry_date=user.created_at, exit_date=user.created_at, status='CLOSED', profit_loss=50.0, risk_reward=2.0, emotion='Disciplined', confidence_level=8),
            Trade(user_id=user.id, symbol='GBPUSD', trade_type='SELL', lot_size=0.1, entry_price=1.2500, exit_price=1.2450, stop_loss=1.2550, take_profit=1.2400, entry_date=user.created_at, exit_date=user.created_at, status='CLOSED', profit_loss=50.0, risk_reward=1.5, emotion='FOMO', confidence_level=4),
            Trade(user_id=user.id, symbol='XAUUSD', trade_type='BUY', lot_size=0.01, entry_price=1900.0, exit_price=1910.0, stop_loss=1890.0, take_profit=1920.0, entry_date=user.created_at, exit_date=user.created_at, status='CLOSED', profit_loss=100.0, risk_reward=2.5, emotion='Calm & Focused', confidence_level=9)
        ]
        db.session.add_all(trades)
        db.session.commit()

        analyzer = AIAnalyzer(user.id)
        weekly_review = analyzer.get_weekly_review()

        assert weekly_review['stats']['total_trades'] == 3
        assert 'win_rate' in weekly_review['stats']
        assert isinstance(weekly_review['summary'], str)
        assert analyzer.answer_question('How did I perform this week').startswith('This week')


if __name__ == '__main__':
    success = test_ai_insights_service()
    print('AI insights service test passed.' if success is not False else 'AI insights service test failed.')

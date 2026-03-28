#!/usr/bin/env python3
"""
Initialize the database
"""

import os
from app import create_app, db

app = create_app(os.getenv('FLASK_ENV') or 'development')

with app.app_context():
    # Import all models to ensure they are registered with SQLAlchemy
    from app.models import user, trade
    from app.models.trade_plan import TradePlan
    from app.models.performance_score import PerformanceScore
    from app.models.trade_feedback import TradeFeedback
    from app.models.cooldown import Cooldown

    db.create_all()
    print('✅ Database initialized successfully!')

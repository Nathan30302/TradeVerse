#!/usr/bin/env python3
"""
Initialize the database
"""

import os
from app import create_app, db
from flask_migrate import upgrade

app = create_app(os.getenv('FLASK_ENV') or 'development')

with app.app_context():
    # Import all models to ensure they are registered with SQLAlchemy
    from app.models import user, trade
    from app.models.trade_plan import TradePlan
    from app.models.performance_score import PerformanceScore
    from app.models.trade_feedback import TradeFeedback
    from app.models.cooldown import Cooldown

    upgrade()
    print('✅ Database upgraded successfully (Alembic)!')

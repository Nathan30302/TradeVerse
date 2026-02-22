"""
WSGI entry point for production servers (Gunicorn)
"""

import os
from app import create_app, db

# Determine environment from FLASK_ENV or default to production
config_name = os.getenv('FLASK_ENV') or 'production'

# Create the Flask application
app = create_app(config_name)

# Ensure database tables are created on startup
with app.app_context():
    try:
        db.create_all()
    except Exception as e:
        app.logger.warning(f"Could not create database tables on startup: {e}")
 
"""
WSGI entry point for production servers (Gunicorn)
"""

import os
from app import create_app

# Determine environment from FLASK_ENV or default to production
config_name = os.getenv('FLASK_ENV') or 'production'

# Create the Flask application
app = create_app(config_name)
 
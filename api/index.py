"""
TradeVerse - Flask Application Entry Point
For deployment platforms that require api/index.py
"""

from app import create_app

# Create the Flask application instance
app = create_app()

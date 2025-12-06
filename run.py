#!/usr/bin/env python3
"""
TradeVerse - Professional Trading Journal
Main Application Entry Point

Run this file to start the application:
    python run.py
"""

import os
from app import create_app, db
from app.models.user import User
from app.models.trade import Trade

# Create the Flask application
app = create_app(os.getenv('FLASK_ENV') or 'development')

# Shell context for Flask CLI
@app.shell_context_processor
def make_shell_context():
    """Make database and models available in Flask shell"""
    return {
        'db': db,
        'User': User,
        'Trade': Trade
    }

# Custom CLI commands
@app.cli.command()
def init_db():
    """Initialize the database"""
    db.create_all()
    print('✅ Database initialized successfully!')

@app.cli.command()
def reset_db():
    """Reset the database (WARNING: Deletes all data!)"""
    response = input('⚠️  This will delete ALL data. Are you sure? (yes/no): ')
    if response.lower() == 'yes':
        db.drop_all()
        db.create_all()
        print('✅ Database reset successfully!')
    else:
        print('❌ Database reset cancelled.')

if __name__ == '__main__':
    print('🚀 Starting TradeVerse...')
    print('📊 Professional Trading Journal')
    print('🌐 Open your browser to: http://localhost:5000')
    print('⏹️  Press CTRL+C to stop\n')
    
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True
    )
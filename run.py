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
from flask_migrate import upgrade

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
    upgrade()
    print('Database upgraded successfully (Alembic).')

@app.cli.command()
def reset_db():
    """Reset the database (WARNING: Deletes all data!)"""
    response = input('WARNING: This will delete ALL data. Are you sure? (yes/no): ')
    if response.lower() == 'yes':
        uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
        if not (uri and uri.startswith('sqlite')):
            print('Refusing to reset non-SQLite database. Use migrations and/or managed DB tooling.')
            return
        db.drop_all()
        upgrade()
        print('Database reset successfully (dropped tables, then Alembic upgrade).')
    else:
        print('Database reset cancelled.')

if __name__ == '__main__':
    # Keep local/dev DB aligned with models so routes don’t crash on schema drift.
    if (os.getenv('FLASK_ENV') or 'development') != 'production':
        try:
            with app.app_context():
                upgrade()
        except Exception as exc:
            print(
                'WARNING: Automatic db upgrade failed — run `flask db upgrade` manually:',
                exc,
            )

    port = int(os.environ.get('PORT', '5001'))

    print('Starting TradeVerse...')
    print('Professional Trading Journal')
    print(f'Open your browser to: http://localhost:{port}')
    print('Press CTRL+C to stop\n')
    
    # Respect the configured DEBUG flag so running locally in production mode
    # doesn't accidentally enable the debugger. For production use Gunicorn
    # via the Procfile which loads `app.wsgi:app`.
    app.run(
        host='0.0.0.0',
        port=port,
        debug=app.config.get('DEBUG', False)
    )

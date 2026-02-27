"""
TEMPORARY FILE — app/routes/admin_reset.py

PURPOSE:
    One-time use route to clear and reseed instruments on Render's database.
    The database on Render still has the old 17 stub instruments.
    This route clears them so the app reseeds with all 257 instruments.

USAGE:
    1. Add this file to app/routes/admin_reset.py
    2. Register it in app/__init__.py (instructions below)
    3. Push to GitHub → Render auto-deploys
    4. Visit: https://tradeverse-wl7z.onrender.com/admin/reset-instruments?key=tradeverse2026
    5. You will see a JSON response confirming success
    6. DELETE this file and remove the blueprint registration
    7. Push to GitHub again to remove the route

REGISTER IN app/__init__.py — add these two lines wherever other blueprints are registered:
    from app.routes.admin_reset import bp as admin_reset_bp
    app.register_blueprint(admin_reset_bp)
"""

from flask import Blueprint, jsonify, request
from app import db

bp = Blueprint('admin_reset', __name__, url_prefix='/admin')


@bp.route('/reset-instruments', methods=['GET'])
def reset_instruments():
    """
    Clears all instruments from the database so the app reseeds on next request.
    Protected by a secret key query parameter.
    """
    # Simple secret key protection — only you know this URL
    secret = request.args.get('key', '')
    if secret != 'tradeverse2026':
        return jsonify({'error': 'Unauthorized'}), 403

    try:
        # Count before
        before = db.session.execute(db.text('SELECT COUNT(*) FROM instruments')).scalar()

        # Clear all instruments (reseeding happens automatically on next /api/instruments call)
        db.session.execute(db.text('DELETE FROM instrument_aliases'))
        db.session.execute(db.text('DELETE FROM instruments'))
        db.session.commit()

        # Count after
        after = db.session.execute(db.text('SELECT COUNT(*) FROM instruments')).scalar()

        return jsonify({
            'status': 'success',
            'message': 'Instruments cleared. Visit /api/instruments to trigger reseed.',
            'before': before,
            'after': after,
            'next_step': 'Visit /api/instruments?category=Stocks to trigger automatic reseed'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@bp.route('/check-instruments', methods=['GET'])
def check_instruments():
    """
    Check current instrument counts by category — no secret key needed.
    Visit: /admin/check-instruments
    """
    try:
        total = db.session.execute(db.text('SELECT COUNT(*) FROM instruments')).scalar()
        categories = db.session.execute(db.text(
            'SELECT category, COUNT(*) as count FROM instruments GROUP BY category ORDER BY category'
        )).fetchall()

        return jsonify({
            'total': total,
            'categories': {row[0]: row[1] for row in categories}
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
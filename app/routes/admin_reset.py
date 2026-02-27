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
        from app.models.instrument import Instrument, DEFAULT_INSTRUMENTS

        before = db.session.execute(db.text('SELECT COUNT(*) FROM instruments')).scalar()

        # Find instrument IDs that are referenced by trades (cannot delete these)
        referenced_ids = set(row[0] for row in db.session.execute(
            db.text('SELECT DISTINCT instrument_id FROM trades WHERE instrument_id IS NOT NULL')
        ).fetchall())

        # Delete aliases for unreferenced instruments only
        if referenced_ids:
            db.session.execute(db.text(
                f'DELETE FROM instrument_aliases WHERE instrument_id NOT IN ({",".join(str(i) for i in referenced_ids)})'
            ))
            db.session.execute(db.text(
                f'DELETE FROM instruments WHERE id NOT IN ({",".join(str(i) for i in referenced_ids)})'
            ))
        else:
            db.session.execute(db.text('DELETE FROM instrument_aliases'))
            db.session.execute(db.text('DELETE FROM instruments'))

        db.session.commit()

        after_clear = db.session.execute(db.text('SELECT COUNT(*) FROM instruments')).scalar()

        # Now insert all DEFAULT_INSTRUMENTS that don't already exist
        inserted = 0
        skipped = 0
        for inst_data in DEFAULT_INSTRUMENTS:
            symbol = inst_data.get('symbol', '').upper()
            existing = db.session.execute(
                db.text('SELECT id FROM instruments WHERE symbol = :sym'),
                {'sym': symbol}
            ).fetchone()
            if not existing:
                instrument = Instrument(
                    symbol=symbol,
                    name=inst_data.get('name', symbol),
                    instrument_type=inst_data.get('instrument_type', 'forex'),
                    category=inst_data.get('category', 'Forex'),
                    pip_size=inst_data.get('pip_size', 0.0001),
                    tick_value=inst_data.get('tick_value', 1.0),
                    contract_size=inst_data.get('contract_size', 100000),
                    price_decimals=inst_data.get('price_decimals', 5),
                    lot_min=inst_data.get('lot_min', 0.01),
                    lot_max=inst_data.get('lot_max', 100.0),
                    margin_rate=inst_data.get('margin_rate'),
                    is_active=True
                )
                db.session.add(instrument)
                inserted += 1
            else:
                skipped += 1

        db.session.commit()
        after = db.session.execute(db.text('SELECT COUNT(*) FROM instruments')).scalar()

        # Get category breakdown
        categories = db.session.execute(db.text(
            'SELECT category, COUNT(*) FROM instruments GROUP BY category ORDER BY category'
        )).fetchall()

        return jsonify({
            'status': 'success',
            'before': before,
            'after': after,
            'inserted': inserted,
            'skipped_existing': skipped,
            'referenced_kept': list(referenced_ids),
            'categories': {row[0]: row[1] for row in categories}
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
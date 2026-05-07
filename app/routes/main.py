"""
Main Routes
Homepage and general application routes
"""

from flask import Blueprint, render_template, redirect, url_for, request, jsonify, send_from_directory, current_app
from flask_login import current_user
from app.models.instrument import Instrument
from datetime import datetime

# Create Blueprint
bp = Blueprint('main', __name__)

@bp.route('/robots.txt')
def robots():
    """Serve robots.txt for Google crawlers"""
    static_folder = current_app.static_folder
    return send_from_directory(static_folder, 'robots.txt')

@bp.route('/favicon.ico')
def favicon():
    """Serve a root favicon for crawlers/browsers expecting /favicon.ico."""
    return send_from_directory(
        current_app.static_folder,
        'img/favicon.png',
        mimetype='image/png',
    )


@bp.route('/sitemap.xml')
def sitemap():
    """Simple sitemap for public marketing pages."""
    from flask import Response

    pages = [
        url_for('main.index', _external=True),
        url_for('main.about', _external=True),
        url_for('main.features', _external=True),
        url_for('main.contact', _external=True),
        url_for('monetization.pricing', _external=True),
    ]
    now = datetime.utcnow().strftime('%Y-%m-%d')
    body = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for p in pages:
        body.append('<url>')
        body.append(f'<loc>{p}</loc>')
        body.append(f'<lastmod>{now}</lastmod>')
        body.append('<changefreq>weekly</changefreq>')
        body.append('<priority>0.8</priority>')
        body.append('</url>')
    body.append('</urlset>')
    return Response('\n'.join(body), mimetype='application/xml')

@bp.route('/')
def index():
    """
    Homepage - Landing page for TradeVerse
    
    If user is logged in, redirect to dashboard
    Otherwise, show the marketing homepage
    """
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    
    return render_template('main/index.html')

@bp.route('/about')
def about():
    """About page - Information about TradeVerse"""
    return render_template('main/about.html')

@bp.route('/features')
def features():
    """Features page - Showcase all features"""
    return render_template('main/features.html')

@bp.route('/pricing')
def pricing():
    """Pricing page - Subscription plans"""
    return redirect(url_for('monetization.pricing'), code=301)

@bp.route('/contact')
def contact():
    """Contact page - Contact form"""
    return render_template('main/contact.html')


@bp.route('/api/calculate-pnl', methods=['POST'])
def calculate_pnl():
    """
    Calculate P&L for a trade based on instrument type and prices
    
    Request body:
    {
        "instrument_id": 1,
        "entry_price": 1.2000,
        "exit_price": 1.2050,
        "lot_size": 1.0,
        "trade_type": "BUY"
    }
    """
    try:
        data = request.get_json()
        
        instrument_id = data.get('instrument_id')
        entry_price = float(data.get('entry_price', 0))
        exit_price = float(data.get('exit_price', 0))
        lot_size = float(data.get('lot_size', 1.0))
        trade_type = data.get('trade_type', 'BUY')
        
        if not instrument_id or not entry_price or not exit_price:
            return jsonify({'error': 'Missing required fields'}), 400
        
        # Get instrument
        instrument = Instrument.query.get(instrument_id)
        if not instrument:
            return jsonify({'error': 'Instrument not found'}), 404
        
        # Single source of truth: use the same Exness-style calculator used for persisted trades.
        from app.services.pnl import calculate_trade_pnl

        pnl, pips_or_points, _method = calculate_trade_pnl(
            symbol=instrument.symbol,
            trade_type=trade_type,
            entry_price=entry_price,
            exit_price=exit_price,
            lot_size=lot_size,
        )
        
        return jsonify({
            'profit_loss': pnl,
            'pips_or_points': pips_or_points,
            'instrument_type': instrument.instrument_type,
            'instrument_symbol': instrument.symbol
        })
    
    except ValueError as e:
        return jsonify({'error': f'Invalid input: {str(e)}'}), 400
    except Exception:
        current_app.logger.exception("P&L calculation error")
        return jsonify({'error': 'Calculation error'}), 500
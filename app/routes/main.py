"""
Main Routes
Homepage and general application routes
"""

import os

from flask import Blueprint, render_template, redirect, url_for, request, jsonify, send_from_directory, current_app, abort
from flask_login import login_required, current_user
from app.models.instrument import Instrument
from datetime import datetime, date
from app.utils.timeutil import utc_now

# Create Blueprint
bp = Blueprint('main', __name__)

@bp.route('/robots.txt')
def robots():
    """
    robots.txt with absolute Sitemap URL (Google recommends absolute; avoids property mismatch).
    """
    from flask import Response
    from app.services.seo import public_site_origin

    origin = public_site_origin(current_app, request).rstrip("/")
    if not origin:
        origin = (request.url_root or "").rstrip("/")
    if not origin:
        static_folder = current_app.static_folder
        return send_from_directory(static_folder, "robots.txt")
    body = (
        "User-agent: *\n"
        "Allow: /\n"
        "\n"
        f"Sitemap: {origin}/sitemap.xml\n"
    )
    return Response(body, mimetype="text/plain; charset=utf-8")

@bp.route('/favicon.ico')
def favicon():
    """Serve a root favicon for crawlers/browsers expecting /favicon.ico."""
    # Prefer a real .ico if present; fall back to the PNG.
    try:
        return send_from_directory(current_app.static_folder, 'favicon.ico', mimetype='image/x-icon')
    except Exception:
        return send_from_directory(
            current_app.static_folder,
            'img/favicon.png',
            mimetype='image/png',
        )


@bp.route('/sitemap.xml')
def sitemap():
    """Simple sitemap for public marketing pages."""
    from flask import Response
    from app.services.seo import public_site_origin

    base = public_site_origin(current_app, request).rstrip("/")
    if not base:
        base = (request.url_root or "").rstrip("/")
    pages = [
        base + url_for('main.index'),
        base + url_for('main.about'),
        base + url_for('main.features'),
        base + url_for('main.contact'),
        base + url_for('main.terms'),
        base + url_for('main.privacy'),
    ]
    now = utc_now().strftime('%Y-%m-%d')
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

    # Weekly-rotating hero background for landing page.
    # Slot 0 is the current Apollo 11 visor image; additional slots
    # can be appended as more inspirational assets are added.
    hero_images = [
        'img/landing-space-hero.jpg',   # week 0 (current default)
        'img/landing-space-hero-1.jpg', # JWST deep field
        'img/landing-space-hero-2.jpg', # Earth (Apollo 17)
    ]
    try:
        weeks_since_epoch = (date.today() - date(2026, 1, 1)).days // 7
        idx = weeks_since_epoch % len(hero_images)
    except Exception:
        idx = 0

    hero_image_url = url_for('static', filename=hero_images[idx])

    return render_template('main/index.html', hero_image_url=hero_image_url)

@bp.route('/about')
def about():
    """About page - Information about TradeVerse"""
    return render_template('main/about.html')

@bp.route('/features')
def features():
    """Features page - Showcase all features"""
    return render_template('main/features.html')

@bp.route('/pricing')
@login_required
def pricing():
    """Pricing page for authenticated users inside the app."""
    from app.routes.monetization import render_pricing_page

    return render_pricing_page()

@bp.route('/contact')
def contact():
    """Contact page - Contact form"""
    return render_template('main/contact.html')


@bp.route('/terms')
def terms():
    """Terms and risk disclaimer (not financial advice)."""
    return render_template('main/terms.html')


@bp.route('/privacy')
def privacy():
    """Privacy policy — how we handle account and usage data."""
    return render_template('main/privacy.html')


@bp.route('/planner-screenshot/<path:stored>')
@login_required
def planner_screenshot_file(stored):
    """
    Serve Trade Planner before/after images.

    Files may live under TRADE_SCREENSHOTS_FOLDER (production volume / tmp) or
    app/static/uploads/trade_screenshots (development). DB stores paths like
    uploads/trade_screenshots/name.png.
    """
    rel = (stored or '').replace('\\', '/').strip()
    prefix = 'uploads/trade_screenshots/'
    if not rel.startswith(prefix):
        abort(404)
    fname = rel[len(prefix) :].strip()
    if not fname or '..' in fname or fname.startswith('/'):
        abort(404)

    cfg_dir = current_app.config.get('TRADE_SCREENSHOTS_FOLDER')
    static_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'trade_screenshots')

    for folder in (cfg_dir, static_dir):
        if not folder:
            continue
        full = os.path.join(folder, fname)
        if os.path.isfile(full):
            return send_from_directory(folder, fname)
    abort(404)


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
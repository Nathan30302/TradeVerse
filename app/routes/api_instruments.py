"""
API Routes for Instrument Search and Management

Provides endpoints for:
- Instrument search with fuzzy matching
- Instrument metadata lookup
- Broker listing
"""
from flask import Blueprint, request, jsonify
from sqlalchemy import func
from flask_login import login_required, current_user

from app.services.instrument_catalog import (
    catalog, search_instruments, get_instrument, get_instrument_metadata
)
from app.mappers.instrument_mapper import (
    mapper, map_broker_symbol, list_available_brokers, get_broker_profile
)

bp = Blueprint('api_instruments', __name__, url_prefix='/api')


@bp.route('/instruments', methods=['GET'])
@login_required
def search_instruments_api():
    """
    Search instruments with ranking and filtering.
    """
    query = request.args.get('q', '').strip()
    broker_id = request.args.get('broker', '')
    inst_type = request.args.get('type', '')
    
    try:
        limit = min(int(request.args.get('limit', 20)), 100)
        offset = int(request.args.get('offset', 0))
    except ValueError:
        limit = 20
        offset = 0
    
    if broker_id and query:
        mapping = map_broker_symbol(query, broker_id)
        if mapping.confidence >= 0.8:
            query = mapping.canonical_symbol
    
    results = search_instruments(
        query=query,
        limit=limit,
        offset=offset,
        inst_type=inst_type if inst_type else None
    )
    
    response_results = []
    for r in results:
        response_results.append({
            'symbol': r['symbol'],
            'display_name': r.get('display_name', r['symbol']),
            'type': r.get('type', 'unknown'),
            'score': r.get('_score', 0),
            'metadata': {
                'pip_or_tick_size': r.get('pip_or_tick_size'),
                'tick_value': r.get('tick_value'),
                'contract_size': r.get('contract_size'),
                'price_decimals': r.get('price_decimals')
            }
        })
    
    total = results[0].get('_total', len(results)) if results else 0
    
    return jsonify({
        'success': True,
        'results': response_results,
        'total': total,
        'limit': limit,
        'offset': offset,
        'query': query
    })


@bp.route('/instruments/<symbol>', methods=['GET'])
@login_required
def get_instrument_api(symbol):
    """Get full metadata for a specific instrument."""
    instrument = get_instrument(symbol)
    
    if not instrument:
        return jsonify({'success': False, 'error': 'Instrument not found'}), 404
    
    metadata = get_instrument_metadata(symbol)
    
    return jsonify({
        'success': True,
        'instrument': {
            'symbol': instrument['symbol'],
            'display_name': instrument.get('display_name', instrument['symbol']),
            'type': instrument.get('type', 'unknown'),
            'aliases': instrument.get('aliases', []),
            'pip_or_tick_size': instrument.get('pip_or_tick_size'),
            'tick_value': instrument.get('tick_value'),
            'contract_size': instrument.get('contract_size'),
            'price_decimals': instrument.get('price_decimals'),
            'notes': instrument.get('notes', '')
        }
    })


@bp.route('/instruments/map', methods=['POST'])
@login_required
def map_instrument_api():
    """Map a broker-specific symbol to canonical form."""
    data = request.get_json()
    
    if not data:
        return jsonify({'success': False, 'error': 'Request body required'}), 400
    
    symbol = data.get('symbol', '').strip()
    broker_id = data.get('broker_id', 'generic')
    
    if not symbol:
        return jsonify({'success': False, 'error': 'Symbol required'}), 400
    
    result = map_broker_symbol(symbol, broker_id)
    
    return jsonify({
        'success': True,
        'mapping': {
            'original_symbol': result.original_symbol,
            'canonical_symbol': result.canonical_symbol,
            'broker_id': result.broker_id,
            'confidence': result.confidence,
            'match_type': result.match_type,
            'warnings': result.warnings,
            'instrument': result.instrument_metadata
        }
    })


@bp.route('/instruments/batch-map', methods=['POST'])
@login_required
def batch_map_instruments_api():
    """Map multiple broker symbols to canonical form."""
    data = request.get_json()
    
    if not data:
        return jsonify({'success': False, 'error': 'Request body required'}), 400
    
    symbols = data.get('symbols', [])
    broker_id = data.get('broker_id', 'generic')
    
    if not symbols or not isinstance(symbols, list):
        return jsonify({'success': False, 'error': 'Symbols array required'}), 400
    
    report = mapper.get_mapping_report(symbols, broker_id)
    
    return jsonify({'success': True, 'report': report})


@bp.route('/brokers', methods=['GET'])
@login_required
def list_brokers_api():
    """List all available broker profiles."""
    brokers = list_available_brokers()
    return jsonify({'success': True, 'brokers': brokers})


@bp.route('/brokers/<broker_id>', methods=['GET'])
@login_required
def get_broker_api(broker_id):
    """Get full broker profile details."""
    broker = get_broker_profile(broker_id)
    
    if not broker:
        return jsonify({'success': False, 'error': 'Broker not found'}), 404
    
    safe_broker = {
        'id': broker.get('id'),
        'name': broker.get('name'),
        'description': broker.get('description'),
        'api_supported': broker.get('api_supported', False),
        'api_type': broker.get('api_type'),
        'api_docs_url': broker.get('api_docs_url'),
        'import_formats': broker.get('import_formats', []),
        'account_currency_options': broker.get('account_currency_options', []),
        'website': broker.get('website'),
        'notes': broker.get('notes')
    }
    
    return jsonify({'success': True, 'broker': safe_broker})


@bp.route('/instruments/stats', methods=['GET'])
@login_required
def get_instrument_stats():
    """Get statistics about the instrument catalog."""
    types = {}
    for inst in catalog.get_all():
        t = inst.get('type', 'unknown')
        types[t] = types.get(t, 0) + 1
    
    return jsonify({
        'success': True,
        'stats': {
            'total_instruments': catalog.count,
            'by_type': types
        }
    })


# =============================================================================
# STANDARDIZED CATEGORY MAPPING - EXACTLY 8 CATEGORIES (NO DUPLICATES)
# Template has: crypto, crypto_cross, energies, forex, forex_indicator, idx_large, index, stocks
# =============================================================================

# Map DB category names to EXACTLY 8 template category keys
DB_TO_FRONTEND_CATEGORY = {
    'Crypto': 'crypto',
    'Crypto Cross': 'crypto_cross',
    'Energies': 'energies',
    'Forex': 'forex',
    'Forex Indicator': 'forex_indicator',
    'IDX-Large': 'idx_large',
    'Indices': 'index',
    'Stocks': 'stocks',
}

# Reverse mapping: frontend key -> DB category names to search
FRONTEND_TO_DB_CATEGORY = {
    'crypto': ['Crypto'],
    'crypto_cross': ['Crypto Cross'],
    'energies': ['Energies'],
    'forex': ['Forex'],
    'forex_indicator': ['Forex Indicator'],
    'idx_large': ['IDX-Large'],
    'index': ['Indices'],
    'stocks': ['Stocks'],
}


@bp.route('/db/instruments/categories', methods=['GET'])
@login_required
def db_instrument_categories():
    """Return EXACTLY 8 unique categories matching the template - NO duplicates."""
    from app.models.instrument import Instrument
    
    # The EXACT 8 categories from the template (ORDER MATTERS)
    template_categories = [
        {'key': 'crypto', 'name': 'Crypto'},
        {'key': 'crypto_cross', 'name': 'Crypto Cross'},
        {'key': 'energies', 'name': 'Energies'},
        {'key': 'forex', 'name': 'Forex'},
        {'key': 'forex_indicator', 'name': 'Forex Indicator'},
        {'key': 'idx_large', 'name': 'IDX Large'},
        {'key': 'index', 'name': 'Indices'},
        {'key': 'stocks', 'name': 'Stocks'},
    ]
    
    # Check which categories have instruments in DB
    q = Instrument.query.with_entities(Instrument.category).distinct().all()
    db_categories = set(c[0] for c in q if c[0])
    
    # Build result with only unique keys - no duplicates
    result = {}
    for cat in template_categories:
        # Find matching DB category
        matching_db = None
        for db_cat, frontend_key in DB_TO_FRONTEND_CATEGORY.items():
            if frontend_key == cat['key'] and db_cat in db_categories:
                matching_db = db_cat
                break
        
        # Only add category if instruments exist in DB
        if matching_db:
            result[cat['key']] = {'name': cat['name']}
    
    # Always include main categories even if empty (for demo purposes)
    # This ensures we have 8 categories visible
    for cat in template_categories:
        if cat['key'] not in result:
            result[cat['key']] = {'name': cat['name']}
    
    print(f"[db_instrument_categories] Returning {len(result)} unique categories: {list(result.keys())}")
    return jsonify({'success': True, 'categories': result})


@bp.route('/db/instruments', methods=['GET'])
@login_required
def db_instruments():
    """Return instruments stored in DB for a given category (or all)."""
    from app.models.instrument import Instrument
    from sqlalchemy import or_
    
    category = request.args.get('category', '').strip()
    limit = min(int(request.args.get('limit', 1000)), 5000)
    q = Instrument.query.filter(Instrument.is_active == True)
    
    if category:
        # Get the DB category names to search
        db_categories = FRONTEND_TO_DB_CATEGORY.get(category.lower(), [category])
        
        # Build OR filter for all possible DB category values
        filters = []
        for db_cat in db_categories:
            filters.append(Instrument.category.ilike(f"%{db_cat}%"))
        
        # Apply the filter
        if filters:
            q = q.filter(or_(*filters))
    
    instruments = q.order_by(Instrument.symbol).limit(limit).all()
    
    # Debug: log what we're returning
    print(f"[db_instruments] category={category}, found={len(instruments)}")
    
    out = []
    for inst in instruments:
        out.append({
            'id': inst.id,
            'symbol': inst.symbol,
            'name': inst.name,
            'type': inst.instrument_type,
            'category': inst.category,
            'pip_size': inst.pip_size,
            'tick_value': inst.tick_value,
            'contract_size': inst.contract_size,
            'price_decimals': inst.price_decimals
        })
    
    # Console log for debugging
    print(f"TOTAL INSTRUMENTS for {category}: {len(out)}")
    
    return jsonify({'success': True, 'results': out, 'total': len(out)})


@bp.route('/db/instruments/counts', methods=['GET'])
@login_required
def db_instrument_counts():
    """Return total instruments and counts per category."""
    from app.models.instrument import Instrument
    
    total = Instrument.query.filter(Instrument.is_active == True).count()
    
    # Per category with proper mapping
    rows = Instrument.query.with_entities(
        Instrument.category, func.count(Instrument.id)
    ).filter(Instrument.is_active == True).group_by(Instrument.category).all()
    
    counts = {}
    for cat, cnt in rows:
        mapped_cat = DB_TO_FRONTEND_CATEGORY.get(cat, cat.lower() if cat else 'other')
        counts[mapped_cat] = cnt
    
    print(f"[db_instrument_counts] Total: {total}, By category: {counts}")
    
    return jsonify({'success': True, 'total': total, 'by_category': counts})


@bp.route('/db/instruments/quotes', methods=['GET'])
@login_required
def db_instrument_quotes():
    """Return trader-focused instruments for the Dynamic Island rotator."""
    from app.models.instrument import Instrument
    from app.services.simulated_market import market

    trader_focused = ['BTCUSD', 'XAUUSD', 'NAS100', 'US30', 'US500', 'EURUSD']
    limit = min(int(request.args.get('limit', 6)), 10)

    inst_objs = {}
    db_insts = Instrument.query.filter(Instrument.symbol.in_(trader_focused)).all()
    for i in db_insts:
        inst_objs[i.symbol] = i

    symbols = trader_focused[:limit]
    quotes = market.get_quotes(symbols, instrument_objs=inst_objs)

    fallback_names = {
        'BTCUSD': 'Bitcoin', 'XAUUSD': 'Gold', 'NAS100': 'Nasdaq 100',
        'US30': 'US30', 'US500': 'S&P 500', 'EURUSD': 'EUR/USD'
    }
    
    out = []
    for q in quotes:
        name = q.get('name') or fallback_names.get(q['symbol'], q['symbol'])
        out.append({
            'symbol': q['symbol'],
            'name': name,
            'price': q['price'],
            'change_pct': q['change_pct']
        })

    return jsonify({'success': True, 'quotes': out})

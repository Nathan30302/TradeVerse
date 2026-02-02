"""
API Routes for Instrument Search and Management

Provides endpoints for:
- Instrument search with fuzzy matching
- Instrument metadata lookup
- Broker listing
"""
from flask import Blueprint, request, jsonify
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
    
    Query params:
        q: Search query (optional, returns popular if empty)
        broker: Broker ID for symbol normalization (optional)
        type: Filter by instrument type (forex, index, commodity, crypto, stock)
        limit: Max results (default 20, max 100)
        offset: Pagination offset
        
    Returns:
        JSON with results array containing instruments with scores
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
    """
    Get full metadata for a specific instrument.
    
    Args:
        symbol: Canonical instrument symbol
        
    Returns:
        JSON with instrument metadata
    """
    instrument = get_instrument(symbol)
    
    if not instrument:
        return jsonify({
            'success': False,
            'error': 'Instrument not found'
        }), 404
    
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
    """
    Map a broker-specific symbol to canonical form.
    
    Request body:
        symbol: Broker symbol to map
        broker_id: Broker identifier
        
    Returns:
        Mapping result with confidence score
    """
    data = request.get_json()
    
    if not data:
        return jsonify({
            'success': False,
            'error': 'Request body required'
        }), 400
    
    symbol = data.get('symbol', '').strip()
    broker_id = data.get('broker_id', 'generic')
    
    if not symbol:
        return jsonify({
            'success': False,
            'error': 'Symbol required'
        }), 400
    
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
    """
    Map multiple broker symbols to canonical form.
    
    Request body:
        symbols: Array of symbols to map
        broker_id: Broker identifier
        
    Returns:
        Mapping results for all symbols
    """
    data = request.get_json()
    
    if not data:
        return jsonify({
            'success': False,
            'error': 'Request body required'
        }), 400
    
    symbols = data.get('symbols', [])
    broker_id = data.get('broker_id', 'generic')
    
    if not symbols or not isinstance(symbols, list):
        return jsonify({
            'success': False,
            'error': 'Symbols array required'
        }), 400
    
    report = mapper.get_mapping_report(symbols, broker_id)
    
    return jsonify({
        'success': True,
        'report': report
    })


@bp.route('/brokers', methods=['GET'])
@login_required
def list_brokers_api():
    """
    List all available broker profiles.
    
    Returns:
        Array of broker profiles with basic info
    """
    brokers = list_available_brokers()
    
    return jsonify({
        'success': True,
        'brokers': brokers
    })


@bp.route('/brokers/<broker_id>', methods=['GET'])
@login_required
def get_broker_api(broker_id):
    """
    Get full broker profile details.
    
    Args:
        broker_id: Broker identifier
        
    Returns:
        Full broker profile
    """
    broker = get_broker_profile(broker_id)
    
    if not broker:
        return jsonify({
            'success': False,
            'error': 'Broker not found'
        }), 404
    
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
    
    return jsonify({
        'success': True,
        'broker': safe_broker
    })


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

"""
Instruments API Routes
Provides searchable instrument list with metadata for the modern picker UI
Includes FTS5-powered fuzzy search for production scale
"""

from flask import Blueprint, jsonify, request, current_app
from app.models.instrument import Instrument, DEFAULT_INSTRUMENTS
from app.models.trade import Trade
from app import db
from app.services.pnl_calculator_advanced import PnLCalculator, detect_instrument_type
from app.mappers.instrument_mapper import map_broker_symbol
from app.models.instrument_fts import hybrid_search_instruments, search_instruments_fts
import os
import json
import difflib

bp = Blueprint('instruments', __name__, url_prefix='/api/instruments')

@bp.route('', methods=['GET'])
def get_instruments():
    """
    Get searchable list of instruments with hybrid search (exact + alias + FTS fuzzy).
    
    Query parameters:
    - search: Filter by symbol or name (case-insensitive, supports fuzzy matching)
    - category: Filter by category (forex, index, crypto, stock, commodity)
    - limit: Max results (default 50, max 200)
    - broker: Broker ID for broker-aware mapping (e.g., 'ig', 'oanda', 'binance')
    - fuzzy: Enable FTS fuzzy search (default true)
    """
    # support q alias and broker-specific mapping
    search = request.args.get('search') or request.args.get('q') or ''
    search = search.upper().strip()
    category = request.args.get('category', '')
    limit = min(int(request.args.get('limit', 50)), 10000)
    broker = request.args.get('broker')
    fuzzy = request.args.get('fuzzy', 'true').lower() in ('true', '1', 'yes')
    
    # If no search provided, return a simple list ordered by symbol
    if not search:
        query = Instrument.query.filter_by(is_active=True)
        if category:
            query = query.filter_by(category=category.lower())
        instruments = query.order_by(Instrument.symbol).limit(limit).all()
        return jsonify([i.to_dict() for i in instruments])

    # Hybrid search: exact + alias + broker-aware + FTS fuzzy
    if fuzzy:
        try:
            results = hybrid_search_instruments(search, broker_id=broker, limit=limit)
            # Add full metadata to results
            full_results = []
            for res in results:
                inst = Instrument.query.get(res['id'])
                if inst:
                    data = inst.to_dict()
                    data['match_type'] = res.get('match_type', 'unknown')
                    data['search_score'] = res.get('score', 0)
                    full_results.append(data)
            return jsonify(full_results)
        except Exception as e:
            current_app.logger.error(f"Hybrid search error: {e}")
    
    # Fallback: basic search if FTS not available
    candidates = Instrument.query.filter_by(is_active=True).all()
    results = []
    q = search.lower()

    # If broker normalization available, try to map broker-specific symbol to canonical symbol
    mapped_symbol = None
    if broker and q:
        can_sym, conf, details = map_broker_symbol(broker, q)
        if can_sym:
            mapped_symbol = can_sym.upper()

    from app.models.instrument import InstrumentAlias

    def get_aliases(inst):
        try:
            # Prefer DB-backed aliases for performance and scale
            rows = InstrumentAlias.query.filter_by(instrument_id=inst.id).all()
            if rows:
                return [r.alias.lower() for r in rows]
            # fallback: parse description JSON
            if inst.description:
                parsed = json.loads(inst.description)
                if isinstance(parsed, dict) and 'aliases' in parsed and isinstance(parsed['aliases'], list):
                    return [a.lower() for a in parsed['aliases']]
        except Exception:
            return []
        return []

    for inst in candidates:
        score = 0
        sym = (inst.symbol or '').lower()
        name = (inst.name or '').lower()
        aliases = get_aliases(inst)

        # Boost if this is the broker-mapped canonical symbol
        if mapped_symbol and sym == mapped_symbol.lower():
            score += 150

        # Exact symbol match highest
        if q == sym:
            score += 100

        # Symbol startswith
        if sym.startswith(q):
            score += 50

        # Name startswith
        if name.startswith(q):
            score += 30

        # Alias exact or startswith
        for a in aliases:
            if q == a:
                score += 80
            elif a.startswith(q):
                score += 40

        # Contains in symbol or name
        if q in sym or q in name:
            score += 20

        # Fuzzy similarity boost (difflib)
        sym_ratio = difflib.SequenceMatcher(None, q, sym).ratio()
        name_ratio = difflib.SequenceMatcher(None, q, name).ratio()
        best_ratio = max(sym_ratio, name_ratio)
        if best_ratio > 0.6:
            score += int(best_ratio * 10)

        if score > 0:
            results.append((score, inst))

    # Sort by score desc then symbol
    results.sort(key=lambda x: (-x[0], x[1].symbol))
    instruments = [inst.to_dict() for _, inst in results[:limit]]
    return jsonify(instruments)


@bp.route('/<int:id>', methods=['GET'])
def get_instrument(id):
    """Get a single instrument by ID"""
    instrument = Instrument.query.get_or_404(id)
    return jsonify(instrument.to_dict())


@bp.route('/by-symbol/<symbol>', methods=['GET'])
def get_instrument_by_symbol(symbol):
    """Get instrument by symbol"""
    instrument = Instrument.query.filter_by(symbol=symbol.upper()).first_or_404()
    return jsonify(instrument.to_dict())


@bp.route('/categories', methods=['GET'])
def get_categories():
    """Get available instrument categories with count"""
    categories = db.session.query(
        Instrument.category,
        db.func.count(Instrument.id).label('count')
    ).filter_by(is_active=True).group_by(Instrument.category).all()
    
    return jsonify({
        cat: count for cat, count in categories
    })


@bp.before_request
def ensure_instruments():
    """
    Ensure default instruments exist in database.
    Runs on first API call to populate instruments.
    """
    # Seed from a catalog file if present, otherwise fallback to DEFAULT_INSTRUMENTS
    if Instrument.query.first() is None:
        # Look in project root data folder - use EXNESS full catalog
        project_root = os.path.dirname(os.path.dirname(current_app.root_path))
        
        # First try exness_full_catalog.json (has 400+ instruments with 8 sectors)
        catalog_path = os.path.join(project_root, 'data', 'exness_full_catalog.json')
        
        seed_list = DEFAULT_INSTRUMENTS
        if os.path.exists(catalog_path):
            try:
                with open(catalog_path, 'r', encoding='utf-8') as fh:
                    data = json.load(fh)
                    # Handle both formats: {"meta":..., "instruments": [...]} or just [...]
                    if isinstance(data, dict) and 'instruments' in data:
                        seed_list = data['instruments']
                    elif isinstance(data, list):
                        seed_list = data
            except Exception:
                seed_list = DEFAULT_INSTRUMENTS

        # Deduplicate by symbol to avoid unique constraint errors
        seen_symbols = set()
        unique_instruments = []
        for inst_data in seed_list:
            symbol = inst_data.get('symbol', '').upper()
            if symbol and symbol not in seen_symbols:
                seen_symbols.add(symbol)
                unique_instruments.append(inst_data)

        for inst_data in unique_instruments:
            existing = Instrument.query.filter_by(symbol=inst_data['symbol'].upper()).first()
            if not existing:
                # Map the EXNESS fields to our model fields
                instrument = Instrument(
                    symbol=inst_data.get('symbol', '').upper(),
                    name=inst_data.get('name', inst_data.get('symbol', '')),
                    instrument_type=inst_data.get('instrument_type', 'forex'),
                    category=inst_data.get('category', 'Forex'),
                    pip_size=inst_data.get('pip_size', 0.0001),
                    tick_value=inst_data.get('tick_value', 1.0),
                    contract_size=inst_data.get('contract_size', 100000),
                    price_decimals=inst_data.get('price_decimals', 5),
                    is_active=True
                )
                db.session.add(instrument)

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()

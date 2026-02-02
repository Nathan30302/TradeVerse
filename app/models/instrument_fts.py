"""
Full-Text Search (FTS) support for instruments using SQLite FTS5.
Provides fast fuzzy search, typo tolerance, and phrase matching.
"""
from app import db
from sqlalchemy import event, text
import logging

logger = logging.getLogger(__name__)


class InstrumentFTS(db.Model):
    """Virtual FTS5 table for instrument search."""
    __tablename__ = 'instruments_fts'
    
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(50))
    name = db.Column(db.String(200))
    aliases = db.Column(db.String(500))  # comma-separated alias list
    category = db.Column(db.String(50))


def build_fts_index():
    """Build the FTS index from instruments table."""
    try:
        with db.engine.connect() as conn:
            # Drop existing FTS table if present
            conn.execute(text("DROP TABLE IF EXISTS instruments_fts"))
            conn.commit()
            
            # Create FTS5 virtual table
            conn.execute(text("""
                CREATE VIRTUAL TABLE instruments_fts USING fts5(
                    symbol,
                    name,
                    aliases,
                    category,
                    content=instruments,
                    content_rowid=id
                )
            """))
            conn.commit()
            
            # Populate FTS table from instruments
            conn.execute(text("""
                INSERT INTO instruments_fts(rowid, symbol, name, aliases, category)
                SELECT 
                    i.id,
                    i.symbol,
                    i.name,
                    GROUP_CONCAT(ia.alias, ','),
                    i.category
                FROM instruments i
                LEFT JOIN instrument_aliases ia ON i.id = ia.instrument_id
                GROUP BY i.id
            """))
            conn.commit()
            
            logger.info("FTS index built successfully")
            return True
    except Exception as e:
        logger.error(f"Failed to build FTS index: {e}")
        return False


def search_instruments_fts(query: str, limit: int = 20, ranked=True) -> list:
    """
    Search instruments using FTS5 with ranking.
    
    Supports:
    - Prefix search: "eur*" matches EURUSD, EURJPY
    - Phrase search: '"gold future"'
    - OR logic: "EUR OR GBP"
    - AND logic: "EUR AND USD"
    - Negation: "-crypto"
    """
    if not query or len(query.strip()) < 2:
        return []
    
    try:
        # Escape and prepare query
        escaped_query = query.strip().replace('"', '""')
        
        if ranked:
            # Use BM25 ranking (built-in FTS5 function)
            sql = text("""
                SELECT 
                    i.id,
                    i.symbol,
                    i.name,
                    i.instrument_type,
                    i.category,
                    i.description,
                    rank,
                    'fts' as match_type
                FROM instruments_fts f
                JOIN instruments i ON f.rowid = i.id
                WHERE instruments_fts MATCH :query
                ORDER BY rank, i.symbol
                LIMIT :limit
            """)
        else:
            # Simple match without ranking
            sql = text("""
                SELECT 
                    i.id,
                    i.symbol,
                    i.name,
                    i.instrument_type,
                    i.category,
                    i.description,
                    0 as rank,
                    'fts' as match_type
                FROM instruments_fts f
                JOIN instruments i ON f.rowid = i.id
                WHERE instruments_fts MATCH :query
                LIMIT :limit
            """)
        
        with db.engine.connect() as conn:
            result = conn.execute(sql, {'query': escaped_query, 'limit': limit})
            return [dict(row._mapping) for row in result]
    
    except Exception as e:
        logger.error(f"FTS search failed for query '{query}': {e}")
        return []


def hybrid_search_instruments(query: str, broker_id: str = None, limit: int = 20,
                               instrument_mapper=None) -> list:
    """
    Hybrid search combining FTS (typo-tolerant) + exact/alias match + broker mapping.
    Returns ranked results with match type indicators.
    """
    results = []
    seen_ids = set()
    
    # 1. Exact symbol match (highest priority)
    try:
        exact = db.session.execute(
            db.text("SELECT * FROM instruments WHERE symbol = :sym LIMIT 1"),
            {'sym': query.upper()}
        ).fetchone()
        if exact:
            results.append({
                'id': exact.id,
                'symbol': exact.symbol,
                'name': exact.name,
                'instrument_type': exact.instrument_type,
                'category': exact.category,
                'match_type': 'exact',
                'score': 100
            })
            seen_ids.add(exact.id)
    except Exception as e:
        logger.debug(f"Exact match failed: {e}")
    
    # 2. Broker-aware mapping (if mapper provided)
    if instrument_mapper and broker_id:
        try:
            mapped = instrument_mapper(broker_id, query)
            if mapped and mapped.get('canonical_symbol'):
                inst = db.session.execute(
                    db.text("SELECT * FROM instruments WHERE symbol = :sym LIMIT 1"),
                    {'sym': mapped['canonical_symbol']}
                ).fetchone()
                if inst and inst.id not in seen_ids:
                    results.append({
                        'id': inst.id,
                        'symbol': inst.symbol,
                        'name': inst.name,
                        'instrument_type': inst.instrument_type,
                        'category': inst.category,
                        'match_type': f"broker_map ({mapped.get('confidence', 0):.0%})",
                        'score': 90 + int(mapped.get('confidence', 0.5) * 10)
                    })
                    seen_ids.add(inst.id)
        except Exception as e:
            logger.debug(f"Broker mapping failed: {e}")
    
    # 3. Alias match
    try:
        alias_matches = db.session.execute(
            db.text("""
                SELECT DISTINCT i.* FROM instruments i
                JOIN instrument_aliases ia ON i.id = ia.instrument_id
                WHERE ia.alias LIKE :query OR ia.alias = :exact
                LIMIT 10
            """),
            {'query': f"%{query}%", 'exact': query.upper()}
        ).fetchall()
        for row in alias_matches:
            if row.id not in seen_ids:
                results.append({
                    'id': row.id,
                    'symbol': row.symbol,
                    'name': row.name,
                    'instrument_type': row.instrument_type,
                    'category': row.category,
                    'match_type': 'alias',
                    'score': 80
                })
                seen_ids.add(row.id)
    except Exception as e:
        logger.debug(f"Alias search failed: {e}")
    
    # 4. FTS search (fuzzy match for typos)
    fts_results = search_instruments_fts(query, limit=limit, ranked=True)
    for fts_row in fts_results:
        if fts_row['id'] not in seen_ids:
            results.append({
                'id': fts_row['id'],
                'symbol': fts_row['symbol'],
                'name': fts_row['name'],
                'instrument_type': fts_row['instrument_type'],
                'category': fts_row['category'],
                'match_type': 'fts_fuzzy',
                'score': 60
            })
            seen_ids.add(fts_row['id'])
    
    # Sort by score and return
    results.sort(key=lambda x: (-x['score'], x['symbol']))
    return results[:limit]

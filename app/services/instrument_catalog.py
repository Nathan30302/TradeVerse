"""
Instrument Catalog Service

Loads and manages the instrument database, providing search, fuzzy-match,
alias normalization, and metadata lookup capabilities.
"""
import json
import os
import re
from typing import Optional, List, Dict, Any
from difflib import SequenceMatcher
from functools import lru_cache


class InstrumentCatalog:
    """
    Singleton service for instrument data management.
    Loads instruments from JSON and provides search/lookup functionality.
    """
    
    _instance = None
    _instruments: List[Dict[str, Any]] = []
    _symbol_index: Dict[str, Dict[str, Any]] = {}
    _alias_index: Dict[str, str] = {}
    _type_index: Dict[str, List[Dict[str, Any]]] = {}
    _popular_symbols: List[str] = []
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_instruments()
        return cls._instance
    
    def _load_instruments(self) -> None:
        """Load instruments from JSON file."""
        json_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'data', 'instruments.json'
        )
        
        if not os.path.exists(json_path):
            self._instruments = []
            return
        
        with open(json_path, 'r', encoding='utf-8') as f:
            self._instruments = json.load(f)
        
        self._build_indexes()
    
    def _build_indexes(self) -> None:
        """Build lookup indexes for fast searching."""
        self._symbol_index = {}
        self._alias_index = {}
        self._type_index = {}
        
        for instrument in self._instruments:
            symbol = instrument['symbol'].upper()
            self._symbol_index[symbol] = instrument
            
            for alias in instrument.get('aliases', []):
                alias_upper = alias.upper()
                self._alias_index[alias_upper] = symbol
            
            inst_type = instrument.get('type', 'unknown')
            if inst_type not in self._type_index:
                self._type_index[inst_type] = []
            self._type_index[inst_type].append(instrument)
        
        self._popular_symbols = [
            'EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD', 'US500', 'US100', 'US30',
            'BTCUSD', 'ETHUSD', 'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA',
            'GER40', 'UK100', 'JPN225', 'USOIL', 'NATGAS'
        ]
    
    def reload(self) -> None:
        """Reload instruments from disk."""
        self._load_instruments()
    
    @property
    def count(self) -> int:
        """Return total number of instruments."""
        return len(self._instruments)
    
    def get_all(self) -> List[Dict[str, Any]]:
        """Return all instruments."""
        return self._instruments.copy()
    
    def get_by_symbol(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get instrument by exact symbol match."""
        return self._symbol_index.get(symbol.upper())
    
    def get_by_alias(self, alias: str) -> Optional[Dict[str, Any]]:
        """Get instrument by alias lookup."""
        alias_upper = alias.upper()
        if alias_upper in self._alias_index:
            canonical = self._alias_index[alias_upper]
            return self._symbol_index.get(canonical)
        return None
    
    def get_by_type(self, inst_type: str) -> List[Dict[str, Any]]:
        """Get all instruments of a specific type."""
        return self._type_index.get(inst_type, []).copy()
    
    def normalize_symbol(self, symbol: str) -> str:
        """
        Normalize a symbol to its canonical form.
        Handles common variations like underscores, slashes, suffixes.
        """
        if not symbol:
            return ''
        
        normalized = symbol.upper().strip()
        normalized = re.sub(r'[_/\-\.\s]', '', normalized)
        normalized = re.sub(r'(\.M|\.PRO|\.ECN|\.RAW|MICRO|MINI)$', '', normalized, flags=re.IGNORECASE)
        
        if normalized in self._symbol_index:
            return normalized
        
        if normalized in self._alias_index:
            return self._alias_index[normalized]
        
        return normalized
    
    def resolve_symbol(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Resolve a symbol to its instrument, trying multiple strategies:
        1. Exact match
        2. Alias lookup
        3. Normalized match
        """
        upper = symbol.upper().strip()
        
        if upper in self._symbol_index:
            return self._symbol_index[upper]
        
        if upper in self._alias_index:
            return self._symbol_index.get(self._alias_index[upper])
        
        normalized = self.normalize_symbol(symbol)
        if normalized in self._symbol_index:
            return self._symbol_index[normalized]
        if normalized in self._alias_index:
            return self._symbol_index.get(self._alias_index[normalized])
        
        return None
    
    @lru_cache(maxsize=1000)
    def _fuzzy_score(self, s1: str, s2: str) -> float:
        """Calculate fuzzy match score between two strings."""
        return SequenceMatcher(None, s1.lower(), s2.lower()).ratio()
    
    def search(
        self,
        query: str,
        limit: int = 20,
        offset: int = 0,
        inst_type: Optional[str] = None,
        include_fuzzy: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Search instruments with ranking:
        1. Exact match (score: 1.0)
        2. Starts with query (score: 0.9)
        3. Contains query (score: 0.7)
        4. Alias match (score: 0.8)
        5. Fuzzy match (score: variable, min 0.5)
        
        Args:
            query: Search query
            limit: Maximum results to return
            offset: Number of results to skip
            inst_type: Filter by instrument type
            include_fuzzy: Whether to include fuzzy matches
            
        Returns:
            List of instruments with match scores
        """
        if not query:
            return self._get_popular(limit, offset, inst_type)
        
        query_upper = query.upper().strip()
        query_normalized = self.normalize_symbol(query)
        results = []
        seen = set()
        
        candidates = self._instruments
        if inst_type:
            candidates = self._type_index.get(inst_type, [])
        
        for instrument in candidates:
            symbol = instrument['symbol'].upper()
            display = instrument.get('display_name', '').upper()
            aliases = [a.upper() for a in instrument.get('aliases', [])]
            
            if symbol in seen:
                continue
            
            score = 0.0
            match_type = None
            
            if symbol == query_upper or symbol == query_normalized:
                score = 1.0
                match_type = 'exact'
            elif symbol.startswith(query_upper):
                score = 0.9
                match_type = 'startswith'
            elif query_upper in symbol or query_upper in display:
                score = 0.7
                match_type = 'contains'
            elif any(a == query_upper or a == query_normalized for a in aliases):
                score = 0.85
                match_type = 'alias_exact'
            elif any(a.startswith(query_upper) for a in aliases):
                score = 0.75
                match_type = 'alias_startswith'
            elif any(query_upper in a for a in aliases):
                score = 0.65
                match_type = 'alias_contains'
            elif include_fuzzy:
                fuzzy = self._fuzzy_score(query_upper, symbol)
                if fuzzy >= 0.5:
                    score = fuzzy * 0.6
                    match_type = 'fuzzy'
            
            if score > 0:
                seen.add(symbol)
                result = instrument.copy()
                result['_score'] = score
                result['_match_type'] = match_type
                results.append(result)
        
        results.sort(key=lambda x: (-x['_score'], x['symbol']))
        
        total = len(results)
        paginated = results[offset:offset + limit]
        
        for r in paginated:
            r['_total'] = total
        
        return paginated
    
    def _get_popular(
        self,
        limit: int,
        offset: int,
        inst_type: Optional[str]
    ) -> List[Dict[str, Any]]:
        """Return popular instruments."""
        results = []
        
        for symbol in self._popular_symbols:
            if symbol in self._symbol_index:
                inst = self._symbol_index[symbol].copy()
                if inst_type is None or inst.get('type') == inst_type:
                    inst['_score'] = 0.5
                    inst['_match_type'] = 'popular'
                    results.append(inst)
        
        return results[offset:offset + limit]
    
    def get_metadata(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get full metadata for an instrument including P&L calculation params.
        """
        instrument = self.resolve_symbol(symbol)
        if not instrument:
            return None
        
        return {
            'symbol': instrument['symbol'],
            'display_name': instrument.get('display_name', instrument['symbol']),
            'type': instrument.get('type', 'unknown'),
            'pip_or_tick_size': instrument.get('pip_or_tick_size', 0.0001),
            'tick_value': instrument.get('tick_value', 10.0),
            'contract_size': instrument.get('contract_size', 100000),
            'price_decimals': instrument.get('price_decimals', 5),
            'notes': instrument.get('notes', '')
        }


catalog = InstrumentCatalog()


def get_instrument(symbol: str) -> Optional[Dict[str, Any]]:
    """Convenience function to get instrument by symbol."""
    return catalog.resolve_symbol(symbol)


def search_instruments(
    query: str,
    limit: int = 20,
    offset: int = 0,
    inst_type: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Convenience function to search instruments."""
    return catalog.search(query, limit=limit, offset=offset, inst_type=inst_type)


def get_instrument_metadata(symbol: str) -> Optional[Dict[str, Any]]:
    """Convenience function to get instrument metadata."""
    return catalog.get_metadata(symbol)


def get_catalog() -> InstrumentCatalog:
    """Return the singleton InstrumentCatalog instance (backwards compat)."""
    return catalog

"""
Universal Instrument Mapper

Maps broker-specific symbols to canonical instrument symbols using:
1. Direct mapping lookup
2. Pattern matching with regex
3. Normalization and alias resolution
4. Fuzzy matching as fallback
"""
import json
import os
import re
from typing import Optional, Dict, Any, Tuple, List
from dataclasses import dataclass
from difflib import SequenceMatcher

from app.services.instrument_catalog import catalog


@dataclass
class MappingResult:
    """Result of a symbol mapping attempt."""
    canonical_symbol: str
    original_symbol: str
    broker_id: str
    confidence: float
    match_type: str
    instrument_metadata: Optional[Dict[str, Any]] = None
    adjustments: Optional[Dict[str, Any]] = None
    warnings: Optional[List[str]] = None


class InstrumentMapper:
    """
    Maps broker-specific symbols to canonical instrument database symbols.
    """
    
    _instance = None
    _brokers: Dict[str, Dict[str, Any]] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_brokers()
        return cls._instance
    
    def _load_brokers(self) -> None:
        """Load broker profiles from JSON."""
        json_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'data', 'brokers.json'
        )
        
        if not os.path.exists(json_path):
            self._brokers = {}
            return
        
        with open(json_path, 'r', encoding='utf-8') as f:
            brokers_list = json.load(f)
        
        self._brokers = {b['id']: b for b in brokers_list}
    
    def reload(self) -> None:
        """Reload broker profiles from disk."""
        self._load_brokers()
    
    def get_broker(self, broker_id: str) -> Optional[Dict[str, Any]]:
        """Get broker profile by ID."""
        return self._brokers.get(broker_id)
    
    def list_brokers(self) -> List[Dict[str, Any]]:
        """List all available broker profiles."""
        return [
            {
                'id': b['id'],
                'name': b['name'],
                'description': b.get('description', ''),
                'api_supported': b.get('api_supported', False),
                'import_formats': b.get('import_formats', [])
            }
            for b in self._brokers.values()
        ]
    
    def map_symbol(
        self,
        broker_symbol: str,
        broker_id: str
    ) -> MappingResult:
        """
        Map a broker-specific symbol to canonical form.
        
        Args:
            broker_symbol: The symbol as used by the broker
            broker_id: The broker's identifier
            
        Returns:
            MappingResult with canonical symbol and confidence
        """
        broker = self._brokers.get(broker_id)
        warnings = []
        
        if not broker:
            return self._fallback_map(broker_symbol, broker_id, warnings)
        
        result = self._try_direct_mapping(broker_symbol, broker, broker_id)
        if result:
            return result
        
        result = self._try_pattern_mapping(broker_symbol, broker, broker_id)
        if result:
            return result
        
        normalized = self._normalize_symbol(broker_symbol)
        instrument = catalog.resolve_symbol(normalized)
        if instrument:
            return MappingResult(
                canonical_symbol=instrument['symbol'],
                original_symbol=broker_symbol,
                broker_id=broker_id,
                confidence=0.85,
                match_type='normalized',
                instrument_metadata=catalog.get_metadata(instrument['symbol']),
                warnings=warnings if warnings else None
            )
        
        return self._fuzzy_map(broker_symbol, broker_id, warnings)
    
    def _try_direct_mapping(
        self,
        broker_symbol: str,
        broker: Dict[str, Any],
        broker_id: str
    ) -> Optional[MappingResult]:
        """Try direct symbol mapping lookup."""
        mappings = broker.get('symbol_mappings', {})
        
        if broker_symbol in mappings:
            canonical = mappings[broker_symbol]
            return MappingResult(
                canonical_symbol=canonical,
                original_symbol=broker_symbol,
                broker_id=broker_id,
                confidence=1.0,
                match_type='direct',
                instrument_metadata=catalog.get_metadata(canonical)
            )
        
        upper = broker_symbol.upper()
        for key, canonical in mappings.items():
            if key.upper() == upper:
                return MappingResult(
                    canonical_symbol=canonical,
                    original_symbol=broker_symbol,
                    broker_id=broker_id,
                    confidence=0.95,
                    match_type='direct_case_insensitive',
                    instrument_metadata=catalog.get_metadata(canonical)
                )
        
        return None
    
    def _try_pattern_mapping(
        self,
        broker_symbol: str,
        broker: Dict[str, Any],
        broker_id: str
    ) -> Optional[MappingResult]:
        """Try pattern-based symbol mapping."""
        patterns = broker.get('symbol_patterns', [])
        
        for pattern_config in patterns:
            pattern = pattern_config.get('pattern', '')
            canonical_template = pattern_config.get('canonical', '')
            
            try:
                match = re.match(pattern, broker_symbol, re.IGNORECASE)
                if match:
                    canonical = canonical_template
                    for i, group in enumerate(match.groups(), 1):
                        if group:
                            canonical = canonical.replace(f'${i}', group.upper())
                    
                    instrument = catalog.resolve_symbol(canonical)
                    if instrument:
                        return MappingResult(
                            canonical_symbol=instrument['symbol'],
                            original_symbol=broker_symbol,
                            broker_id=broker_id,
                            confidence=0.9,
                            match_type='pattern',
                            instrument_metadata=catalog.get_metadata(instrument['symbol'])
                        )
            except re.error:
                continue
        
        return None
    
    def _normalize_symbol(self, symbol: str) -> str:
        """Normalize symbol by removing common broker suffixes/prefixes."""
        normalized = symbol.upper().strip()
        
        normalized = re.sub(r'[_/\-\.\s]', '', normalized)
        
        suffixes = [
            r'\.M$', r'\.PRO$', r'\.ECN$', r'\.RAW$', r'\.STP$',
            r'MICRO$', r'MINI$', r'\.C$', r'\.I$', r'\.S$'
        ]
        for suffix in suffixes:
            normalized = re.sub(suffix, '', normalized, flags=re.IGNORECASE)
        
        return normalized
    
    def _fuzzy_map(
        self,
        broker_symbol: str,
        broker_id: str,
        warnings: List[str]
    ) -> MappingResult:
        """Use fuzzy matching as fallback."""
        normalized = self._normalize_symbol(broker_symbol)
        
        search_results = catalog.search(normalized, limit=5, include_fuzzy=True)
        
        if search_results:
            best = search_results[0]
            score = best.get('_score', 0)
            
            if score >= 0.6:
                warnings.append(f"Fuzzy matched '{broker_symbol}' to '{best['symbol']}' (score: {score:.2f})")
                return MappingResult(
                    canonical_symbol=best['symbol'],
                    original_symbol=broker_symbol,
                    broker_id=broker_id,
                    confidence=score * 0.8,
                    match_type='fuzzy',
                    instrument_metadata=catalog.get_metadata(best['symbol']),
                    warnings=warnings
                )
        
        warnings.append(f"Could not map symbol '{broker_symbol}' - using as-is")
        return MappingResult(
            canonical_symbol=normalized,
            original_symbol=broker_symbol,
            broker_id=broker_id,
            confidence=0.3,
            match_type='unmapped',
            warnings=warnings
        )
    
    def _fallback_map(
        self,
        broker_symbol: str,
        broker_id: str,
        warnings: List[str]
    ) -> MappingResult:
        """Fallback mapping when broker profile is not found."""
        warnings.append(f"Unknown broker '{broker_id}' - using generic mapping")
        
        normalized = self._normalize_symbol(broker_symbol)
        instrument = catalog.resolve_symbol(normalized)
        
        if instrument:
            return MappingResult(
                canonical_symbol=instrument['symbol'],
                original_symbol=broker_symbol,
                broker_id=broker_id,
                confidence=0.7,
                match_type='generic_normalized',
                instrument_metadata=catalog.get_metadata(instrument['symbol']),
                warnings=warnings
            )
        
        return self._fuzzy_map(broker_symbol, broker_id, warnings)
    
    def batch_map(
        self,
        symbols: List[str],
        broker_id: str
    ) -> Dict[str, MappingResult]:
        """
        Map multiple symbols at once.
        
        Args:
            symbols: List of broker symbols
            broker_id: The broker's identifier
            
        Returns:
            Dictionary mapping original symbols to MappingResults
        """
        results = {}
        for symbol in symbols:
            results[symbol] = self.map_symbol(symbol, broker_id)
        return results
    
    def get_mapping_report(
        self,
        symbols: List[str],
        broker_id: str
    ) -> Dict[str, Any]:
        """
        Generate a mapping report for a batch of symbols.
        
        Returns statistics and details about mapped/unmapped symbols.
        """
        results = self.batch_map(symbols, broker_id)
        
        mapped = []
        unmapped = []
        low_confidence = []
        
        for symbol, result in results.items():
            entry = {
                'original': symbol,
                'canonical': result.canonical_symbol,
                'confidence': result.confidence,
                'match_type': result.match_type
            }
            
            if result.match_type == 'unmapped':
                unmapped.append(entry)
            elif result.confidence < 0.7:
                low_confidence.append(entry)
            else:
                mapped.append(entry)
        
        return {
            'broker_id': broker_id,
            'total_symbols': len(symbols),
            'mapped_count': len(mapped),
            'unmapped_count': len(unmapped),
            'low_confidence_count': len(low_confidence),
            'mapping_rate': len(mapped) / len(symbols) if symbols else 0,
            'mapped': mapped,
            'unmapped': unmapped,
            'low_confidence': low_confidence
        }


mapper = InstrumentMapper()


def map_broker_symbol(arg1: str, arg2: str):
    """Flexible wrapper: accepts either (symbol, broker_id) -> returns MappingResult,
    or (broker_id, symbol) -> returns (canonical, confidence, details) tuple.

    Heuristic: if arg1 matches a known broker id in mapper._brokers, treat as (broker_id, symbol)
    and return a tuple for older callers/tests that expect tuple unpacking. Otherwise return
    the MappingResult object as before.
    """
    # Determine if first arg is a broker id
    first_is_broker = arg1 in mapper._brokers

    if first_is_broker:
        broker_id = arg1
        broker_symbol = arg2
        result = mapper.map_symbol(broker_symbol, broker_id)
        details = {
            'original_symbol': result.original_symbol,
            'canonical_symbol': result.canonical_symbol,
            'confidence': result.confidence,
            'match_type': result.match_type,
            'instrument_metadata': result.instrument_metadata,
            'adjustments': result.adjustments,
            'warnings': result.warnings,
        }
        return result.canonical_symbol, result.confidence, details
    else:
        # treat as (broker_symbol, broker_id) and return MappingResult for callers that expect object
        broker_symbol = arg1
        broker_id = arg2
        return mapper.map_symbol(broker_symbol, broker_id)


def get_broker_profile(broker_id: str) -> Optional[Dict[str, Any]]:
    """Convenience function to get broker profile."""
    return mapper.get_broker(broker_id)


def list_available_brokers() -> List[Dict[str, Any]]:
    """Convenience function to list available brokers."""
    return mapper.list_brokers()

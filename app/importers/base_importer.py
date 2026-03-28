"""
Base Importer Module

Provides base classes and data structures for all trade importers.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum


class ImportStatus(Enum):
    """Import operation status."""
    PENDING = 'pending'
    PARSING = 'parsing'
    MAPPING = 'mapping'
    VALIDATING = 'validating'
    IMPORTING = 'importing'
    COMPLETED = 'completed'
    FAILED = 'failed'
    CANCELLED = 'cancelled'


@dataclass
class TradeRecord:
    """
    Normalized trade record from import.
    All importers convert broker-specific formats to this structure.
    """
    broker_ticket: str
    broker_symbol: str
    canonical_symbol: Optional[str] = None
    instrument_type: Optional[str] = None
    
    trade_type: str = ''
    direction: str = ''
    
    lot_size: float = 0.0
    units: Optional[float] = None
    
    entry_price: float = 0.0
    exit_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    
    entry_date: Optional[datetime] = None
    exit_date: Optional[datetime] = None
    
    profit_loss: Optional[float] = None
    commission: float = 0.0
    swap: float = 0.0
    
    status: str = 'closed'
    
    raw_data: Dict[str, Any] = field(default_factory=dict)
    mapping_confidence: float = 0.0
    mapping_warnings: List[str] = field(default_factory=list)
    validation_errors: List[str] = field(default_factory=list)
    
    def is_valid(self) -> bool:
        """Check if record has minimum required fields."""
        return bool(
            self.broker_symbol and
            self.entry_price > 0 and
            self.lot_size > 0 and
            self.entry_date is not None
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'broker_ticket': self.broker_ticket,
            'broker_symbol': self.broker_symbol,
            'canonical_symbol': self.canonical_symbol,
            'instrument_type': self.instrument_type,
            'trade_type': self.trade_type,
            'direction': self.direction,
            'lot_size': self.lot_size,
            'units': self.units,
            'entry_price': self.entry_price,
            'exit_price': self.exit_price,
            'stop_loss': self.stop_loss,
            'take_profit': self.take_profit,
            'entry_date': self.entry_date.isoformat() if self.entry_date else None,
            'exit_date': self.exit_date.isoformat() if self.exit_date else None,
            'profit_loss': self.profit_loss,
            'commission': self.commission,
            'swap': self.swap,
            'status': self.status,
            'mapping_confidence': self.mapping_confidence,
            'mapping_warnings': self.mapping_warnings,
            'validation_errors': self.validation_errors
        }


@dataclass
class ImportResult:
    """Result of an import operation."""
    success: bool
    status: ImportStatus
    message: str
    
    trades: List[TradeRecord] = field(default_factory=list)
    
    total_parsed: int = 0
    total_mapped: int = 0
    total_imported: int = 0
    total_skipped: int = 0
    total_failed: int = 0
    
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    date_range_start: Optional[datetime] = None
    date_range_end: Optional[datetime] = None
    
    broker_id: Optional[str] = None
    source_file: Optional[str] = None
    source_type: str = 'unknown'
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'success': self.success,
            'status': self.status.value,
            'message': self.message,
            'total_parsed': self.total_parsed,
            'total_mapped': self.total_mapped,
            'total_imported': self.total_imported,
            'total_skipped': self.total_skipped,
            'total_failed': self.total_failed,
            'errors': self.errors,
            'warnings': self.warnings,
            'date_range_start': self.date_range_start.isoformat() if self.date_range_start else None,
            'date_range_end': self.date_range_end.isoformat() if self.date_range_end else None,
            'broker_id': self.broker_id,
            'source_file': self.source_file,
            'source_type': self.source_type,
            'trades': [t.to_dict() for t in self.trades]
        }


class BaseImporter(ABC):
    """
    Abstract base class for all trade importers.
    """
    
    def __init__(self, broker_id: str):
        self.broker_id = broker_id
        self.dry_run = False
    
    @abstractmethod
    def parse(self, source: Any) -> ImportResult:
        """
        Parse trades from source (file, API response, etc).
        Returns ImportResult with parsed TradeRecords.
        """
        pass
    
    @abstractmethod
    def validate(self, trades: List[TradeRecord]) -> List[TradeRecord]:
        """
        Validate parsed trades.
        Adds validation_errors to invalid records.
        """
        pass
    
    def preview(self, source: Any) -> ImportResult:
        """
        Parse and validate without importing.
        Useful for showing user what will be imported.
        """
        self.dry_run = True
        result = self.parse(source)
        if result.success:
            result.trades = self.validate(result.trades)
        return result
    
    def _map_symbols(self, trades: List[TradeRecord]) -> List[TradeRecord]:
        """
        Map broker symbols to canonical symbols.
        """
        from app.mappers.instrument_mapper import map_broker_symbol
        
        for trade in trades:
            mapping = map_broker_symbol(trade.broker_symbol, self.broker_id)
            trade.canonical_symbol = mapping.canonical_symbol
            trade.mapping_confidence = mapping.confidence
            trade.mapping_warnings = mapping.warnings or []
            
            if mapping.instrument_metadata:
                trade.instrument_type = mapping.instrument_metadata.get('type')
        
        return trades
    
    def _calculate_pnl(self, trades: List[TradeRecord]) -> List[TradeRecord]:
        """
        Calculate P&L for trades that don't have it.
        """
        from app.services.pnl_engine import calculate_pnl
        from app.services.instrument_catalog import get_instrument_metadata
        
        for trade in trades:
            if trade.profit_loss is None and trade.exit_price is not None:
                meta = get_instrument_metadata(trade.canonical_symbol or trade.broker_symbol)
                result = calculate_pnl(
                    instrument_symbol=trade.canonical_symbol or trade.broker_symbol,
                    entry_price=trade.entry_price,
                    exit_price=trade.exit_price,
                    size=trade.lot_size,
                    size_type='lots',
                    trade_direction=trade.direction,
                    instrument_meta=meta
                )
                trade.profit_loss = result.pnl
        
        return trades
    
    def _get_date_range(self, trades: List[TradeRecord]) -> tuple:
        """Get date range from trades."""
        dates = [t.entry_date for t in trades if t.entry_date]
        if not dates:
            return None, None
        return min(dates), max(dates)

"""
CSV Trade Importer

Robust CSV parser with mapping profiles for common broker export formats.
Supports OANDA, XM, FXCM, IBKR, MT4 CSV exports.
"""
import csv
import io
from datetime import datetime
from typing import Any, List, Dict, Optional, Union
import re

from .base_importer import BaseImporter, ImportResult, ImportStatus, TradeRecord


class CSVImporter(BaseImporter):
    """
    CSV-based trade importer with broker-specific column mappings.
    """
    
    BROKER_FORMATS = {
        'oanda': {
            'delimiter': ',',
            'date_format': '%Y-%m-%dT%H:%M:%S',
            'columns': {
                'ticket': ['id', 'tradeId', 'trade_id'],
                'symbol': ['instrument', 'symbol', 'pair'],
                'type': ['type', 'side'],
                'lots': ['units', 'size', 'quantity', 'amount'],
                'open_price': ['price', 'openPrice', 'open_price', 'avgPrice'],
                'close_price': ['closePrice', 'close_price', 'closingPrice'],
                'open_time': ['openTime', 'open_time', 'openDate', 'createdAt'],
                'close_time': ['closeTime', 'close_time', 'closeDate', 'closedAt'],
                'profit': ['realizedPL', 'profit', 'pnl', 'p/l', 'pl']
            }
        },
        'fxcm': {
            'delimiter': ',',
            'date_format': '%m/%d/%Y %H:%M:%S',
            'columns': {
                'ticket': ['Ticket', 'Order', 'OrderID'],
                'symbol': ['Symbol', 'Instrument'],
                'type': ['Type', 'Side', 'B/S'],
                'lots': ['Lots', 'Size', 'Amount'],
                'open_price': ['OpenPrice', 'Open Price', 'Entry'],
                'close_price': ['ClosePrice', 'Close Price', 'Exit'],
                'open_time': ['OpenTime', 'Open Time', 'Entry Time'],
                'close_time': ['CloseTime', 'Close Time', 'Exit Time'],
                'profit': ['Profit', 'P/L', 'Gross P/L']
            }
        },
        'xm': {
            'delimiter': '\t',
            'date_format': '%Y.%m.%d %H:%M:%S',
            'columns': {
                'ticket': ['Order', 'Ticket'],
                'symbol': ['Symbol'],
                'type': ['Type'],
                'lots': ['Volume', 'Size'],
                'open_price': ['Price'],
                'close_price': ['Price'],
                'open_time': ['Time'],
                'close_time': ['Time'],
                'profit': ['Profit']
            }
        },
        'ibkr': {
            'delimiter': ',',
            'date_format': '%Y%m%d;%H%M%S',
            'columns': {
                'ticket': ['TradeID', 'Order Reference'],
                'symbol': ['Symbol', 'Underlying'],
                'type': ['Buy/Sell', 'Side'],
                'lots': ['Quantity', 'Shares'],
                'open_price': ['T. Price', 'Trade Price'],
                'close_price': ['C. Price', 'Close Price'],
                'open_time': ['Date/Time', 'DateTime'],
                'close_time': ['Close Date/Time'],
                'profit': ['Realized P/L', 'MTM P/L']
            }
        },
        'pepperstone': {
            'delimiter': ',',
            'date_format': '%Y.%m.%d %H:%M:%S',
            'columns': {
                'ticket': ['Order', 'Ticket'],
                'symbol': ['Symbol'],
                'type': ['Type'],
                'lots': ['Volume'],
                'open_price': ['Open Price'],
                'close_price': ['Close Price'],
                'open_time': ['Open Time'],
                'close_time': ['Close Time'],
                'profit': ['Profit']
            }
        },
        'binance': {
            'delimiter': ',',
            'date_format': '%Y-%m-%d %H:%M:%S',
            'columns': {
                'ticket': ['Order ID', 'OrderId'],
                'symbol': ['Pair', 'Symbol'],
                'type': ['Side', 'Type'],
                'lots': ['Filled', 'Quantity', 'Executed Qty'],
                'open_price': ['Price', 'Avg Price'],
                'close_price': ['Price'],
                'open_time': ['Date(UTC)', 'Time', 'Create Time'],
                'close_time': ['Date(UTC)'],
                'profit': ['Realized Profit', 'PNL']
            }
        },
        'generic': {
            'delimiter': ',',
            'date_format': '%Y-%m-%d %H:%M:%S',
            'columns': {
                'ticket': ['ticket', 'order', 'id', 'trade_id', 'tradeid'],
                'symbol': ['symbol', 'instrument', 'pair', 'market'],
                'type': ['type', 'side', 'direction', 'action'],
                'lots': ['lots', 'size', 'volume', 'quantity', 'units', 'amount'],
                'open_price': ['open_price', 'entry_price', 'price', 'open', 'entry'],
                'close_price': ['close_price', 'exit_price', 'close', 'exit'],
                'open_time': ['open_time', 'entry_time', 'open_date', 'date', 'time'],
                'close_time': ['close_time', 'exit_time', 'close_date'],
                'profit': ['profit', 'pnl', 'p/l', 'pl', 'realized_pnl', 'gross_profit']
            }
        }
    }
    
    def __init__(self, broker_id: str = 'generic'):
        super().__init__(broker_id)
        self.format = self.BROKER_FORMATS.get(broker_id, self.BROKER_FORMATS['generic'])
    
    def parse(self, source: Union[str, io.StringIO, bytes]) -> ImportResult:
        """
        Parse CSV data from string, file-like object, or bytes.
        
        Args:
            source: CSV content as string, StringIO, or bytes
            
        Returns:
            ImportResult with parsed trades
        """
        try:
            if isinstance(source, bytes):
                for encoding in ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']:
                    try:
                        source = source.decode(encoding)
                        break
                    except UnicodeDecodeError:
                        continue
            
            if isinstance(source, str):
                source = io.StringIO(source)
            
            delimiter = self.format.get('delimiter', ',')
            
            sample = source.read(8192)
            source.seek(0)
            
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=',;\t|')
                delimiter = dialect.delimiter
            except csv.Error:
                pass
            
            reader = csv.DictReader(source, delimiter=delimiter)
            
            if not reader.fieldnames:
                return ImportResult(
                    success=False,
                    status=ImportStatus.FAILED,
                    message='Could not parse CSV headers',
                    errors=['No valid headers found in CSV']
                )
            
            column_map = self._build_column_map(reader.fieldnames)
            
            trades = []
            row_num = 1
            errors = []
            
            for row in reader:
                row_num += 1
                try:
                    trade = self._parse_row(row, column_map, row_num)
                    if trade:
                        trades.append(trade)
                except Exception as e:
                    errors.append(f'Row {row_num}: {str(e)}')
            
            trades = self._map_symbols(trades)
            
            trades = self._calculate_pnl(trades)
            
            date_start, date_end = self._get_date_range(trades)
            
            return ImportResult(
                success=True,
                status=ImportStatus.COMPLETED if not self.dry_run else ImportStatus.VALIDATING,
                message=f'Parsed {len(trades)} trades from CSV',
                trades=trades,
                total_parsed=len(trades),
                total_mapped=sum(1 for t in trades if t.mapping_confidence >= 0.7),
                errors=errors,
                date_range_start=date_start,
                date_range_end=date_end,
                broker_id=self.broker_id,
                source_type='csv'
            )
            
        except Exception as e:
            return ImportResult(
                success=False,
                status=ImportStatus.FAILED,
                message=f'Failed to parse CSV: {str(e)}',
                errors=[str(e)],
                broker_id=self.broker_id,
                source_type='csv'
            )
    
    def _build_column_map(self, fieldnames: List[str]) -> Dict[str, str]:
        """Map CSV column names to our standard field names."""
        column_map = {}
        columns_config = self.format.get('columns', {})
        
        fieldnames_lower = {f.lower().strip(): f for f in fieldnames}
        
        for field, possible_names in columns_config.items():
            for name in possible_names:
                name_lower = name.lower()
                if name_lower in fieldnames_lower:
                    column_map[field] = fieldnames_lower[name_lower]
                    break
        
        return column_map
    
    def _parse_row(self, row: Dict[str, str], column_map: Dict[str, str], row_num: int) -> Optional[TradeRecord]:
        """Parse a single CSV row into a TradeRecord."""
        def get_value(field: str) -> Optional[str]:
            col = column_map.get(field)
            if col and col in row:
                val = row[col]
                return val.strip() if val else None
            return None
        
        symbol = get_value('symbol')
        if not symbol:
            return None
        
        ticket = get_value('ticket') or f'CSV-{row_num}'
        
        trade_type = get_value('type') or ''
        direction = self._parse_direction(trade_type)
        
        lots = self._parse_float(get_value('lots')) or 0
        if lots < 0:
            lots = abs(lots)
            if direction == 'buy':
                direction = 'sell'
            elif direction == 'sell':
                direction = 'buy'
        
        entry_price = self._parse_float(get_value('open_price')) or 0
        exit_price = self._parse_float(get_value('close_price'))
        
        entry_date = self._parse_datetime(get_value('open_time'))
        exit_date = self._parse_datetime(get_value('close_time'))
        
        profit = self._parse_float(get_value('profit'))
        
        status = 'closed' if exit_price or profit is not None else 'open'
        
        return TradeRecord(
            broker_ticket=ticket,
            broker_symbol=symbol,
            trade_type=trade_type,
            direction=direction,
            lot_size=lots,
            entry_price=entry_price,
            exit_price=exit_price,
            entry_date=entry_date,
            exit_date=exit_date,
            profit_loss=profit,
            status=status,
            raw_data=dict(row)
        )
    
    def _parse_direction(self, trade_type: str) -> str:
        """Parse trade direction from type string."""
        if not trade_type:
            return 'buy'
        
        t = trade_type.lower()
        if any(x in t for x in ['sell', 'short', 's', 'ask']):
            return 'sell'
        return 'buy'
    
    def _parse_float(self, value: Optional[str]) -> Optional[float]:
        """Parse float from string, handling various formats."""
        if not value:
            return None
        
        cleaned = re.sub(r'[^\d.\-+eE]', '', value.replace(',', ''))
        
        try:
            return float(cleaned)
        except (ValueError, TypeError):
            return None
    
    def _parse_datetime(self, value: Optional[str]) -> Optional[datetime]:
        """Parse datetime from string, trying multiple formats."""
        if not value:
            return None
        
        formats = [
            self.format.get('date_format', '%Y-%m-%d %H:%M:%S'),
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%dT%H:%M:%SZ',
            '%Y-%m-%dT%H:%M:%S.%fZ',
            '%Y.%m.%d %H:%M:%S',
            '%Y.%m.%d %H:%M',
            '%d/%m/%Y %H:%M:%S',
            '%m/%d/%Y %H:%M:%S',
            '%d-%m-%Y %H:%M:%S',
            '%Y%m%d;%H%M%S',
            '%Y%m%d %H:%M:%S',
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(value.strip(), fmt)
            except ValueError:
                continue
        
        return None
    
    def validate(self, trades: List[TradeRecord]) -> List[TradeRecord]:
        """Validate parsed trades."""
        for trade in trades:
            errors = []
            
            if not trade.broker_symbol:
                errors.append('Missing symbol')
            
            if trade.entry_price <= 0:
                errors.append('Invalid entry price')
            
            if trade.lot_size <= 0:
                errors.append('Invalid lot size')
            
            if not trade.entry_date:
                errors.append('Missing entry date')
            
            if trade.mapping_confidence < 0.5:
                errors.append(f'Low mapping confidence: {trade.mapping_confidence:.2f}')
            
            trade.validation_errors = errors
        
        return trades

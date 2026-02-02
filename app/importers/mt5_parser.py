"""
MT4/MT5 Statement Parser

Parses MetaTrader 4/5 HTML statement exports.
Handles both detailed and summary statement formats.
"""
import re
from datetime import datetime
from typing import List, Optional, Dict, Any, Union
from html.parser import HTMLParser
import io

from .base_importer import BaseImporter, ImportResult, ImportStatus, TradeRecord


class MT5StatementParser(HTMLParser):
    """HTML parser for MT4/MT5 statement files."""
    
    def __init__(self):
        super().__init__()
        self.in_table = False
        self.in_row = False
        self.in_cell = False
        self.current_row = []
        self.current_cell = ''
        self.tables = []
        self.current_table = []
        self.table_headers = []
        self.is_header = False
    
    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            self.in_table = True
            self.current_table = []
            self.table_headers = []
        elif tag == 'tr':
            self.in_row = True
            self.current_row = []
        elif tag in ('td', 'th'):
            self.in_cell = True
            self.current_cell = ''
            self.is_header = (tag == 'th')
    
    def handle_endtag(self, tag):
        if tag == 'table':
            if self.current_table:
                self.tables.append({
                    'headers': self.table_headers,
                    'rows': self.current_table
                })
            self.in_table = False
        elif tag == 'tr':
            if self.is_header and self.current_row:
                self.table_headers = self.current_row
            elif self.current_row:
                self.current_table.append(self.current_row)
            self.in_row = False
            self.is_header = False
        elif tag in ('td', 'th'):
            self.current_row.append(self.current_cell.strip())
            self.in_cell = False
    
    def handle_data(self, data):
        if self.in_cell:
            self.current_cell += data


class MT5Parser(BaseImporter):
    """
    Parser for MetaTrader 4/5 HTML statement exports.
    
    Supports:
    - Detailed statement (shows individual trades)
    - Account history export
    - Both MT4 and MT5 formats
    """
    
    COLUMN_MAPPINGS = {
        'ticket': ['Ticket', 'Order', 'Position', '#', 'Deal', 'Trade'],
        'symbol': ['Symbol', 'Instrument'],
        'type': ['Type', 'Action'],
        'lots': ['Volume', 'Lots', 'Size'],
        'open_time': ['Open Time', 'Time', 'Open Date'],
        'open_price': ['Open Price', 'Price', 'Entry'],
        'sl': ['S/L', 'SL', 'Stop Loss'],
        'tp': ['T/P', 'TP', 'Take Profit'],
        'close_time': ['Close Time', 'Close Date'],
        'close_price': ['Close Price', 'Exit'],
        'commission': ['Commission', 'Comm'],
        'swap': ['Swap', 'Rollover'],
        'profit': ['Profit', 'P/L', 'Gross']
    }
    
    def __init__(self, broker_id: str = 'mt5_generic'):
        super().__init__(broker_id)
    
    def parse(self, source: Union[str, bytes, io.IOBase]) -> ImportResult:
        """
        Parse MT4/MT5 HTML statement.
        
        Args:
            source: HTML content as string, bytes, or file-like object
            
        Returns:
            ImportResult with parsed trades
        """
        try:
            if isinstance(source, bytes):
                for encoding in ['utf-8', 'utf-8-sig', 'utf-16', 'latin-1', 'cp1252']:
                    try:
                        html_content = source.decode(encoding)
                        break
                    except UnicodeDecodeError:
                        continue
                else:
                    return ImportResult(
                        success=False,
                        status=ImportStatus.FAILED,
                        message='Could not decode HTML file',
                        errors=['Unable to detect file encoding']
                    )
            elif hasattr(source, 'read'):
                html_content = source.read()
                if isinstance(html_content, bytes):
                    html_content = html_content.decode('utf-8')
            else:
                html_content = source
            
            parser = MT5StatementParser()
            parser.feed(html_content)
            
            trades_table = self._find_trades_table(parser.tables)
            
            if not trades_table:
                return ImportResult(
                    success=False,
                    status=ImportStatus.FAILED,
                    message='Could not find trades table in statement',
                    errors=['No valid trades table found. Ensure this is a detailed statement export.']
                )
            
            column_map = self._build_column_map(trades_table['headers'])
            
            trades = []
            errors = []
            
            for row_num, row in enumerate(trades_table['rows'], 1):
                try:
                    trade = self._parse_row(row, trades_table['headers'], column_map, row_num)
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
                message=f'Parsed {len(trades)} trades from MT4/MT5 statement',
                trades=trades,
                total_parsed=len(trades),
                total_mapped=sum(1 for t in trades if t.mapping_confidence >= 0.7),
                errors=errors,
                date_range_start=date_start,
                date_range_end=date_end,
                broker_id=self.broker_id,
                source_type='mt5'
            )
            
        except Exception as e:
            return ImportResult(
                success=False,
                status=ImportStatus.FAILED,
                message=f'Failed to parse MT4/MT5 statement: {str(e)}',
                errors=[str(e)],
                broker_id=self.broker_id,
                source_type='mt5'
            )
    
    def _find_trades_table(self, tables: List[Dict]) -> Optional[Dict]:
        """Find the table containing trade data."""
        for table in tables:
            headers = table.get('headers', [])
            headers_lower = [h.lower() for h in headers]
            
            has_symbol = any('symbol' in h or 'instrument' in h for h in headers_lower)
            has_profit = any('profit' in h or 'p/l' in h for h in headers_lower)
            has_type = any('type' in h or 'action' in h for h in headers_lower)
            
            if has_symbol and (has_profit or has_type):
                return table
        
        for table in tables:
            rows = table.get('rows', [])
            if len(rows) > 2:
                first_row = rows[0] if rows else []
                if len(first_row) >= 5:
                    return table
        
        return None
    
    def _build_column_map(self, headers: List[str]) -> Dict[str, int]:
        """Map column indices to field names."""
        column_map = {}
        headers_lower = [h.lower() for h in headers]
        
        for field, possible_names in self.COLUMN_MAPPINGS.items():
            for name in possible_names:
                name_lower = name.lower()
                for idx, header in enumerate(headers_lower):
                    if name_lower in header:
                        column_map[field] = idx
                        break
                if field in column_map:
                    break
        
        return column_map
    
    def _parse_row(
        self,
        row: List[str],
        headers: List[str],
        column_map: Dict[str, int],
        row_num: int
    ) -> Optional[TradeRecord]:
        """Parse a single table row into a TradeRecord."""
        
        def get_value(field: str) -> Optional[str]:
            idx = column_map.get(field)
            if idx is not None and idx < len(row):
                val = row[idx]
                return val.strip() if val else None
            return None
        
        symbol = get_value('symbol')
        if not symbol:
            return None
        
        trade_type = get_value('type') or ''
        if trade_type.lower() in ['balance', 'deposit', 'withdrawal', 'credit', 'rebate']:
            return None
        
        ticket = get_value('ticket') or f'MT-{row_num}'
        direction = self._parse_direction(trade_type)
        
        lots_str = get_value('lots')
        lots = self._parse_float(lots_str) or 0
        
        entry_price = self._parse_float(get_value('open_price')) or 0
        exit_price = self._parse_float(get_value('close_price'))
        
        sl = self._parse_float(get_value('sl'))
        tp = self._parse_float(get_value('tp'))
        
        entry_date = self._parse_datetime(get_value('open_time'))
        exit_date = self._parse_datetime(get_value('close_time'))
        
        commission = self._parse_float(get_value('commission')) or 0
        swap = self._parse_float(get_value('swap')) or 0
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
            stop_loss=sl if sl and sl > 0 else None,
            take_profit=tp if tp and tp > 0 else None,
            entry_date=entry_date,
            exit_date=exit_date,
            commission=commission,
            swap=swap,
            profit_loss=profit,
            status=status,
            raw_data={'row': row, 'headers': headers}
        )
    
    def _parse_direction(self, trade_type: str) -> str:
        """Parse trade direction from type string."""
        if not trade_type:
            return 'buy'
        
        t = trade_type.lower()
        if 'sell' in t or 'short' in t:
            return 'sell'
        return 'buy'
    
    def _parse_float(self, value: Optional[str]) -> Optional[float]:
        """Parse float from string."""
        if not value:
            return None
        
        cleaned = re.sub(r'[^\d.\-+]', '', value.replace(',', '').replace(' ', ''))
        
        try:
            return float(cleaned)
        except (ValueError, TypeError):
            return None
    
    def _parse_datetime(self, value: Optional[str]) -> Optional[datetime]:
        """Parse datetime from MT4/MT5 format."""
        if not value:
            return None
        
        formats = [
            '%Y.%m.%d %H:%M:%S',
            '%Y.%m.%d %H:%M',
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d %H:%M',
            '%d.%m.%Y %H:%M:%S',
            '%d.%m.%Y %H:%M',
            '%Y/%m/%d %H:%M:%S',
            '%Y/%m/%d %H:%M',
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

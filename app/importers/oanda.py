"""
OANDA API Trade Importer

Uses OANDA's REST v20 API to fetch trade history.
Requires user consent and API key storage.

API Documentation: https://developer.oanda.com/rest-live-v20/introduction/
"""
import os
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import json

from .base_importer import BaseImporter, ImportResult, ImportStatus, TradeRecord


class OANDAImporter(BaseImporter):
    """
    OANDA REST API v20 trade importer.
    
    Requires:
    - API Key (access token)
    - Account ID
    - Environment (practice/live)
    """
    
    PRACTICE_URL = 'https://api-fxpractice.oanda.com'
    LIVE_URL = 'https://api-fxtrade.oanda.com'
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        account_id: Optional[str] = None,
        is_practice: bool = True
    ):
        super().__init__('oanda')
        self.api_key = api_key
        self.account_id = account_id
        self.base_url = self.PRACTICE_URL if is_practice else self.LIVE_URL
        self._session = None
    
    @property
    def is_configured(self) -> bool:
        """Check if API credentials are configured."""
        return bool(self.api_key and self.account_id)
    
    def _get_session(self):
        """Get or create HTTP session with auth headers."""
        if self._session is None:
            try:
                import requests
                self._session = requests.Session()
                self._session.headers.update({
                    'Authorization': f'Bearer {self.api_key}',
                    'Content-Type': 'application/json',
                    'Accept-Datetime-Format': 'RFC3339'
                })
            except ImportError:
                raise ImportError('requests library required for OANDA API')
        return self._session
    
    def test_connection(self) -> Dict[str, Any]:
        """
        Test API connection and return account info.
        
        Returns:
            Account information dict or error details
        """
        if not self.is_configured:
            return {
                'success': False,
                'error': 'API key and account ID required'
            }
        
        try:
            session = self._get_session()
            response = session.get(
                f'{self.base_url}/v3/accounts/{self.account_id}'
            )
            
            if response.status_code == 200:
                data = response.json()
                account = data.get('account', {})
                return {
                    'success': True,
                    'account_id': account.get('id'),
                    'currency': account.get('currency'),
                    'balance': account.get('balance'),
                    'margin_available': account.get('marginAvailable'),
                    'open_trade_count': account.get('openTradeCount'),
                    'pl': account.get('pl')
                }
            else:
                return {
                    'success': False,
                    'error': f'API error: {response.status_code}',
                    'details': response.text
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def parse(
        self,
        source: Optional[Dict[str, Any]] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        count: int = 500
    ) -> ImportResult:
        """
        Fetch trades from OANDA API.
        
        Args:
            source: Optional params dict (can override from_date, to_date, count)
            from_date: Start date for trade history
            to_date: End date for trade history (default: now)
            count: Maximum number of trades to fetch
            
        Returns:
            ImportResult with parsed trades
        """
        if not self.is_configured:
            return ImportResult(
                success=False,
                status=ImportStatus.FAILED,
                message='OANDA API not configured',
                errors=['API key and account ID are required. Configure in broker settings.'],
                broker_id=self.broker_id,
                source_type='api'
            )
        
        if source:
            from_date = source.get('from_date', from_date)
            to_date = source.get('to_date', to_date)
            count = source.get('count', count)
        
        if to_date is None:
            to_date = datetime.utcnow()
        if from_date is None:
            from_date = to_date - timedelta(days=90)
        
        try:
            trades_data = self._fetch_trades(from_date, to_date, count)
            
            trades = []
            errors = []
            
            for trade_data in trades_data:
                try:
                    trade = self._parse_trade(trade_data)
                    if trade:
                        trades.append(trade)
                except Exception as e:
                    errors.append(f"Trade {trade_data.get('id', '?')}: {str(e)}")
            
            trades = self._map_symbols(trades)
            trades = self._calculate_pnl(trades)
            
            date_start, date_end = self._get_date_range(trades)
            
            return ImportResult(
                success=True,
                status=ImportStatus.COMPLETED if not self.dry_run else ImportStatus.VALIDATING,
                message=f'Fetched {len(trades)} trades from OANDA',
                trades=trades,
                total_parsed=len(trades),
                total_mapped=sum(1 for t in trades if t.mapping_confidence >= 0.7),
                errors=errors,
                date_range_start=date_start,
                date_range_end=date_end,
                broker_id=self.broker_id,
                source_type='api'
            )
            
        except Exception as e:
            return ImportResult(
                success=False,
                status=ImportStatus.FAILED,
                message=f'Failed to fetch trades from OANDA: {str(e)}',
                errors=[str(e)],
                broker_id=self.broker_id,
                source_type='api'
            )
    
    def _fetch_trades(
        self,
        from_date: datetime,
        to_date: datetime,
        count: int
    ) -> List[Dict[str, Any]]:
        """Fetch closed trades from OANDA API."""
        session = self._get_session()
        
        all_trades = []
        
        params = {
            'state': 'CLOSED',
            'count': min(count, 500),
        }
        
        url = f'{self.base_url}/v3/accounts/{self.account_id}/trades'
        response = session.get(url, params=params)
        
        if response.status_code != 200:
            raise Exception(f'OANDA API error: {response.status_code} - {response.text}')
        
        data = response.json()
        trades = data.get('trades', [])
        all_trades.extend(trades)
        
        return all_trades
    
    def _parse_trade(self, trade_data: Dict[str, Any]) -> Optional[TradeRecord]:
        """Parse OANDA trade data into TradeRecord."""
        instrument = trade_data.get('instrument', '')
        if not instrument:
            return None
        
        trade_id = trade_data.get('id', '')
        
        units = float(trade_data.get('initialUnits', 0))
        direction = 'buy' if units > 0 else 'sell'
        lots = abs(units) / 100000
        
        entry_price = float(trade_data.get('price', 0))
        exit_price = float(trade_data.get('averageClosePrice', 0))
        
        open_time_str = trade_data.get('openTime', '')
        close_time_str = trade_data.get('closeTime', '')
        
        entry_date = self._parse_datetime(open_time_str)
        exit_date = self._parse_datetime(close_time_str)
        
        realized_pl = float(trade_data.get('realizedPL', 0))
        financing = float(trade_data.get('financing', 0))
        commission = float(trade_data.get('commission', 0))
        
        sl_order = trade_data.get('stopLossOrder', {})
        tp_order = trade_data.get('takeProfitOrder', {})
        sl = float(sl_order.get('price', 0)) if sl_order else None
        tp = float(tp_order.get('price', 0)) if tp_order else None
        
        state = trade_data.get('state', 'CLOSED')
        status = 'open' if state == 'OPEN' else 'closed'
        
        return TradeRecord(
            broker_ticket=trade_id,
            broker_symbol=instrument,
            trade_type=direction,
            direction=direction,
            lot_size=lots,
            units=abs(units),
            entry_price=entry_price,
            exit_price=exit_price if exit_price > 0 else None,
            stop_loss=sl if sl and sl > 0 else None,
            take_profit=tp if tp and tp > 0 else None,
            entry_date=entry_date,
            exit_date=exit_date,
            profit_loss=realized_pl,
            commission=commission,
            swap=financing,
            status=status,
            raw_data=trade_data
        )
    
    def _parse_datetime(self, value: Optional[str]) -> Optional[datetime]:
        """Parse OANDA RFC3339 datetime."""
        if not value:
            return None
        
        try:
            value = value.split('.')[0] + 'Z'
            return datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ')
        except:
            try:
                return datetime.fromisoformat(value.replace('Z', '+00:00'))
            except:
                return None
    
    def validate(self, trades: List[TradeRecord]) -> List[TradeRecord]:
        """Validate trades."""
        for trade in trades:
            errors = []
            
            if not trade.broker_symbol:
                errors.append('Missing instrument')
            
            if trade.entry_price <= 0:
                errors.append('Invalid entry price')
            
            if trade.lot_size <= 0 and (trade.units is None or trade.units <= 0):
                errors.append('Invalid position size')
            
            trade.validation_errors = errors
        
        return trades


def create_oanda_importer(
    api_key: str,
    account_id: str,
    is_practice: bool = True
) -> OANDAImporter:
    """
    Factory function to create OANDA importer.
    
    IMPORTANT: Store API keys securely using encryption.
    Never log or expose API keys.
    """
    return OANDAImporter(
        api_key=api_key,
        account_id=account_id,
        is_practice=is_practice
    )

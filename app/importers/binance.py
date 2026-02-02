"""
Binance API Trade Importer

Uses Binance's REST API to fetch trade history.
Supports spot and futures trading.

API Documentation: https://binance-docs.github.io/apidocs/spot/en/
"""
import hmac
import hashlib
import time
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from urllib.parse import urlencode

from .base_importer import BaseImporter, ImportResult, ImportStatus, TradeRecord


class BinanceImporter(BaseImporter):
    """
    Binance REST API trade importer.
    
    Requires:
    - API Key
    - API Secret
    
    Supports:
    - Spot trading history
    - Futures/USDM trading history
    """
    
    SPOT_URL = 'https://api.binance.com'
    FUTURES_URL = 'https://fapi.binance.com'
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        use_futures: bool = False
    ):
        super().__init__('binance')
        self.api_key = api_key
        self.api_secret = api_secret
        self.use_futures = use_futures
        self.base_url = self.FUTURES_URL if use_futures else self.SPOT_URL
        self._session = None
    
    @property
    def is_configured(self) -> bool:
        """Check if API credentials are configured."""
        return bool(self.api_key and self.api_secret)
    
    def _get_session(self):
        """Get or create HTTP session."""
        if self._session is None:
            try:
                import requests
                self._session = requests.Session()
                self._session.headers.update({
                    'X-MBX-APIKEY': self.api_key
                })
            except ImportError:
                raise ImportError('requests library required for Binance API')
        return self._session
    
    def _sign_request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Sign request with HMAC SHA256."""
        params['timestamp'] = int(time.time() * 1000)
        query_string = urlencode(params)
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        params['signature'] = signature
        return params
    
    def test_connection(self) -> Dict[str, Any]:
        """
        Test API connection and return account info.
        """
        if not self.is_configured:
            return {
                'success': False,
                'error': 'API key and secret required'
            }
        
        try:
            session = self._get_session()
            
            if self.use_futures:
                endpoint = '/fapi/v2/account'
            else:
                endpoint = '/api/v3/account'
            
            params = self._sign_request({})
            response = session.get(f'{self.base_url}{endpoint}', params=params)
            
            if response.status_code == 200:
                data = response.json()
                
                if self.use_futures:
                    return {
                        'success': True,
                        'total_wallet_balance': data.get('totalWalletBalance'),
                        'available_balance': data.get('availableBalance'),
                        'total_unrealized_profit': data.get('totalUnrealizedProfit'),
                        'asset_count': len(data.get('assets', []))
                    }
                else:
                    balances = data.get('balances', [])
                    non_zero = [b for b in balances if float(b.get('free', 0)) > 0 or float(b.get('locked', 0)) > 0]
                    return {
                        'success': True,
                        'can_trade': data.get('canTrade'),
                        'account_type': data.get('accountType'),
                        'balances': len(non_zero)
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
        symbol: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        limit: int = 500
    ) -> ImportResult:
        """
        Fetch trades from Binance API.
        
        Args:
            source: Optional params dict
            symbol: Trading pair (e.g., 'BTCUSDT'). If None, fetches for popular pairs
            from_date: Start date
            to_date: End date
            limit: Max trades per symbol
            
        Returns:
            ImportResult with parsed trades
        """
        if not self.is_configured:
            return ImportResult(
                success=False,
                status=ImportStatus.FAILED,
                message='Binance API not configured',
                errors=['API key and secret are required. Configure in broker settings.'],
                broker_id=self.broker_id,
                source_type='api'
            )
        
        if source:
            symbol = source.get('symbol', symbol)
            from_date = source.get('from_date', from_date)
            to_date = source.get('to_date', to_date)
            limit = source.get('limit', limit)
        
        try:
            if symbol:
                symbols = [symbol]
            else:
                symbols = self._get_traded_symbols()
            
            all_trades = []
            errors = []
            
            for sym in symbols:
                try:
                    trades_data = self._fetch_trades(sym, from_date, to_date, limit)
                    for trade_data in trades_data:
                        trade = self._parse_trade(trade_data, sym)
                        if trade:
                            all_trades.append(trade)
                except Exception as e:
                    errors.append(f'{sym}: {str(e)}')
            
            all_trades = self._map_symbols(all_trades)
            all_trades = self._calculate_pnl(all_trades)
            
            date_start, date_end = self._get_date_range(all_trades)
            
            return ImportResult(
                success=True,
                status=ImportStatus.COMPLETED if not self.dry_run else ImportStatus.VALIDATING,
                message=f'Fetched {len(all_trades)} trades from Binance',
                trades=all_trades,
                total_parsed=len(all_trades),
                total_mapped=sum(1 for t in all_trades if t.mapping_confidence >= 0.7),
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
                message=f'Failed to fetch trades from Binance: {str(e)}',
                errors=[str(e)],
                broker_id=self.broker_id,
                source_type='api'
            )
    
    def _get_traded_symbols(self) -> List[str]:
        """Get list of symbols with trade history."""
        return [
            'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT',
            'ADAUSDT', 'DOGEUSDT', 'MATICUSDT', 'DOTUSDT', 'AVAXUSDT'
        ]
    
    def _fetch_trades(
        self,
        symbol: str,
        from_date: Optional[datetime],
        to_date: Optional[datetime],
        limit: int
    ) -> List[Dict[str, Any]]:
        """Fetch trades for a symbol."""
        session = self._get_session()
        
        if self.use_futures:
            endpoint = '/fapi/v1/userTrades'
        else:
            endpoint = '/api/v3/myTrades'
        
        params = {
            'symbol': symbol,
            'limit': min(limit, 1000)
        }
        
        if from_date:
            params['startTime'] = int(from_date.timestamp() * 1000)
        if to_date:
            params['endTime'] = int(to_date.timestamp() * 1000)
        
        params = self._sign_request(params)
        response = session.get(f'{self.base_url}{endpoint}', params=params)
        
        if response.status_code != 200:
            raise Exception(f'Binance API error: {response.status_code} - {response.text}')
        
        return response.json()
    
    def _parse_trade(self, trade_data: Dict[str, Any], symbol: str) -> Optional[TradeRecord]:
        """Parse Binance trade data into TradeRecord."""
        trade_id = str(trade_data.get('id', ''))
        if not trade_id:
            return None
        
        qty = float(trade_data.get('qty', 0))
        price = float(trade_data.get('price', 0))
        
        is_buyer = trade_data.get('isBuyer', True)
        direction = 'buy' if is_buyer else 'sell'
        
        time_ms = trade_data.get('time', 0)
        trade_time = datetime.fromtimestamp(time_ms / 1000) if time_ms else None
        
        commission = float(trade_data.get('commission', 0))
        commission_asset = trade_data.get('commissionAsset', '')
        
        realized_pnl = float(trade_data.get('realizedPnl', 0)) if 'realizedPnl' in trade_data else None
        
        return TradeRecord(
            broker_ticket=trade_id,
            broker_symbol=symbol,
            trade_type=direction,
            direction=direction,
            lot_size=qty,
            units=qty,
            entry_price=price,
            exit_price=price,
            entry_date=trade_time,
            exit_date=trade_time,
            profit_loss=realized_pnl,
            commission=commission,
            status='closed',
            raw_data=trade_data
        )
    
    def validate(self, trades: List[TradeRecord]) -> List[TradeRecord]:
        """Validate trades."""
        for trade in trades:
            errors = []
            
            if not trade.broker_symbol:
                errors.append('Missing symbol')
            
            if trade.entry_price <= 0:
                errors.append('Invalid price')
            
            if trade.lot_size <= 0:
                errors.append('Invalid quantity')
            
            trade.validation_errors = errors
        
        return trades


def create_binance_importer(
    api_key: str,
    api_secret: str,
    use_futures: bool = False
) -> BinanceImporter:
    """
    Factory function to create Binance importer.
    
    IMPORTANT: Store API keys securely using encryption.
    Never log or expose API keys.
    """
    return BinanceImporter(
        api_key=api_key,
        api_secret=api_secret,
        use_futures=use_futures
    )

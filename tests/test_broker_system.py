#!/usr/bin/env python3
"""
Unit tests for the Broker Profile System.

Tests:
- Instrument search and catalog
- Symbol mapping
- P&L calculations for different asset classes
- CSV/MT5 importers (dry run)
"""
import pytest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestInstrumentCatalog:
    """Test instrument catalog functionality."""
    
    def test_catalog_loads(self):
        """Test that instrument catalog loads successfully."""
        from app.services.instrument_catalog import catalog
        assert catalog.count > 0
        assert catalog.count >= 2500
    
    def test_get_by_symbol_exact(self):
        """Test exact symbol lookup."""
        from app.services.instrument_catalog import get_instrument
        
        eurusd = get_instrument('EURUSD')
        assert eurusd is not None
        assert eurusd['symbol'] == 'EURUSD'
        assert eurusd['type'] == 'forex'
    
    def test_get_by_alias(self):
        """Test alias lookup."""
        from app.services.instrument_catalog import catalog
        
        gold = catalog.resolve_symbol('GOLD')
        assert gold is not None
        assert gold['symbol'] == 'XAUUSD'
    
    def test_search_forex(self):
        """Test searching for forex pairs."""
        from app.services.instrument_catalog import search_instruments
        
        results = search_instruments('EURUSD', limit=10)
        assert len(results) > 0
        assert results[0]['symbol'] == 'EURUSD'
    
    def test_search_indices(self):
        """Test searching for indices."""
        from app.services.instrument_catalog import search_instruments
        
        results = search_instruments('US500', limit=5)
        assert len(results) > 0
        assert results[0]['symbol'] == 'US500'
    
    def test_search_nasdaq(self):
        """Test searching with alias."""
        from app.services.instrument_catalog import search_instruments
        
        results = search_instruments('NAS100', limit=5)
        assert len(results) > 0
    
    def test_search_crypto(self):
        """Test searching for crypto."""
        from app.services.instrument_catalog import search_instruments
        
        results = search_instruments('BTC', limit=5)
        assert len(results) > 0
        assert any('BTC' in r['symbol'] for r in results)
    
    def test_get_metadata(self):
        """Test getting instrument metadata."""
        from app.services.instrument_catalog import get_instrument_metadata
        
        meta = get_instrument_metadata('EURUSD')
        assert meta is not None
        assert 'pip_or_tick_size' in meta
        assert 'contract_size' in meta
        assert meta['type'] == 'forex'


class TestInstrumentMapper:
    """Test instrument mapping functionality."""
    
    def test_oanda_mapping(self):
        """Test OANDA symbol mapping."""
        from app.mappers.instrument_mapper import map_broker_symbol
        
        result = map_broker_symbol('EUR_USD', 'oanda')
        assert result.canonical_symbol == 'EURUSD'
        assert result.confidence >= 0.9
    
    def test_oanda_gold_mapping(self):
        """Test OANDA gold mapping."""
        from app.mappers.instrument_mapper import map_broker_symbol
        
        result = map_broker_symbol('XAU_USD', 'oanda')
        assert result.canonical_symbol == 'XAUUSD'
    
    def test_binance_mapping(self):
        """Test Binance symbol mapping."""
        from app.mappers.instrument_mapper import map_broker_symbol
        
        result = map_broker_symbol('BTCUSDT', 'binance')
        assert result.canonical_symbol == 'BTCUSDT'
        assert result.confidence >= 0.8
    
    def test_mt4_suffix_stripping(self):
        """Test that MT4 suffixes are stripped."""
        from app.mappers.instrument_mapper import map_broker_symbol
        
        result = map_broker_symbol('EURUSD.ecn', 'mt4_generic')
        assert result.canonical_symbol == 'EURUSD'
    
    def test_xm_micro_mapping(self):
        """Test XM micro account symbol mapping."""
        from app.mappers.instrument_mapper import map_broker_symbol
        
        result = map_broker_symbol('EURUSDm', 'xm')
        assert result.canonical_symbol == 'EURUSD'
    
    def test_generic_fallback(self):
        """Test generic mapping fallback."""
        from app.mappers.instrument_mapper import map_broker_symbol
        
        result = map_broker_symbol('EURUSD', 'unknown_broker')
        assert result.canonical_symbol == 'EURUSD'
    
    def test_batch_mapping(self):
        """Test batch symbol mapping."""
        from app.mappers.instrument_mapper import mapper
        
        symbols = ['EUR_USD', 'GBP_USD', 'XAU_USD']
        results = mapper.batch_map(symbols, 'oanda')
        
        assert len(results) == 3
        assert all(r.confidence > 0 for r in results.values())
    
    def test_mapping_report(self):
        """Test mapping report generation."""
        from app.mappers.instrument_mapper import mapper
        
        symbols = ['EURUSD', 'UNKNOWN123', 'GBPUSD']
        report = mapper.get_mapping_report(symbols, 'generic')
        
        assert report['total_symbols'] == 3
        assert report['mapped_count'] >= 2
    
    def test_broker_list(self):
        """Test listing available brokers."""
        from app.mappers.instrument_mapper import list_available_brokers
        
        brokers = list_available_brokers()
        assert len(brokers) >= 10
        assert any(b['id'] == 'oanda' for b in brokers)
        assert any(b['id'] == 'binance' for b in brokers)


class TestPnLEngine:
    """Test P&L calculation engine."""
    
    def test_forex_pnl_buy(self):
        """Test forex P&L calculation for buy trade."""
        from app.services.pnl_engine import calculate_pnl
        
        result = calculate_pnl(
            instrument_symbol='EURUSD',
            entry_price=1.1000,
            exit_price=1.1050,
            size=1.0,
            size_type='lots',
            trade_direction='buy'
        )
        
        assert result.pnl > 0
        assert result.pip_move == 50
    
    def test_forex_pnl_sell(self):
        """Test forex P&L calculation for sell trade."""
        from app.services.pnl_engine import calculate_pnl
        
        result = calculate_pnl(
            instrument_symbol='EURUSD',
            entry_price=1.1050,
            exit_price=1.1000,
            size=1.0,
            size_type='lots',
            trade_direction='sell'
        )
        
        assert result.pnl > 0
        assert result.pip_move == 50
    
    def test_forex_pnl_loss(self):
        """Test forex P&L for losing trade."""
        from app.services.pnl_engine import calculate_pnl
        
        result = calculate_pnl(
            instrument_symbol='EURUSD',
            entry_price=1.1050,
            exit_price=1.1000,
            size=1.0,
            size_type='lots',
            trade_direction='buy'
        )
        
        assert result.pnl < 0
    
    def test_index_pnl(self):
        """Test index P&L calculation."""
        from app.services.pnl_engine import calculate_pnl
        
        result = calculate_pnl(
            instrument_symbol='US500',
            entry_price=4500.00,
            exit_price=4550.00,
            size=1.0,
            size_type='contracts',
            trade_direction='buy'
        )
        
        assert result.pnl > 0
        assert result.points == 50.0
    
    def test_commodity_pnl(self):
        """Test commodity (gold) P&L calculation."""
        from app.services.pnl_engine import calculate_pnl
        
        result = calculate_pnl(
            instrument_symbol='XAUUSD',
            entry_price=1900.00,
            exit_price=1910.00,
            size=1.0,
            size_type='lots',
            trade_direction='buy'
        )
        
        assert result.pnl > 0
    
    def test_crypto_pnl(self):
        """Test crypto P&L calculation."""
        from app.services.pnl_engine import calculate_pnl
        
        result = calculate_pnl(
            instrument_symbol='BTCUSDT',
            entry_price=40000.00,
            exit_price=41000.00,
            size=0.5,
            size_type='units',
            trade_direction='buy'
        )
        
        assert result.pnl == 500.0
    
    def test_stock_pnl(self):
        """Test stock P&L calculation."""
        from app.services.pnl_engine import calculate_pnl
        
        result = calculate_pnl(
            instrument_symbol='AAPL',
            entry_price=150.00,
            exit_price=155.00,
            size=100,
            size_type='units',
            trade_direction='buy'
        )
        
        assert result.pnl == 500.0
        assert result.details['pct_return'] == pytest.approx(3.33, rel=0.1)
    
    def test_pip_value_calculation(self):
        """Test pip value calculation."""
        from app.services.pnl_engine import calculate_pip_value
        
        pip_value = calculate_pip_value('EURUSD', lot_size=1.0)
        assert pip_value > 0
    
    def test_position_size_calculation(self):
        """Test position size calculation."""
        from app.services.pnl_engine import calculate_position_size
        
        lot_size = calculate_position_size(
            instrument_symbol='EURUSD',
            risk_amount=100,
            stop_loss_pips=20
        )
        
        assert lot_size > 0
        assert lot_size <= 10


class TestCSVImporter:
    """Test CSV importer functionality."""
    
    def test_parse_basic_csv(self):
        """Test parsing basic CSV data."""
        from app.importers.csv_importer import CSVImporter
        
        csv_data = """ticket,symbol,type,lots,open_price,close_price,open_time,close_time,profit
1,EURUSD,buy,0.1,1.1000,1.1050,2024-01-01 10:00:00,2024-01-01 12:00:00,50.00
2,GBPUSD,sell,0.2,1.2500,1.2450,2024-01-02 09:00:00,2024-01-02 11:00:00,100.00
"""
        
        importer = CSVImporter('generic')
        result = importer.preview(csv_data)
        
        assert result.success
        assert result.total_parsed == 2
        assert len(result.trades) == 2
    
    def test_csv_direction_parsing(self):
        """Test CSV direction parsing."""
        from app.importers.csv_importer import CSVImporter
        
        csv_data = """ticket,symbol,type,lots,open_price
1,EURUSD,buy,0.1,1.1000
2,GBPUSD,sell,0.2,1.2500
3,USDJPY,short,0.1,110.00
4,AUDUSD,long,0.1,0.7500
"""
        
        importer = CSVImporter('generic')
        result = importer.preview(csv_data)
        
        assert result.success
        assert result.trades[0].direction == 'buy'
        assert result.trades[1].direction == 'sell'
        assert result.trades[2].direction == 'sell'
        assert result.trades[3].direction == 'buy'
    
    def test_oanda_format(self):
        """Test OANDA CSV format parsing."""
        from app.importers.csv_importer import CSVImporter
        
        csv_data = """id,instrument,type,units,price,openTime,closeTime,realizedPL
123,EUR_USD,buy,10000,1.1000,2024-01-01T10:00:00,2024-01-01T12:00:00,50.00
"""
        
        importer = CSVImporter('oanda')
        result = importer.preview(csv_data)
        
        assert result.success
        assert result.total_parsed == 1
        assert result.trades[0].canonical_symbol == 'EURUSD'


class TestMT5Parser:
    """Test MT5 statement parser."""
    
    def test_parse_simple_html(self):
        """Test parsing simple MT5 HTML statement."""
        from app.importers.mt5_parser import MT5Parser
        
        html_data = """
        <html>
        <body>
        <table>
            <tr><th>Ticket</th><th>Symbol</th><th>Type</th><th>Volume</th><th>Price</th><th>Profit</th></tr>
            <tr><td>12345</td><td>EURUSD</td><td>buy</td><td>0.10</td><td>1.1000</td><td>50.00</td></tr>
            <tr><td>12346</td><td>GBPUSD</td><td>sell</td><td>0.20</td><td>1.2500</td><td>100.00</td></tr>
        </table>
        </body>
        </html>
        """
        
        parser = MT5Parser('mt4_generic')
        result = parser.preview(html_data)
        
        assert result.success
        assert result.total_parsed == 2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

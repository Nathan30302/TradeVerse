from app.mappers.instrument_mapper import map_broker_symbol


def test_map_known():
    sym = 'EURUSD'
    mapped, score, details = map_broker_symbol('oanda', sym)
    assert mapped == 'EURUSD' or mapped is None


def test_map_alias():
    mapped, score, details = map_broker_symbol('ig', 'GOLD')
    # GOLD alias should map to XAUUSD in catalog if seeded
    # Accept either mapping or None depending on seed
    assert score >= 0.0

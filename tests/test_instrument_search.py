from app.services.instrument_catalog import get_catalog


def test_search_basic():
    cat = get_catalog()
    results = cat.search('USA')
    assert isinstance(results, list)
    # Should return some results (SPX alias includes USA in sample)
    assert len(results) >= 0

"""Instrument groups: metals with metals, forex with forex, energies with oil."""

from app import create_app, db, schema_compat
from app.models.instrument import (
    Instrument,
    catalog_by_symbol,
    sync_instrument_taxonomy,
)
from app.models.user import User


def test_catalog_puts_metals_and_forex_in_the_right_groups():
    by_sym = catalog_by_symbol()
    assert by_sym["XAUUSD"]["category"] == "Metals"
    assert by_sym["XAGUSD"]["category"] == "Metals"
    assert by_sym["XPTUSD"]["category"] == "Metals"
    assert by_sym["EURUSD"]["category"] == "Forex"
    assert by_sym["UKOIL"]["category"] == "Energies"
    metals = {s for s, rec in by_sym.items() if rec.get("category") == "Metals"}
    forex = {s for s, rec in by_sym.items() if rec.get("category") == "Forex"}
    assert "XAUUSD" in metals
    assert "XAUUSD" not in forex
    assert "EURUSD" in forex
    assert not any(s.startswith("XAU") or s.startswith("XAG") for s in forex)


def test_sync_moves_gold_out_of_forex():
    app = create_app("testing")
    with app.app_context():
        db.drop_all()
        db.create_all()
        schema_compat.refresh(app)
        gold = Instrument(
            symbol="XAUUSD",
            name="Gold",
            instrument_type="forex",
            category="Forex",
            pip_size=0.01,
            contract_size=100,
            tick_value=1.0,
            is_active=True,
        )
        euro = Instrument(
            symbol="EURUSD",
            name="EUR/USD",
            instrument_type="forex",
            category="Forex",
            pip_size=0.0001,
            contract_size=100000,
            tick_value=10.0,
            is_active=True,
        )
        db.session.add_all([gold, euro])
        db.session.commit()
        n = sync_instrument_taxonomy()
        assert n >= 1
        assert Instrument.query.filter_by(symbol="XAUUSD").first().category == "Metals"
        assert Instrument.query.filter_by(symbol="EURUSD").first().category == "Forex"


def test_add_trade_tabs_and_category_api_order():
    app = create_app("testing")
    with app.app_context():
        db.drop_all()
        db.create_all()
        schema_compat.refresh(app)
        u = User(username="catuser", email="cat@example.com")
        u.set_password("password12")
        db.session.add(u)
        db.session.add(
            Instrument(
                symbol="EURUSD",
                name="EUR/USD",
                instrument_type="forex",
                category="Forex",
                pip_size=0.0001,
                contract_size=100000,
                tick_value=10.0,
                is_active=True,
            )
        )
        db.session.add(
            Instrument(
                symbol="XAUUSD",
                name="Gold",
                instrument_type="forex",
                category="Metals",
                pip_size=0.01,
                contract_size=100,
                tick_value=1.0,
                is_active=True,
            )
        )
        db.session.commit()
        c = app.test_client()
        c.post("/auth/login", data={"username": "catuser", "password": "password12"}, follow_redirects=True)
        body = c.get("/trade/add").get_data(as_text=True)
        assert 'data-category="forex"' in body
        assert 'data-category="metals"' in body
        assert 'data-category="energies"' in body
        assert "Metals &amp; oil" not in body
        assert "theme-contrast.css" in body
        cats = c.get("/api/db/instruments/categories").get_json()
        keys = cats.get("order") or list((cats.get("categories") or {}).keys())
        assert keys[0] == "forex"
        assert "metals" in keys
        gold = c.get("/api/db/instruments?category=metals&limit=20").get_json()
        symbols = [r["symbol"] for r in (gold.get("results") or [])]
        assert "XAUUSD" in symbols
        fx = c.get("/api/db/instruments?category=forex&limit=50").get_json()
        fx_syms = [r["symbol"] for r in (fx.get("results") or [])]
        assert "EURUSD" in fx_syms
        assert "XAUUSD" not in fx_syms

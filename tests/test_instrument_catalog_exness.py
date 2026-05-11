"""Catalog integrity: exness_full_catalog.json symbols ⊆ DB, no duplicate symbols."""

import json
from pathlib import Path

import pytest

from app import create_app, db, schema_compat
from app.models.instrument import Instrument


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_catalog_symbols():
    path = _repo_root() / "data" / "exness_full_catalog.json"
    data = json.loads(path.read_text())
    return [str(x["symbol"]).strip().upper() for x in data.get("instruments", []) if x.get("symbol")]


def _seed_from_catalog():
    path = _repo_root() / "data" / "exness_full_catalog.json"
    data = json.loads(path.read_text())
    for rec in data.get("instruments", []):
        sym = (rec.get("symbol") or "").strip()
        if not sym:
            continue
        inst = Instrument.query.filter(Instrument.symbol == sym).first()
        if inst:
            continue
        inst = Instrument(symbol=sym)
        inst.name = rec.get("name") or sym
        inst.instrument_type = rec.get("instrument_type") or "forex"
        inst.category = rec.get("category") or "Forex"
        inst.pip_size = float(rec.get("pip_size") or 0.0001)
        inst.contract_size = float(rec.get("contract_size") or 100000)
        tv = rec.get("tick_value")
        if tv is not None:
            inst.tick_value = float(tv)
        elif (rec.get("instrument_type") or "").lower() == "index":
            su = sym.upper()
            if "US30" in su and "_X" not in su:
                inst.tick_value = 5.0
            elif any(x in su for x in ("US100", "USTEC", "NAS")):
                inst.tick_value = 20.0
            else:
                inst.tick_value = 1.0
        else:
            inst.tick_value = 1.0 if tv is None else float(tv)
        inst.price_decimals = int(rec.get("price_decimals") or 5)
        inst.is_active = True
        db.session.add(inst)
    db.session.commit()


@pytest.fixture
def app():
    app = create_app("testing")
    with app.app_context():
        db.drop_all()
        db.create_all()
        schema_compat.refresh(app)
        _seed_from_catalog()
        yield app


def test_catalog_symbols_all_present_no_duplicates(app):
    catalog_syms = _load_catalog_symbols()
    assert len(catalog_syms) > 200

    with app.app_context():
        rows = db.session.query(Instrument.symbol).filter(Instrument.is_active == True).all()
        db_syms_upper = {r[0].strip().upper() for r in rows}
        syms_upper_list = [r[0].strip().upper() for r in rows]

    missing = [s for s in catalog_syms if s not in db_syms_upper]
    assert not missing, f"missing {len(missing)} symbols, first few: {missing[:12]}"

    assert len(syms_upper_list) == len(set(syms_upper_list)), "duplicate case-insensitive symbols"

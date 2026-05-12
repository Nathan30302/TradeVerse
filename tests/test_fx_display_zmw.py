"""Display FX includes ZMW (fallback merge when missing from feed)."""

from app.services.fx_display import DISPLAY_LABELS, get_usd_rates_map


def test_rates_map_includes_zmw():
    m = get_usd_rates_map()
    assert "USD" in m
    assert "ZMW" in m
    assert m["ZMW"] > 0


def test_display_label_zmw():
    assert "ZMW" in DISPLAY_LABELS

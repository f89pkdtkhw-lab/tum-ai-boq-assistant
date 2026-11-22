"""#225: estimate ranges by source (price list, history, unchanged) and the null case. Offline, synthetic."""
from decimal import Decimal
from types import SimpleNamespace as NS

from app.pruefung.spannen import (
    FALLBACK_REL, HISTORIE_OHNE_STREUUNG_REL, HISTORIE_MIN_REL, PREISLISTE_REL, UNVERAENDERT_REL,
    preis_spanne, quelle_von_treffer, rel_fuer, summe_gp_spannen,
)
from app.pruefung.geschaetztes_lv import geschaetztes_lv
from app.pruefung.preise import kalkuliere
from test_pruefung_geschaetztes_lv import ANPASSUNGEN, LV_SYN, PREISLISTE, _zeilen


def _r(n):
    return round(n, 2)


def test_price_list_range_is_narrow():
    ev, eb, gv, gb = preis_spanne(ep=100, menge=10, quelle="preisliste")
    assert (ev, eb, gv, gb) == (95.0, 105.0, 950.0, 1050.0)
    assert rel_fuer("preisliste") == PREISLISTE_REL


def test_history_range_uses_spread_of_deviations():
    # Midpoint 220 (already applied), spread 8 % → 202.40–237.60
    ev, eb, gv, gb = preis_spanne(ep=22, menge=10, quelle="historie", streuung_prozent=8)
    assert (ev, eb, gv, gb) == (20.24, 23.76, 202.4, 237.6)
    assert rel_fuer("historie", 8) == Decimal("0.08")
    # Fewer than two observations: default 10 %, never narrower than 5 %
    assert rel_fuer("historie", None) == HISTORIE_OHNE_STREUUNG_REL
    assert rel_fuer("historie", 1) == HISTORIE_MIN_REL


def test_unchanged_range_is_wide():
    ev, eb, gv, gb = preis_spanne(ep=5, menge=10, quelle="unveraendert")
    assert (ev, eb, gv, gb) == (4.25, 5.75, 42.5, 57.5)
    assert rel_fuer("unveraendert") == UNVERAENDERT_REL


def test_no_price_has_no_range():
    assert preis_spanne(ep=None, menge=3, quelle="ohne_preis") == (None, None, None, None)
    assert preis_spanne(ep=None, menge=None, quelle="preisliste") == (None, None, None, None)
    assert rel_fuer("ohne_preis") is None


def test_fallback_uses_explicit_range_else_wide():
    ev, eb, gv, gb = preis_spanne(ep=20, menge=2, quelle="index", ep_von=16, ep_bis=24)
    assert (ev, eb, gv, gb) == (16.0, 24.0, 32.0, 48.0)
    ev, eb, gv, gb = preis_spanne(ep=20, menge=2, quelle="recherche")
    assert (ev, eb) == (16.0, 24.0)  # ±20 %
    assert rel_fuer("index") == FALLBACK_REL


def test_total_range_is_the_sum_of_item_ranges():
    # Example LV: list 1200 ±5 %, history 220 ±8 %, unchanged 50 ±15 %, unpriced skipped.
    zeilen = [
        NS(in_summe=True, gp_neu=1200, gp_von=1140, gp_bis=1260),
        NS(in_summe=True, gp_neu=220, gp_von=202.4, gp_bis=237.6),
        NS(in_summe=True, gp_neu=50, gp_von=42.5, gp_bis=57.5),
        NS(in_summe=True, gp_neu=None, gp_von=None, gp_bis=None),
    ]
    von, bis = summe_gp_spannen(zeilen)
    assert (von, bis) == (1384.9, 1555.1)
    assert _r(von) == _r(1140 + 202.4 + 42.5)
    assert _r(bis) == _r(1260 + 237.6 + 57.5)


def test_estimated_bill_ranges_on_the_synthetic_lv():
    kalkulation = kalkuliere(LV_SYN, PREISLISTE)
    g = geschaetztes_lv(LV_SYN, ANPASSUNGEN, PREISLISTE, kalkulation)
    z = _zeilen(g)
    # List match, narrow ±5 % of the (possibly updated) total
    assert (z["01.01"].gp_neu, z["01.01"].gp_von, z["01.01"].gp_bis) == (200.0, 190.0, 210.0)
    assert (z["01.02"].gp_neu, z["01.02"].gp_von, z["01.02"].gp_bis) == (600.0, 570.0, 630.0)
    assert (z["01.03"].gp_neu, z["01.03"].gp_von, z["01.03"].gp_bis) == (0.0, 0.0, 0.0)
    assert (z["NEU-1"].gp_neu, z["NEU-1"].gp_von, z["NEU-1"].gp_bis) == (54.0, 51.36, 56.76)
    # No price data: no range
    assert z["NEU-2"].ep is None and z["NEU-2"].gp_von is None and z["NEU-2"].gp_bis is None
    assert (g.summe_netto_von, g.summe_netto_bis) == (811.36, 896.76)
    assert _r(g.summe_netto_von) == _r(190 + 570 + 0 + 51.36)
    assert _r(g.summe_netto_bis) == _r(210 + 630 + 0 + 56.76)


def test_quelle_von_treffer():
    assert quelle_von_treffer("oz", 10) == "preisliste"
    assert quelle_von_treffer("index", 10) == "index"
    assert quelle_von_treffer("recherche", 10) == "recherche"
    assert quelle_von_treffer("text", None) == "ohne_preis"
    assert quelle_von_treffer("kein_treffer", 10) == "unveraendert"

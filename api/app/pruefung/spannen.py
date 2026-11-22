"""Price-estimate ranges (low–high) per item and in total (issue #225).

The point estimate stays the existing field; the range is optional and never invents a
price. Width depends on the source:

* ``preisliste`` — list or price-database match: narrow (±5 %).
* ``historie`` — past projects of the same trade: half-width is the sample standard
  deviation of the historical percentage deviations, floored at 5 %; with fewer than
  two observations a 10 % default is used.
* ``index`` / ``recherche`` — price fallback (#218): the explicit unit-price range
  when the fallback provided one, otherwise a wide ±20 %.
* ``unveraendert`` — the bill price is kept, with no independent source: wide (±15 %).
* ``ohne_preis`` — no price data: no estimate and no range.

The total range is the sum of the item ranges (items in the net sum). A priced item
without a range contributes its point estimate to both ends, so the total stays
consistent. Unpriced items contribute nothing.
"""
from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from typing import Literal

from .preise import _cent, _dez

Quelle = Literal["preisliste", "historie", "index", "recherche", "unveraendert", "ohne_preis"]

# Relative half-width of the estimate, by source.
PREISLISTE_REL = Decimal("0.05")
UNVERAENDERT_REL = Decimal("0.15")
FALLBACK_REL = Decimal("0.20")
HISTORIE_MIN_REL = Decimal("0.05")
HISTORIE_OHNE_STREUUNG_REL = Decimal("0.10")

LISTE_TREFFER = frozenset({"oz", "text", "aehnlich"})
FALLBACK_TREFFER = frozenset({"index", "recherche"})


def rel_fuer(quelle: str, streuung_prozent: float | None = None) -> Decimal | None:
    """Half-width as a fraction of the estimate; None when no range applies."""
    if quelle == "preisliste":
        return PREISLISTE_REL
    if quelle == "unveraendert":
        return UNVERAENDERT_REL
    if quelle in FALLBACK_TREFFER:
        return FALLBACK_REL
    if quelle == "historie":
        if streuung_prozent is None:
            return HISTORIE_OHNE_STREUUNG_REL
        return max(abs(_dez(streuung_prozent)) / Decimal(100), HISTORIE_MIN_REL)
    return None


def quelle_von_treffer(treffer: str | None, ep: float | None) -> Quelle:
    """Map a B6 match type to a range source."""
    if ep is None:
        return "ohne_preis"
    if treffer in LISTE_TREFFER:
        return "preisliste"
    if treffer in FALLBACK_TREFFER:
        return treffer  # type: ignore[return-value]
    return "unveraendert"


def preis_spanne(*, ep: float | None, menge: float | None, quelle: str,
                 ep_von: float | None = None, ep_bis: float | None = None,
                 streuung_prozent: float | None = None
                 ) -> tuple[float | None, float | None, float | None, float | None]:
    """``(ep_von, ep_bis, gp_von, gp_bis)``. All None when there is no price or no range."""
    if quelle == "ohne_preis" or (ep is None and ep_von is None):
        return None, None, None, None
    if ep_von is not None and ep_bis is not None:
        ev = float(_cent(_dez(min(ep_von, ep_bis))))
        eb = float(_cent(_dez(max(ep_von, ep_bis))))
    else:
        rel = rel_fuer(quelle, streuung_prozent)
        if rel is None or ep is None:
            return None, None, None, None
        ev = max(0.0, float(_cent(_dez(ep) * (1 - rel))))
        eb = float(_cent(_dez(ep) * (1 + rel)))
    gv = float(_cent(_dez(menge) * _dez(ev))) if menge is not None else None
    gb = float(_cent(_dez(menge) * _dez(eb))) if menge is not None else None
    return ev, eb, gv, gb


def summe_gp_spannen(zeilen: Iterable) -> tuple[float | None, float | None]:
    """Sum of in-sum item ranges. Priced items without a range use the point estimate."""
    von = bis = Decimal("0")
    irgendwelche = False
    for z in zeilen:
        if not getattr(z, "in_summe", True):
            continue
        gp = getattr(z, "gp_neu", None)
        if gp is None:
            gp = getattr(z, "gp", None)
        if gp is None:
            continue
        irgendwelche = True
        low = getattr(z, "gp_von", None)
        high = getattr(z, "gp_bis", None)
        if low is not None and high is not None:
            von += _dez(low)
            bis += _dez(high)
        else:
            von += _dez(gp)
            bis += _dez(gp)
    if not irgendwelche:
        return None, None
    return float(_cent(von)), float(_cent(bis))

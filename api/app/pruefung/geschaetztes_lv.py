"""New estimated bill: the original bill with all adjustments applied, priced again (B8, epic #93).

Deterministic, offline, additive. Input: the original bill, the B7 adjustments (`anpassungen.py`)
and the B6 pricing (`preise.py`). Nothing is mutated; the original `lv` and `kalkulation` stay as
they are.

* One row per original position, in bill order, plus one row per added item. No original item
  is ever dropped: a removed item stays with status ``removed``, ``menge_neu`` 0 and ``gp_neu`` 0.
* Original rows keep the unit price the B6 matcher found for them (``kalkulation``); added items
  are priced the same way (B9 ``kalkuliere_mit_preis_db``: uploaded list first, price database for
  the gaps). No price is invented: an item
  without a match keeps ``ep`` null and the sum is marked incomplete (``vollstaendig`` false).
* ``differenz_netto`` is the new net sum minus ``kalkulation.summe_netto``; both sums skip the
  same unpriced items, so the difference covers what is priced on both sides.
* Without a price list, quantities and statuses are still computed; prices and sums are null.

Adjustments are applied only to a unique OZ that exists in the bill (B7 never adjusts an
ambiguous OZ); a removal wins over a quantity change, and the first quantity change per item wins.
"""
import logging
from collections import Counter
from collections.abc import Iterable, Sequence
from decimal import ROUND_HALF_UP, Decimal

from ..ai import step_api
from ..modelle import (LV, Anpassung, GeschaetztePosition, GeschaetztesLv, Kalkulation, Position,
                       Preisliste, Pruefbericht, StatusAnzahl)
from .anpassungen import anpassungen_ableiten
from .preise import NICHT_IN_SUMME, _cent, _dez, kalkuliere_mit_preis_db
from .spannen import preis_spanne, quelle_von_treffer, summe_gp_spannen

log = logging.getLogger(__name__)

MENGE_TOLERANZ = 1e-6
# Adjustments from these reports always need an estimator's approval (issue #114).
FREIGABE_BERICHTE = frozenset({"vergleich", "was_wenn"})


def _gleich(a: float, b: float) -> bool:
    return abs(a - b) <= MENGE_TOLERANZ * max(1.0, abs(a), abs(b))


def _freigabe(anpassungen: Iterable[Anpassung]) -> bool:
    return any(a.freigabe_noetig or a.bericht in FREIGABE_BERICHTE for a in anpassungen)


def _grund(anpassungen: Sequence[Anpassung]) -> str:
    return " ".join(a.grund.strip() for a in anpassungen if a.grund.strip())


def _gp(menge: float | None, ep: float | None) -> Decimal | None:
    return None if menge is None or ep is None else _cent(_dez(menge) * _dez(ep))


def _float(wert: Decimal | None) -> float | None:
    return None if wert is None else float(wert)


def _mit_spanne(k, ep: float | None, menge_neu: float | None, status: str) -> dict:
    """Optional low/high fields for one estimated-bill row (#225)."""
    quelle = quelle_von_treffer(getattr(k, "treffer", None), ep)
    ev, eb, gv, gb = preis_spanne(
        ep=ep, menge=menge_neu, quelle=quelle,
        ep_von=getattr(k, "ep_von", None) if k is not None else None,
        ep_bis=getattr(k, "ep_bis", None) if k is not None else None)
    if ev is None:
        return {}
    if status == "removed":
        gv, gb = 0.0, 0.0
    return {"ep_von": ev, "ep_bis": eb, "gp_von": gv, "gp_bis": gb}


def _passende_kalkulation(lv: LV, preisliste: Preisliste | None, kalkulation: Kalkulation | None
                          ) -> Kalkulation | None:
    """The B6/B9 pricing of exactly this bill: the given one when it lines up, else priced again
    (uploaded list first, price database for the gaps; None without any price source)."""
    if kalkulation is not None and len(kalkulation.positionen) == len(lv.positionen) and all(
            k.oz == p.oz for k, p in zip(kalkulation.positionen, lv.positionen)):
        return kalkulation
    return kalkuliere_mit_preis_db(lv, preisliste)


def _hinzugefuegte_position(a: Anpassung) -> Position:
    if a.position is not None:
        return a.position.model_copy(update={"oz": a.oz, "menge": a.menge_neu})
    return Position(oz=a.oz, menge=a.menge_neu)


def geschaetztes_lv(lv: LV, anpassungen: Sequence[Anpassung], preisliste: Preisliste | None = None,
                    kalkulation: Kalkulation | None = None) -> GeschaetztesLv:
    """Apply `anpassungen` to `lv` and price the result with the B6 matcher.

    `kalkulation`: the B6/B9 pricing of the original bill (default: priced from `preisliste` and the
    price database). No price source at all → quantities and statuses only, prices and sums null.
    """
    alt = _passende_kalkulation(lv, preisliste, kalkulation)
    anzahl_oz = Counter(p.oz for p in lv.positionen)
    eindeutig = {p.oz for p in lv.positionen if anzahl_oz[p.oz] == 1}

    entfernen: dict[str, Anpassung] = {}
    menge: dict[str, Anpassung] = {}
    hinzufuegen: list[Anpassung] = []
    for a in anpassungen:
        if a.art == "hinzufuegen":
            hinzufuegen.append(a)
        elif a.oz in eindeutig and a.art == "entfernen":
            entfernen.setdefault(a.oz, a)
        elif a.oz in eindeutig and a.art == "menge" and a.menge_neu is not None:
            menge.setdefault(a.oz, a)

    zeilen: list[GeschaetztePosition] = []
    for i, pos in enumerate(lv.positionen):
        k = alt.positionen[i] if alt is not None else None
        ep = k.ep if k is not None else None
        gp_alt = _dez(k.gp) if k is not None and k.gp is not None else None
        in_summe = k.in_summe if k is not None else pos.typ not in NICHT_IN_SUMME
        status, menge_neu, angewandt = "unchanged", pos.menge, []
        if pos.oz in entfernen:
            status, menge_neu, angewandt = "removed", 0.0, [entfernen[pos.oz]]
        elif pos.oz in menge and (pos.menge is None or not _gleich(pos.menge, menge[pos.oz].menge_neu)):
            status, menge_neu, angewandt = "updated", menge[pos.oz].menge_neu, [menge[pos.oz]]
        if status == "removed":
            gp_neu = Decimal("0")
        elif status == "unchanged":
            gp_neu = gp_alt
        else:
            gp_neu = _gp(menge_neu, ep)
        zeilen.append(GeschaetztePosition(
            oz=pos.oz, status=status, kurztext=pos.kurztext, einheit=pos.einheit, menge_alt=pos.menge,
            menge_neu=menge_neu, ep=ep, gp_alt=_float(gp_alt), gp_neu=_float(gp_neu),
            anpassung_ids=[a.id for a in angewandt], grund=_grund(angewandt),
            freigabe_noetig=_freigabe(angewandt), in_summe=in_summe, **_mit_spanne(k, ep, menge_neu, status)))

    neu = [_hinzugefuegte_position(a) for a in hinzufuegen]
    preise_neu = (kalkuliere_mit_preis_db(LV(name=lv.name, quelle=lv.quelle, positionen=neu), preisliste,
                                          alt.mwst_satz) if alt is not None and neu else None)
    neu_preise = preise_neu.positionen if preise_neu is not None else [None] * len(neu)
    for a, pos, k in zip(hinzufuegen, neu, neu_preise):
        ep = k.ep if k is not None else None
        zeilen.append(GeschaetztePosition(
            oz=pos.oz, status="added", kurztext=pos.kurztext, einheit=pos.einheit, menge_alt=None,
            menge_neu=pos.menge, ep=ep, gp_alt=None, gp_neu=_float(_gp(pos.menge, ep)),
            anpassung_ids=[a.id], grund=_grund([a]), freigabe_noetig=_freigabe([a]),
            in_summe=k.in_summe if k is not None else pos.typ not in NICHT_IN_SUMME,
            **_mit_spanne(k, ep, pos.menge, "added")))

    anzahl = StatusAnzahl(**Counter(z.status for z in zeilen))
    ohne_preis = sum(z.ep is None and z.status != "removed" for z in zeilen)
    if alt is None:  # no price list: quantities and statuses only
        return GeschaetztesLv(positionen=zeilen, summe_netto=None, summe_brutto=None, differenz_netto=None,
                              differenz_prozent=None, ohne_preis=ohne_preis, vollstaendig=False, anzahl=anzahl)

    summiert = [z for z in zeilen if z.in_summe]
    netto = _cent(sum((_dez(z.gp_neu) for z in summiert if z.gp_neu is not None), Decimal("0")))
    basis = _dez(alt.summe_netto)
    differenz = _cent(netto - basis)
    prozent = None if basis == 0 else float((differenz / basis * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    von, bis = summe_gp_spannen(summiert)
    return GeschaetztesLv(
        preisliste_id=alt.preisliste_id, waehrung=alt.waehrung, mwst_satz=alt.mwst_satz, positionen=zeilen,
        summe_netto=float(netto), summe_brutto=float(_cent(netto * (1 + _dez(alt.mwst_satz)))),
        differenz_netto=float(differenz), differenz_prozent=prozent, ohne_preis=ohne_preis,
        vollstaendig=all(z.gp_neu is not None for z in summiert), anzahl=anzahl,
        summe_netto_von=von, summe_netto_bis=bis)


def _notes(bericht: Pruefbericht) -> list[step_api.Note]:
    """Report 2/3 step notes (B5 stores them serialised) as `Note` objects for B7."""
    notes = []
    for b in bericht.berichte or ():
        if b.id not in FREIGABE_BERICHTE:
            continue
        for roh in b.notes:
            try:
                notes.append(step_api.Note.model_validate(roh))
            except ValueError:
                continue
    return notes


def ergaenze_geschaetztes_lv(bericht: Pruefbericht, preisliste: Preisliste | None) -> Pruefbericht:
    """Additive: adds `anpassungen` (B7, when not yet set) and `geschaetztes_lv`, and feeds
    `differenz_netto` into `zusammenfassung.schaetzung_abweichung_eur` (B1). On any failure the
    report is returned unchanged."""
    try:
        anpassungen = bericht.anpassungen
        if anpassungen is None:
            anpassungen = anpassungen_ableiten(bericht.lv, bericht.findings, _notes(bericht), bericht.was_wenn or ())
        geschaetzt = geschaetztes_lv(bericht.lv, anpassungen, preisliste, bericht.kalkulation)
        teile = {"anpassungen": anpassungen, "geschaetztes_lv": geschaetzt}
        if bericht.zusammenfassung is not None and geschaetzt.differenz_netto is not None:
            z_update = {"schaetzung_abweichung_eur": geschaetzt.differenz_netto}
            if geschaetzt.summe_netto_von is not None and geschaetzt.summe_netto_bis is not None:
                z_update["schaetzung_von"] = geschaetzt.summe_netto_von
                z_update["schaetzung_bis"] = geschaetzt.summe_netto_bis
            teile["zusammenfassung"] = bericht.zusammenfassung.model_copy(update=z_update)
        return bericht.model_copy(update=teile)
    except Exception:
        log.exception("B8 estimated bill failed; review report returned without it")
        return bericht

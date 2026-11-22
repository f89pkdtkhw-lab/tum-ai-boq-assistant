"""Fallback prices for bill items without a price-list or price-DB match (t237).

Order per item: uploaded list → price database (``preise.kalkuliere``) → **index price** → **web research**.

1. Index price (deterministic, offline): only for raw-material-heavy work (bitumen, insulation, concrete,
   reinforcing steel, masonry, timber, steel, copper/zinc, roof tiles). The short text is mapped by keyword
   to a reference unit-price range (base year 2021, net, *rough guide values kept by LV Scout, not official
   figures*) and scaled with the matching Destatis construction price index for that trade (GENESIS
   61261-0001, residential buildings, annual average, 2021 = 100). Index name, value and factor are shown
   as the source. See ``docs/preis-fallback.md``.
2. Web research: items still without a price are researched with the deep-research helper
   (``recherche.recherchiere_fehlende_preise``); the midpoint of the sourced market range becomes the EP.
   Runs only when deep research is active (Claude with web search); the mock stays deterministic.

Every fallback price is marked ``geschaetzt`` with ``treffer`` ``index``/``recherche``, range and sources;
the calculation is flagged ``enthaelt_schaetzungen``. Nothing here may break the analysis: a failure
becomes a warning and the item stays without a price.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal

from ..modelle import LV, Kalkulation, KalkulationsPosition, PreisQuelle
from .preise import _cent, _dez, kanonische_einheit

log = logging.getLogger(__name__)

GENESIS_URL = "https://www-genesis.destatis.de/datenbank/online/table/61261-0001"
INDEX_JAHR = 2025  # latest full annual average published in 61261-0001 (checked Nov 2026)
BASISJAHR = 2021

# Destatis, GENESIS 61261-0001 "Baupreisindizes", Wohngebäude, annual average 2025, 2021 = 100.
BAUPREISINDEX = {
    "Abdichtungsarbeiten": 132.8,
    "Wärmedämm-Verbundsysteme": 136.5,
    "Betonarbeiten": 124.1,
    "Mauerarbeiten": 122.6,
    "Zimmer- und Holzbauarbeiten": 122.4,
    "Stahlbauarbeiten": 123.8,
    "Klempnerarbeiten": 138.9,
    "Dachdeckungsarbeiten": 140.9,
}


@dataclass(frozen=True)
class Referenz:
    """Rough net unit-price range in the base year (guide value, own assumption, not an official figure)."""
    id: str
    material: str
    stichworte: tuple[str, ...]  # normalised substrings (ae/oe/ue/ss), longer = more specific
    spannen: dict[str, tuple[float, float]]  # canonical unit -> (from, to) EUR net, base year
    index: str  # key of BAUPREISINDEX


REFERENZEN: tuple[Referenz, ...] = (
    Referenz("bitumen-anstrich", "Bitumen (Anstrich/Dickbeschichtung)",
             ("bitum", "schwarzanstrich", "schutzanstrich", "dickbeschicht", "kmb"),
             {"m²": (8.0, 18.0)}, "Abdichtungsarbeiten"),
    Referenz("bitumen-bahn", "Bitumenbahnen (Dachabdichtung)",
             ("bitumenbahn", "bitumenschweissbahn", "schweissbahn", "dachabdichtung"),
             {"m²": (25.0, 50.0)}, "Abdichtungsarbeiten"),
    Referenz("wdvs", "Dämmstoff mit Putzsystem (WDVS)",
             ("waermedaemmverbund", "wdvs", "verbundsystem"),
             {"m²": (90.0, 150.0)}, "Wärmedämm-Verbundsysteme"),
    Referenz("daemmung", "Dämmstoffplatten (liefern und einbauen, ohne Putzsystem)",
             ("daemm", "mineralwolle", "steinwolle", "glaswolle", "perimeter", "xps", "polystyrol"),
             {"m²": (20.0, 45.0)}, "Wärmedämm-Verbundsysteme"),
    Referenz("bewehrung", "Betonstahl / Bewehrung",
             ("bewehrung", "betonstahl", "betonstahlmatte", "stabstahl", "baustahl"),
             {"t": (1400.0, 2200.0), "kg": (1.4, 2.2)}, "Betonarbeiten"),
    Referenz("beton", "Beton / Zement (Ortbeton)",
             ("ortbeton", "stahlbeton", "beton", "zement"),
             {"m³": (160.0, 260.0)}, "Betonarbeiten"),
    Referenz("mauerwerk", "Mauersteine (Ziegel, Kalksandstein, Porenbeton)",
             ("mauerwerk", "kalksandstein", "porenbeton", "hochlochziegel", "ziegel"),
             {"m²": (60.0, 110.0), "m³": (250.0, 400.0)}, "Mauerarbeiten"),
    Referenz("holz", "Bauholz (KVH, BSH)",
             ("konstruktionsvollholz", "brettschichtholz", "bauholz", "kantholz", "holzbalken", "sparren"),
             {"m³": (600.0, 1100.0)}, "Zimmer- und Holzbauarbeiten"),
    Referenz("stahl", "Baustahl (Stahlkonstruktion)",
             ("stahlkonstruktion", "stahltraeger", "stahlbau", "stahlstuetze"),
             {"kg": (3.0, 6.0), "t": (3000.0, 6000.0)}, "Stahlbauarbeiten"),
    Referenz("kupfer-zink", "Kupfer / Titanzink (Klempner)",
             ("kupfer", "titanzink", "dachrinne", "regenrinne", "fallrohr"),
             {"m": (35.0, 80.0)}, "Klempnerarbeiten"),
    Referenz("dachziegel", "Dachziegel / Dachsteine",
             ("dachziegel", "dachstein", "biberschwanz"),
             {"m²": (45.0, 85.0)}, "Dachdeckungsarbeiten"),
)

_ERSETZE = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def _norm(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "").casefold().translate(_ERSETZE)


def finde_referenz(kurztext: str, einheit: str | None) -> Referenz | None:
    """Best raw-material reference for a short text with a known unit; None without a clear match.
    Score = total length of matched keywords (more specific wins); the first entry wins on ties."""
    kanon = kanonische_einheit(einheit)
    if kanon is None:
        return None
    text = _norm(kurztext)
    beste, punkte = None, 0
    for ref in REFERENZEN:
        if not any(kanonische_einheit(e) == kanon for e in ref.spannen):
            continue
        wert = sum(len(s) for s in ref.stichworte if s in text)
        if wert > punkte:
            beste, punkte = ref, wert
    return beste


def _spanne(ref: Referenz, einheit: str | None) -> tuple[float, float]:
    kanon = kanonische_einheit(einheit)
    return next(v for e, v in ref.spannen.items() if kanonische_einheit(e) == kanon)


def index_preis(kurztext: str, einheit: str | None) -> dict | None:
    """{"ep", "ep_von", "ep_bis", "quellen", "hinweis"} for raw-material items, else None."""
    ref = finde_referenz(kurztext, einheit)
    if ref is None:
        return None
    von, bis = _spanne(ref, einheit)
    wert = BAUPREISINDEX[ref.index]
    faktor = _dez(wert) / Decimal(100)
    ep_von, ep_bis = _cent(_dez(von) * faktor), _cent(_dez(bis) * faktor)
    ep = _cent((ep_von + ep_bis) / 2)
    faktor_text = f"{float(faktor):.3f}"
    return {
        "ep": float(ep), "ep_von": float(ep_von), "ep_bis": float(ep_bis),
        "quellen": [
            PreisQuelle(titel=f"Destatis Baupreisindex Wohngebäude – {ref.index}: {wert:g} "
                              f"({INDEX_JAHR}, {BASISJAHR} = 100), GENESIS 61261-0001", url=GENESIS_URL),
            PreisQuelle(titel=f"Referenz-EP {ref.material}: {von:g}–{bis:g} EUR/{einheit} netto "
                              f"(Basis {BASISJAHR}, Richtwert LV Scout, kein amtlicher Wert)"),
        ],
        "hinweis": (f"Index estimate: reference range {von:g}–{bis:g} EUR × price index factor {faktor_text} "
                    f"({ref.index}, {BASISJAHR}→{INDEX_JAHR}); net, without regional or project surcharges. "
                    f"Guide value, check against a supplier quote."),
    }


def _mit_schaetzung(k: KalkulationsPosition, treffer: str, ep: float, ep_von: float | None,
                    ep_bis: float | None, quellen: list[PreisQuelle], hinweis: str) -> KalkulationsPosition:
    ep_d = _dez(ep)
    gp = _cent(_dez(k.menge) * ep_d) if k.menge is not None else None
    return k.model_copy(update={
        "ep": float(ep_d), "gp": float(gp) if gp is not None else None, "treffer": treffer,
        "ep_differenz": float(_cent(ep_d - _dez(k.ep_lv))) if k.ep_lv is not None else None,
        "gp_differenz": float(_cent(gp - _dez(k.gp_lv))) if gp is not None and k.gp_lv is not None else None,
        "preis_eintrag": None, "preisliste_id": None, "aehnlichkeit": None, "geschaetzt": True,
        "ep_von": ep_von, "ep_bis": ep_bis, "preis_quellen": quellen, "schaetzung_hinweis": hinweis,
    })


def neu_summieren(kalkulation: Kalkulation, positionen: list[KalkulationsPosition]) -> Kalkulation:
    """Sums and counters as in ``preise.kalkuliere``, plus the estimate flags."""
    netto = Decimal("0")
    ohne_preis = ohne_menge = 0
    vollstaendig = True
    for k in positionen:
        if k.ep is None:
            ohne_preis += 1
        elif k.gp is None:
            ohne_menge += 1
        if k.in_summe:
            if k.gp is None:
                vollstaendig = False
            else:
                netto += _dez(k.gp)
    netto = _cent(netto)
    geschaetzt = sum(k.geschaetzt for k in positionen)
    return kalkulation.model_copy(update={
        "positionen": positionen, "summe_netto": float(netto),
        "summe_brutto": float(_cent(netto * (1 + _dez(kalkulation.mwst_satz)))),
        "ohne_preis": ohne_preis, "ohne_menge": ohne_menge, "vollstaendig": vollstaendig,
        "enthaelt_schaetzungen": geschaetzt > 0, "geschaetzt_anzahl": geschaetzt,
    })


def ergaenze_indexpreise(kalkulation: Kalkulation | None) -> Kalkulation | None:
    """Index stage for every ``kein_treffer`` item; never raises."""
    if kalkulation is None or not any(k.treffer == "kein_treffer" for k in kalkulation.positionen):
        return kalkulation
    try:
        neu = []
        for k in kalkulation.positionen:
            treffer = index_preis(k.kurztext, k.einheit) if k.treffer == "kein_treffer" else None
            neu.append(k if treffer is None else _mit_schaetzung(
                k, "index", treffer["ep"], treffer["ep_von"], treffer["ep_bis"], treffer["quellen"],
                treffer["hinweis"]))
        return neu_summieren(kalkulation, neu)
    except Exception:  # noqa: BLE001 - a fallback must never break the analysis
        log.exception("Index price fallback failed")
        return kalkulation.model_copy(update={
            "warnungen": [*kalkulation.warnungen, "Index price fallback failed; items stay without a price."]})


def ergaenze_recherchepreise(kalkulation: Kalkulation | None, lv: LV, *, aufruf=None,
                             fortschritt=None) -> Kalkulation | None:
    """Web research stage for items still without a price; never raises."""
    if kalkulation is None or not any(k.treffer == "kein_treffer" for k in kalkulation.positionen):
        return kalkulation
    from . import recherche  # local import: recherche pulls in the model layer
    try:
        ergebnisse, warnungen = recherche.recherchiere_fehlende_preise(
            lv, kalkulation, aufruf=aufruf, fortschritt=fortschritt)
    except Exception:  # noqa: BLE001
        log.exception("Price research fallback failed")
        ergebnisse, warnungen = {}, ["Web price research failed; items stay without a price."]
    neu = []
    for k in kalkulation.positionen:
        e = ergebnisse.get(k.oz) if k.treffer == "kein_treffer" else None
        werte = [w for w in (e.marktpreis_von, e.marktpreis_bis) if w is not None] if e else []
        if not werte:
            neu.append(k)
            continue
        ep = float(_cent(sum(_dez(w) for w in werte) / len(werte)))
        neu.append(_mit_schaetzung(
            k, "recherche", ep, e.marktpreis_von, e.marktpreis_bis,
            [PreisQuelle(titel=q.titel or q.url, url=q.url) for q in e.quellen],
            f"Web research estimate: midpoint of the sourced market range. {e.text}"[:600]))
    ergebnis = neu_summieren(kalkulation, neu) if ergebnisse else kalkulation
    if warnungen:
        ergebnis = ergebnis.model_copy(update={"warnungen": [*ergebnis.warnungen, *warnungen]})
    return ergebnis

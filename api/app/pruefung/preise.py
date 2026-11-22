"""Price the original bill from a supplied price list (B6, epic #93).

Deterministic, offline, no model calls. Per position the price-list entry is
matched in this order:

1. same OZ,
2. normalised short text and the same canonical unit (exact),
3. token similarity of the short text with the same unit, at least AEHNLICHKEIT_MIN.

A unit mismatch never matches. An OZ match is also accepted when the bill
position has no unit (unknown is not a mismatch); text matches always need
both units. No price is invented: positions without a match keep ``ep``/``gp``
null and are counted in ``ohne_preis``.
"""
import re
import unicodedata
from collections.abc import Callable
from decimal import ROUND_HALF_UP, Decimal

from ..modelle import LV, Kalkulation, KalkulationsPosition, Position, Preisliste, PreislistenEintrag
from .regeln import _kanonische_einheit

AEHNLICHKEIT_MIN = 0.8
MWST_SATZ = 0.19
CENT = Decimal("0.01")
# Position types that are priced but not added to the total (shown only).
NICHT_IN_SUMME = frozenset({"bedarf", "alternativ"})
# Unit spellings beyond the typo list in regeln.py that mean the same unit.
WEITERE_EINHEITEN = {"m^2": "m²", "m^3": "m³", "std": "h", "std.": "h", "pauschal": "psch",
                     "stück": "St", "st.": "St", "lm": "m"}

# B9 (#133): seam for the price database (D5 registers `als_preisliste()` here). None = today's behaviour.
preis_service: Callable[[], Preisliste | None] | None = None
PREIS_DB_ID = "preis-db"

_TOKEN = re.compile(r"[^\W_]+")


def _cent(wert: Decimal) -> Decimal:
    return wert.quantize(CENT, rounding=ROUND_HALF_UP)


def _dez(wert: float) -> Decimal:
    return Decimal(str(wert))


def kanonische_einheit(einheit: str | None) -> str | None:
    if einheit is None or not einheit.strip():
        return None
    roh = einheit.strip()
    kanon = WEITERE_EINHEITEN.get(roh.lower(), _kanonische_einheit(roh))
    return kanon.casefold()


def normalisiere_text(text: str) -> str:
    return " ".join(tokens(text))


def tokens(text: str) -> list[str]:
    return _TOKEN.findall(unicodedata.normalize("NFKC", text or "").casefold())


def aehnlichkeit(a: str, b: str) -> float:
    """Dice coefficient over the token sets of two short texts (0–1)."""
    ta, tb = set(tokens(a)), set(tokens(b))
    if not ta or not tb:
        return 0.0
    return 2 * len(ta & tb) / (len(ta) + len(tb))


def _normalisiere_oz(oz: str | None) -> str | None:
    if oz is None:
        return None
    wert = re.sub(r"\s+", "", oz).rstrip(".")
    return wert or None


def _finde_eintrag(pos: Position, eintraege: list[PreislistenEintrag]
                   ) -> tuple[str, PreislistenEintrag | None, float | None]:
    einheit = kanonische_einheit(pos.einheit)
    oz = _normalisiere_oz(pos.oz)
    for eintrag in eintraege:
        if oz and _normalisiere_oz(eintrag.oz) == oz and einheit in (None, kanonische_einheit(eintrag.einheit)):
            return "oz", eintrag, round(aehnlichkeit(pos.kurztext, eintrag.kurztext), 3)
    if einheit is None:
        return "kein_treffer", None, None
    gleiche_einheit = [e for e in eintraege if kanonische_einheit(e.einheit) == einheit]
    text = normalisiere_text(pos.kurztext)
    if text:
        for eintrag in gleiche_einheit:
            if normalisiere_text(eintrag.kurztext) == text:
                return "text", eintrag, 1.0
    bester, beste = None, 0.0
    for eintrag in gleiche_einheit:  # first entry wins on ties, so the result is deterministic
        wert = aehnlichkeit(pos.kurztext, eintrag.kurztext)
        if wert > beste:
            bester, beste = eintrag, wert
    if bester is not None and beste >= AEHNLICHKEIT_MIN:
        return "aehnlich", bester, round(beste, 3)
    return "kein_treffer", None, None


def _differenz(a: Decimal | None, b: float | None) -> float | None:
    return None if a is None or b is None else float(_cent(a - _dez(b)))


def hole_preis_db() -> tuple[Preisliste | None, list[str]]:
    """Price database via the seam; an unreachable or failing service gives (None, warning), never an exception."""
    if preis_service is None:
        return None, []
    try:
        return preis_service(), []
    except Exception:  # noqa: BLE001 - any failure of the price DB must not break the analysis
        return None, ["Price database unreachable: prices come from the uploaded price list only."]


def kalkuliere_mit_preis_db(lv: LV, preisliste: Preisliste | None, mwst_satz: float = MWST_SATZ,
                            indexpreise: bool = True) -> Kalkulation | None:
    """Uploaded list first, the price database fills `kein_treffer`, then the index price fallback
    (``preis_fallback``, estimates marked). None when there is no price source at all (no upload, no
    database), so the report stays as without pricing. Also used for added items (B8)."""
    datenbank, warnungen = hole_preis_db()
    if preisliste is None and datenbank is None:
        if not warnungen:
            return None
        preisliste = Preisliste(id=PREIS_DB_ID)  # DB failed and nothing uploaded: empty, marked, with the warning
    kalkulation = kalkuliere(lv, preisliste, mwst_satz, ergaenzung=datenbank)
    kalkulation.warnungen.extend(warnungen)
    if not indexpreise:
        return kalkulation
    from .preis_fallback import ergaenze_indexpreise  # t237: index price for items without a match
    return ergaenze_indexpreise(kalkulation)


def kalkuliere(lv: LV, preisliste: Preisliste | None, mwst_satz: float = MWST_SATZ,
               ergaenzung: Preisliste | None = None) -> Kalkulation:
    """`ergaenzung` (price database) is only consulted for positions the main list does not match."""
    haupt = preisliste if preisliste is not None else ergaenzung
    if preisliste is None:
        ergaenzung = None
    positionen: list[KalkulationsPosition] = []
    netto = Decimal("0")
    ohne_preis = ohne_menge = 0
    vollstaendig = True
    for pos in lv.positionen:
        treffer, eintrag, wert = _finde_eintrag(pos, haupt.eintraege)
        quelle = haupt.id
        if eintrag is None and ergaenzung is not None:
            treffer, eintrag, wert = _finde_eintrag(pos, ergaenzung.eintraege)
            quelle = ergaenzung.id
        ep = _dez(eintrag.ep) if eintrag else None
        gp = _cent(_dez(pos.menge) * ep) if ep is not None and pos.menge is not None else None
        in_summe = pos.typ not in NICHT_IN_SUMME
        if eintrag is None:
            ohne_preis += 1
        elif gp is None:
            ohne_menge += 1
        if in_summe:
            if gp is None:
                vollstaendig = False
            else:
                netto += gp
        positionen.append(KalkulationsPosition(
            oz=pos.oz, kurztext=pos.kurztext, menge=pos.menge, einheit=pos.einheit,
            ep=float(ep) if ep is not None else None, gp=float(gp) if gp is not None else None,
            ep_lv=pos.ep, gp_lv=pos.gp, ep_differenz=_differenz(ep, pos.ep), gp_differenz=_differenz(gp, pos.gp),
            treffer=treffer, preis_eintrag=eintrag.id if eintrag else None,
            preisliste_id=quelle if eintrag else None, aehnlichkeit=wert, in_summe=in_summe,
        ))
    netto = _cent(netto)
    return Kalkulation(
        preisliste_id=haupt.id, waehrung=haupt.waehrung, mwst_satz=mwst_satz, positionen=positionen,
        summe_netto=float(netto), summe_brutto=float(_cent(netto * (1 + _dez(mwst_satz)))),
        ohne_preis=ohne_preis, ohne_menge=ohne_menge, vollstaendig=vollstaendig,
    )

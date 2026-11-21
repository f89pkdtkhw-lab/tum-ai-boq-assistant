"""Structured adjustments from the reports (epic #93, issue #113, B7). Pure, offline, additive.

Findings and notes stay unchanged; this module only derives a machine-readable list of
`Anpassung` objects that B8 (#114) applies to build the estimated bill. An adjustment is only
produced where a number is evidenced; text-only suggestions stay hints. No adjustment carries a
price: unit prices come only from the price list (B6) and the estimated bill (B8).

Producers:

* Report 1 (`regelwerk`)
  - layer area deviation (`MENGE_SCHICHTEN_ABWEICHUNG`, mengen.py) → `menge` to the group
    median; a plausibility assumption, so approval is required;
  - missing required item (`NORM_POSITION_FEHLT`, B2 #95) → `hinzufuegen`, only when the source
    states what and how much (`normen.fehlende_positionen`); a new OZ `NEU-<n>` marks the item;
  - duplicate content (`INHALT_DUPLIKAT`) → `entfernen` of the later item, only when it is
    certain: same section, same item type and a non-empty short text; the first item is kept;
  - `NORM_EXTRA` is a notice and never removes an item.
* Report 2 (`vergleich`): a `historical_adjustment` note whose ± approximation is flagged too
  big (bewertung.approximation_zu_gross) → `menge` toward the comparable cases, approval required.
* Report 3 (`was_wenn`): a `what_if` note for an item with a high-chance what-if entry → `menge`,
  approval required.

A note only counts as a quantity statement when its unit matches the item unit and its base value
equals the item quantity. Items whose OZ is not unique are never adjusted (the OZ would be
ambiguous). At most one quantity change per item: Report 1 before Report 2 before Report 3, and
none for an item that is removed.
"""
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from ..modelle import Anpassung, Finding, LV, Position
from .bewertung import approximation_zu_gross
from .mengen import UNITS, erwartete_schichtmengen
from .normen import NORM_POSITION_FEHLT, fehlende_positionen

NEU_PRAEFIX = "NEU-"
MENGE_TOLERANZ = 1e-6
NACHKOMMASTELLEN = 3

_BERICHT_REIHENFOLGE = {"regelwerk": 0, "vergleich": 1, "was_wenn": 2}


@dataclass(frozen=True)
class FehlendePosition:
    """What and how much is missing, as B2 (`NORM_POSITION_FEHLT`) knows it. No price."""
    kurztext: str
    einheit: str
    menge: float
    titel_pfad: tuple[str, ...] = field(default_factory=tuple)
    langtext: str = ""


def _num(value: float) -> str:
    return f"{value:g}".replace(".", ",")


def _einheit(einheit: str | None) -> str | None:
    entry = UNITS.get((einheit or "").strip().casefold())
    return entry[0] if entry else None


def _gleich(a: float, b: float) -> bool:
    return abs(a - b) <= MENGE_TOLERANZ * max(1.0, abs(a), abs(b))


def _feld(obj: Any, name: str) -> Any:
    return obj.get(name) if isinstance(obj, Mapping) else getattr(obj, name, None)


def _menge(finding_id: str, pos: Position, neu: float, grund: str, bericht: str,
           freigabe: bool) -> Anpassung | None:
    neu = round(neu, NACHKOMMASTELLEN)
    if pos.menge is None or neu < 0 or _gleich(pos.menge, neu):
        return None
    return Anpassung(id=f"ANPASSUNG:menge:{finding_id}", oz=pos.oz, art="menge",
                     menge_alt=pos.menge, menge_neu=neu, grund=grund, bericht=bericht,
                     finding_id=finding_id, freigabe_noetig=freigabe)


def _aus_mengen(lv: LV, findings: Sequence[Finding], eindeutig: Mapping[str, Position]) -> list[Anpassung]:
    erwartet = erwartete_schichtmengen(lv)
    ergebnis = []
    for f in findings:
        pos = eindeutig.get(f.oz)
        if f.regel_id != "MENGE_SCHICHTEN_ABWEICHUNG" or f.id not in erwartet or pos is None:
            continue
        mid = erwartet[f.id]
        a = _menge(f.id, pos, mid,
                   f"Layer area {_num(pos.menge)} m² deviates from the median {_num(round(mid, 3))} m² "
                   f"of the layers of the same component; plausibility assumption, not a standard.",
                   "regelwerk", True)
        if a:
            ergebnis.append(a)
    return ergebnis


def _aus_fehlenden(findings: Sequence[Finding], fehlende: Mapping[str, Any]) -> list[Anpassung]:
    ergebnis = []
    for f in findings:
        spec = fehlende.get(f.id)
        if f.regel_id != NORM_POSITION_FEHLT or spec is None:
            continue
        kurztext, einheit, menge = (_feld(spec, "kurztext") or "", _feld(spec, "einheit") or "",
                                    _feld(spec, "menge"))
        if not kurztext.strip() or not einheit.strip() or menge is None or menge <= 0:
            continue  # "what" or "how much" unknown: stays a hint
        if not f.titel.endswith(f": {kurztext}"):
            continue  # the structured entry must describe exactly this finding
        oz = f"{NEU_PRAEFIX}{len(ergebnis) + 1}"
        position = Position(oz=oz, kurztext=kurztext, langtext=_feld(spec, "langtext") or "",
                            menge=round(menge, NACHKOMMASTELLEN), einheit=einheit,
                            titel_pfad=list(_feld(spec, "titel_pfad") or ()))
        ergebnis.append(Anpassung(
            id=f"ANPASSUNG:hinzufuegen:{f.id}", oz=oz, art="hinzufuegen", menge_alt=None,
            menge_neu=position.menge, position=position,
            grund=f"Required item missing (near OZ {f.oz}): {kurztext}, {_num(position.menge)} {einheit}; "
                  f"quantity as stated or derived by the source of {f.regel_id}.",
            bericht="regelwerk", finding_id=f.id, freigabe_noetig=False))
    return ergebnis


def _register_fehlende(lv: LV, findings: Sequence[Finding]) -> Mapping[str, Any]:
    """Default: B2's numbers from the curated register, only when B2 reported a missing item."""
    if not any(f.regel_id == NORM_POSITION_FEHLT for f in findings):
        return {}
    try:
        return fehlende_positionen(lv)
    except (OSError, ValueError):  # register unreadable: the findings stay hints
        return {}


def _aus_duplikaten(lv: LV, findings: Sequence[Finding], eindeutig: Mapping[str, Position]) -> list[Anpassung]:
    ergebnis = []
    for f in findings:
        dup = eindeutig.get(f.oz)
        if f.regel_id != "INHALT_DUPLIKAT" or dup is None or not dup.kurztext.strip():
            continue
        schluessel = (dup.kurztext, dup.langtext, dup.einheit, dup.menge, dup.ep)
        erste = next((p for p in lv.positionen
                      if (p.kurztext, p.langtext, p.einheit, p.menge, p.ep) == schluessel), None)
        if erste is None or erste is dup or erste.oz == dup.oz:
            continue
        if erste.titel_pfad != dup.titel_pfad or erste.typ != dup.typ:
            continue  # same work in two sections may be intended
        ergebnis.append(Anpassung(
            id=f"ANPASSUNG:entfernen:{f.id}", oz=dup.oz, art="entfernen", menge_alt=dup.menge,
            menge_neu=0, grund=f"Identical content to OZ {erste.oz} in the same section; "
                               f"OZ {erste.oz} is kept, the duplicate OZ {dup.oz} is removed.",
            bericht="regelwerk", finding_id=f.id, freigabe_noetig=False))
    return ergebnis


def _mengen_note(note: Any, eindeutig: Mapping[str, Position]) -> Position | None:
    """The item when the note states its quantity: same unit and base value = item quantity."""
    pos = eindeutig.get(_feld(note, "oz"))
    base, est = _feld(note, "base_value"), _feld(note, "estimated_value")
    if pos is None or pos.menge is None or base is None or est is None:
        return None
    unit = _einheit(_feld(note, "unit"))
    if unit is None or unit != _einheit(pos.einheit) or not _gleich(base, pos.menge):
        return None
    return pos


def _aus_notes(notes: Sequence[Any], was_wenn: Sequence[Any], eindeutig: Mapping[str, Position]) -> list[Anpassung]:
    hohe_chance = {_feld(w, "oz"): w for w in was_wenn if _feld(w, "chance") == "hoch"}
    ergebnis = []
    for note in notes:
        step, note_id = _feld(note, "step"), _feld(note, "id")
        pos = _mengen_note(note, eindeutig)
        if pos is None or not note_id:
            continue
        est = _feld(note, "estimated_value")
        if step == "historical_adjustment" and approximation_zu_gross(note):
            grund = (f"Report 2: comparable cases suggest {_num(est)} {pos.einheit} instead of "
                     f"{_num(pos.menge)}; approximation flagged too big, approval required.")
            bericht = "vergleich"
        elif step == "what_if" and pos.oz in hohe_chance:
            empfehlung = _feld(hohe_chance[pos.oz], "empfehlung") or ""
            grund = (f"Report 3: high chance in this project, recommended {_num(est)} {pos.einheit} "
                     f"instead of {_num(pos.menge)}; approval required. {empfehlung}").strip()
            bericht = "was_wenn"
        else:
            continue
        a = _menge(note_id, pos, est, grund, bericht, True)
        if a:
            ergebnis.append(a)
    return ergebnis


def anpassungen_ableiten(lv: LV, findings: Sequence[Finding], notes: Iterable[Any] = (),
                         was_wenn: Iterable[Any] = (),
                         fehlende: Mapping[str, Any] | None = None) -> list[Anpassung]:
    """Adjustments for the estimated bill, derived from findings, step notes and the what-if list.

    `notes`: step API notes (B5, `historical_adjustment` / `what_if`); `was_wenn`: what-if entries
    with `oz` and `chance`; `fehlende`: B2's structured missing items keyed by finding id
    (`normen.fehlende_positionen`, or `FehlendePosition`); without it, the curated register is used.
    All are optional; with today's findings alone, only Report 1 adjustments are produced.
    """
    notes, was_wenn = list(notes), list(was_wenn)
    anzahl = Counter(p.oz for p in lv.positionen)
    eindeutig = {p.oz: p for p in lv.positionen if anzahl[p.oz] == 1}

    entfernen = _aus_duplikaten(lv, findings, eindeutig)
    entfernt = {a.oz for a in entfernen}
    mengen = sorted(_aus_mengen(lv, findings, eindeutig) + _aus_notes(notes, was_wenn, eindeutig),
                    key=lambda a: _BERICHT_REIHENFOLGE[a.bericht])
    gesehen: set[str] = set()
    menge_je_oz = []
    for a in mengen:  # one quantity change per item, the earliest report wins
        if a.oz in entfernt or a.oz in gesehen:
            continue
        gesehen.add(a.oz)
        menge_je_oz.append(a)
    return menge_je_oz + _aus_fehlenden(findings, _register_fehlende(lv, findings) if fehlende is None else fehlende) + entfernen

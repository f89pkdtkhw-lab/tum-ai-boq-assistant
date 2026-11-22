"""B5 (#98): three separate reports, the final report and the what-if list (epic #93, steps 3-7).

`ergaenze_berichte(pruefbericht)` adds the optional fields `berichte`, `was_wenn` and
`schlussbericht` to an existing review report. Existing fields are never changed.

* **Report 1 `regelwerk`** – every rule/norm/model finding by id, with severity groups
  (big problem = kritisch/hoch, warning = mittel, notice = niedrig).
* **Report 2 `vergleich`** – all DB tags are compared with the LV description. No comparable
  tag → `neue_tags` proposal and no approximation. Otherwise recent cases by tag feed the
  existing estimate step (`step_api.select_cases` / `estimate` / `estimate_note`, Note 3) for a
  ± approximation per item; approximations above `ZU_GROSS_SCHWELLE` are flagged. Problems from
  the notes/marks of these similar projects are listed as well.
* **Report 3 `was_wenn`** – recent cases overall, problems from their notes/marks and the
  chance that each one applies here. High chance → recommendation (increase/decrease and why);
  low chance → listed for awareness. Never a penalty.
* **Final report** – one row per bill item (none dropped) with problems and their references,
  warnings, the ± approximation (estimated · ± · why · need to add · problem · recommendation),
  plus the project description. The what-if list is `Pruefbericht.was_wenn`.

History access goes only through the D1 DB actions, behind the seam `history_db` (protocol
`HistoryDB` below; None = not connected). If it is None or fails, Reports 2/3 get
`status="nicht_verbunden"` with a readable message and everything else still works.

Deterministic and offline by default: no invented items, prices or standards. With a usable key
(#167) Claude adds comparable tags and rates the chance of each noted problem (`berichte_ki`); without
a key or on any model error the deterministic result stays. Case texts are data, never instructions.
Every approximation stays approval-required.
"""
import json
import logging
import re
from collections import Counter
from collections.abc import Iterable, Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Protocol

from ..ai import step_api
from ..ai.step_api import Assumptions, Baseline, EstimatePosition, HistoryRecord, Measurement
from ..modelle import (
    LV, Bericht, Finding, Naeherung, Position, ProblemVerweis, Pruefbericht, Schlussbericht,
    SchlussPosition, WasWenn, Zaehler, Zusammenfassung,
)
from .bewertung import zusammenfassen
from . import berichte_ki  # #167: AI checks 2/3 (Claude) on top of the deterministic matching

log = logging.getLogger(__name__)

ZU_GROSS_SCHWELLE = Decimal("0.25")  # |factor - 1| above 25 % → "approximation too big"
FALL_LIMIT = 20  # cases per DB call (step API limit range 3-20)
METRIK = "menge"
# Target concept (epic #93): Report 2 always uses the step API's only ratio method. The result
# stays an approval-required estimate (Note 3); nothing is applied to the bill automatically.
ZIELKONZEPT_ANNAHMEN = {"ratio_method": "median", "selected_by": "estimator"}

TITEL = {"regelwerk": "Report 1 – regulations", "vergleich": "Report 2 – similar projects",
         "was_wenn": "Report 3 – what-if"}
NICHT_VERBUNDEN = ("History database is not connected (DB actions D1/D2); "
                   "this report is skipped, the rest of the review is complete.")
NICHT_ERREICHBAR = ("History database is not reachable ({art}); "
                    "this report is skipped, the rest of the review is complete.")

GROSS, WARNUNG, HINWEIS = {"kritisch", "hoch"}, {"mittel"}, {"niedrig"}
MEHR = {"underestimated", "unterschätzt", "unterschaetzt", "more", "mehr", "higher", "höher",
        "hoeher", "additional", "zusätzlich", "zusaetzlich", "missing", "fehlte", "fehlend",
        "fehlende", "increase", "increased", "extra", "nachtrag", "exceeded", "überschritten"}
WENIGER = {"overestimated", "überschätzt", "ueberschaetzt", "less", "weniger", "lower",
           "niedriger", "fewer", "decrease", "decreased", "unnecessary", "entfiel", "entfallen",
           "unused", "unneeded"}
STOPP = {
    "with", "from", "than", "that", "this", "were", "was", "have", "been", "into", "over", "under",
    "much", "very", "also", "only", "item", "items", "work", "works", "case", "project", "because",
    "after", "before", "during", "about", "some", "they", "their", "there", "when", "which",
    "eine", "einer", "eines", "einem", "einen", "der", "die", "das", "und", "oder", "mit", "von",
    "für", "fuer", "nicht", "wurde", "wurden", "war", "waren", "sind", "ist", "auch", "nur",
    "beim", "durch", "nach", "über", "ueber", "unter", "zum", "zur", "bei", "aus", "position",
    "leistung", "arbeiten", "liefern", "herstellen", "einbauen", "gemäß", "gemaess", "inkl",
    "synthetic", "synthetisch",
} | MEHR | WENIGER
_WORT = re.compile(r"[a-zäöüß]+")


class HistoryDB(Protocol):
    """D1 DB actions used here (epic #93: all tags · recent by tag · recent overall).

    Records follow the 7 DB columns: id, date, description, tags, expected_json, actual_json,
    note (dicts or pydantic models). `tags()` may return names, `{tag: count}` or
    `[{"tag": ..., "count": ...}]`.
    """

    def tags(self) -> Iterable[Any]: ...

    def records_by_tag(self, tag: str, limit: int) -> Iterable[Any]: ...

    def records_latest(self, limit: int) -> Iterable[Any]: ...


# Seam for D1/D2: set at start-up to an object with the three actions. None = not connected.
history_db: HistoryDB | None = None
_SEAM = object()


class _NichtErreichbar(Exception):
    pass


# ---------------------------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------------------------
def _woerter(text: str) -> set[str]:
    return {w for w in _WORT.findall(text.casefold()) if len(w) >= 4 and w not in STOPP}


def _norm(text: str) -> str:
    return " ".join(text.casefold().split())


def _rund(wert: Decimal | float, stellen: int = 2) -> float:
    return float(round(Decimal(str(wert)), stellen))


def _zahl(wert: Any) -> float | None:
    if isinstance(wert, bool) or wert is None:
        return None
    try:
        zahl = float(str(wert).replace(",", ".")) if isinstance(wert, str) else float(wert)
    except (TypeError, ValueError):
        return None
    return zahl if zahl == zahl and zahl not in (float("inf"), float("-inf")) else None


def _gruppe(schwere: str) -> str:
    return "grosse_probleme" if schwere in GROSS else "warnungen" if schwere in WARNUNG else "hinweise"


def _db_aufruf(funktion, *args) -> list[Any]:
    try:
        return list(funktion(*args) or [])
    except Exception as exc:  # connection refused, missing table, timeout …
        raise _NichtErreichbar(type(exc).__name__) from None


def _nicht_verbunden(bericht_id: str, meldung: str) -> Bericht:
    return Bericht(id=bericht_id, titel=TITEL[bericht_id], status="nicht_verbunden", meldung=meldung)


def _fehler(bericht_id: str) -> Bericht:
    return Bericht(id=bericht_id, titel=TITEL[bericht_id], status="fehler",
                   meldung="This report could not be built; the rest of the review is complete.")


# ---------------------------------------------------------------------------------------------
# DB records (7 columns) → normalised form
# ---------------------------------------------------------------------------------------------
def _als_dict(roh: Any) -> dict[str, Any]:
    if hasattr(roh, "model_dump"):
        return roh.model_dump(mode="json")
    if isinstance(roh, dict):
        return roh
    return dict(vars(roh))


def _json(wert: Any) -> Any:
    if isinstance(wert, str):
        try:
            return json.loads(wert)
        except ValueError:
            return wert
    return wert


def _datum(wert: Any) -> date:
    if isinstance(wert, datetime):
        return wert.date()
    if isinstance(wert, date):
        return wert
    return date.fromisoformat(str(wert).strip()[:10])


def _erstes(eintrag: dict, *schluessel: str) -> Any:
    for key in schluessel:
        if eintrag.get(key) not in (None, ""):
            return eintrag[key]
    return None


def _messwerte(roh: Any) -> list[dict[str, Any]]:
    """Objects of expected_json/actual_json as {oz, kurztext, menge, einheit}; tolerant shapes."""
    roh = _json(roh)
    eintraege: list[Any] = []
    if isinstance(roh, list):
        eintraege = roh
    elif isinstance(roh, dict):
        for key in ("positionen", "positions", "items", "objects", "objekte", "measurements", "values"):
            if isinstance(roh.get(key), list):
                eintraege = roh[key]
                break
        else:
            if roh and all(isinstance(v, dict) for v in roh.values()):
                eintraege = [{"oz": k, **v} for k, v in roh.items()]
    werte = []
    for eintrag in eintraege:
        if not isinstance(eintrag, dict):
            continue
        metrik = eintrag.get("metric")
        menge = _erstes(eintrag, "menge", "quantity", "qty")
        if menge is None and metrik in (None, "menge", "quantity"):
            menge = eintrag.get("value")
        werte.append({
            "oz": str(_erstes(eintrag, "oz", "position", "case_oz") or "").strip(),
            "kurztext": str(_erstes(eintrag, "kurztext", "text", "name", "objekt", "object",
                                    "description") or ""),
            "menge": _zahl(menge),
            "einheit": str(_erstes(eintrag, "einheit", "unit") or "").strip(),
        })
    return werte


def _probleme_aus_notiz(roh: Any) -> list[str]:
    """Problems from the note/marks column: free text, lines or JSON marks."""
    roh = _json(roh)
    teile: list[str] = []
    if isinstance(roh, str):
        teile = re.split(r"[\n;|]+", roh)
    elif isinstance(roh, list):
        for eintrag in roh:
            if isinstance(eintrag, str):
                teile += re.split(r"[\n;|]+", eintrag)
            elif isinstance(eintrag, dict):
                text = " – ".join(str(eintrag[k]) for k in ("what_happened", "reason", "text", "note",
                                                            "problem") if eintrag.get(k))
                teile.append(text)
    elif isinstance(roh, dict):
        return _probleme_aus_notiz([roh])
    return [t.strip() for t in teile if len(t.strip()) >= 3]


def _fall(roh: Any) -> dict[str, Any]:
    eintrag = _als_dict(roh)
    return {
        "case_id": str(_erstes(eintrag, "id", "case_id")),
        "date": _datum(eintrag.get("date")),
        "description": str(eintrag.get("description") or ""),
        "tags": [str(t).strip().casefold() for t in (_json(eintrag.get("tags")) or []) if str(t).strip()],
        "expected": _messwerte(_erstes(eintrag, "expected_json", "estimated_values")),
        "actual": _messwerte(_erstes(eintrag, "actual_json", "real_values")),
        "probleme": _probleme_aus_notiz(_erstes(eintrag, "note", "notes", "marks")),
    }


def _faelle(rohe: Iterable[Any]) -> list[dict[str, Any]]:
    """Normalised cases; records without id or with an unreadable date are skipped."""
    faelle = []
    for roh in rohe:
        try:
            fall = _fall(roh)
        except (TypeError, ValueError, AttributeError):
            continue
        if fall["case_id"] not in ("", "None"):
            faelle.append(fall)
    return faelle


def _tag_namen(roh: Iterable[Any]) -> list[str]:
    if isinstance(roh, dict):
        roh = list(roh)
    namen = []
    for eintrag in roh:
        name = _erstes(eintrag, "tag", "name") if isinstance(eintrag, dict) else eintrag
        name = str(name or "").strip().casefold()
        if name and name not in namen:
            namen.append(name)
    return namen


# ---------------------------------------------------------------------------------------------
# LV description, tag comparison and new-tag proposal
# ---------------------------------------------------------------------------------------------
def _lv_text(lv: LV) -> str:
    teile = [lv.name, *[" ".join(p.titel_pfad) + " " + p.kurztext + " " + p.langtext for p in lv.positionen]]
    return " ".join(teile).casefold()


def vergleichbare_tags(lv: LV, db_tags: Sequence[str]) -> list[str]:
    """DB tags that occur in the LV description (whole word, or inside a compound word ≥ 5 letters)."""
    text = _lv_text(lv)
    woerter = set(_WORT.findall(text))
    return [t for t in db_tags if t in woerter or (len(t) >= 5 and t in text)]


def neue_tags_vorschlag(lv: LV, anzahl: int = 3) -> list[str]:
    """Most frequent descriptive words of the LV name and section titles, then short texts."""
    zaehler: Counter[str] = Counter()
    for text in [lv.name, *{" ".join(p.titel_pfad) for p in lv.positionen}]:
        zaehler.update(_woerter(text))
    if len(zaehler) < anzahl:
        for p in lv.positionen:
            zaehler.update(_woerter(p.kurztext))
    return [w for w, _ in sorted(zaehler.items(), key=lambda kv: (-kv[1], kv[0]))[:anzahl]]


# ---------------------------------------------------------------------------------------------
# Problems from notes/marks and their chance in this project
# ---------------------------------------------------------------------------------------------
def _richtung(problem: str) -> str | None:
    woerter = set(_WORT.findall(problem.casefold()))
    mehr, weniger = bool(woerter & MEHR), bool(woerter & WENIGER)
    return "mehr" if mehr and not weniger else "weniger" if weniger and not mehr else None


def bewerte_probleme(lv: LV, faelle: Sequence[dict[str, Any]], projekt_tags: set[str]) -> list[WasWenn]:
    """Group identical problems across cases and rate their chance for this LV (deterministic).

    High chance: an item of this bill shares ≥ 2 keywords with the problem, or 1 keyword and
    the case shares a comparable tag with this project. Otherwise low chance (awareness only).
    """
    gruppen: dict[str, dict[str, Any]] = {}
    for fall in faelle:
        for problem in fall["probleme"]:
            gruppe = gruppen.setdefault(_norm(problem), {"text": problem, "ids": [], "tags": set()})
            if fall["case_id"] not in gruppe["ids"]:
                gruppe["ids"].append(fall["case_id"])
            gruppe["tags"] |= set(fall["tags"])
    positionen = [(p, _woerter(" ".join([p.kurztext, p.langtext, *p.titel_pfad])),
                   " ".join([p.kurztext, p.langtext, *p.titel_pfad]).casefold()) for p in lv.positionen]
    ergebnis = []
    for gruppe in gruppen.values():
        text, ids = gruppe["text"], gruppe["ids"]
        stichwoerter = _woerter(text)
        beste, treffer = None, set()
        for position, woerter, roh in positionen:
            hits = {w for w in stichwoerter if w in woerter or (len(w) >= 5 and w in roh)}
            if len(hits) > len(treffer):
                beste, treffer = position, hits
        gemeinsam = sorted(gruppe["tags"] & projekt_tags)
        hoch = beste is not None and (len(treffer) >= 2 or (treffer and gemeinsam))
        faelle_text = ", ".join(ids)
        if hoch:
            bezeichnung = f"OZ {beste.oz}" + (f" ({beste.kurztext})" if beste.kurztext else "")
            richtung = _richtung(text)
            verb = {"mehr": "Consider increasing", "weniger": "Consider decreasing"}.get(richtung, "Check")
            empfehlung = (f"{verb} the quantity of {bezeichnung}: past case(s) {faelle_text} report "
                          f"\"{text}\". Estimator approval required.")
            grund = f"Matches {bezeichnung} on {', '.join(sorted(treffer))}"
            grund += f" and shares tag(s) {', '.join(gemeinsam)}." if gemeinsam else "."
        else:
            empfehlung = ""
            grund = ("For awareness only: "
                     + (f"weak match with OZ {beste.oz} on {', '.join(sorted(treffer))}."
                        if beste is not None else "no item of this bill matches the problem."))
        ergebnis.append(WasWenn(oz=beste.oz if beste is not None else None, problem=text,
                                chance="hoch" if hoch else "niedrig", empfehlung=empfehlung,
                                case_ids=ids, begruendung=grund))
    return sorted(ergebnis, key=lambda w: (w.chance != "hoch", w.case_ids[0] if w.case_ids else "", w.problem))


def _probleme(lv: LV, faelle: Sequence[dict[str, Any]], projekt_tags: set[str], schritt: str
              ) -> tuple[list[WasWenn], bool]:
    """Deterministic rating, then Claude's rating when a model is configured (#167). True = rated by Claude."""
    liste = bewerte_probleme(lv, faelle, projekt_tags)
    ki = berichte_ki.bewerte_chancen(lv, liste, schritt)
    return (ki, True) if ki is not None else (liste, False)


# ---------------------------------------------------------------------------------------------
# Report 2: ± approximation per item through the existing estimate step (Note 3)
# ---------------------------------------------------------------------------------------------
def _passt(messwert: dict[str, Any], position: Position) -> bool:
    """Same object: equal short text, or equal OZ when a short text is missing on either side."""
    if messwert["kurztext"].strip() and position.kurztext.strip():
        return _norm(messwert["kurztext"]) == _norm(position.kurztext)
    return bool(messwert["oz"]) and messwert["oz"] == position.oz.strip()


def _messung(position: Position, messwert: dict[str, Any]) -> Measurement:
    return Measurement(oz=position.oz, metric=METRIK, value=messwert["menge"],
                       unit=messwert["einheit"] or position.einheit)


def naeherung(position: Position, faelle: Sequence[dict[str, Any]], vergleich_tags: Sequence[str]
              ) -> tuple[Naeherung | None, step_api.Note | None]:
    if position.menge is None or not (position.einheit or "").strip():
        return None, None
    kandidaten = []
    for fall in faelle:
        erwartet = [m for m in fall["expected"] if _passt(m, position)]
        if not erwartet:
            continue
        tatsaechlich = [m for m in fall["actual"] if _passt(m, position)]
        kandidaten.append(HistoryRecord(
            case_id=fall["case_id"], date=fall["date"], description=fall["description"], tags=fall["tags"],
            estimated_values=[_messung(position, m) for m in erwartet],
            real_values=[_messung(position, m) for m in tatsaechlich]))
    if not kandidaten:
        return None, None
    haeufig = Counter(t for r in kandidaten for t in set(r.tags) if t in vergleich_tags)
    if not haeufig:
        return None, None
    tag = sorted(haeufig.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    ziel = EstimatePosition(oz=position.oz, kurztext=position.kurztext, title_path=position.titel_pfad,
                            work_tags=[tag], metric=METRIK, unit=position.einheit)
    annahmen = Assumptions(**ZIELKONZEPT_ANNAHMEN, baseline=Baseline(
        value=position.menge, unit=position.einheit, source=f"LV quantity OZ {position.oz}"))
    auswahl = step_api.select_cases(ziel, kandidaten, "comparable", FALL_LIMIT)
    ergebnis = step_api.estimate(ziel, auswahl, annahmen)
    note = step_api.estimate_note(step_api.EstimateTarget(position=ziel, assumptions=annahmen),
                                  auswahl, ergebnis)
    if ergebnis.estimated_value is None or ergebnis.factor is None:
        return None, note
    menge = Decimal(str(position.menge))
    abweichung = ergebnis.estimated_value - menge
    ids = [c.case_id for c in auswahl.selected]
    eur = None if position.ep is None else _rund(abweichung * Decimal(str(position.ep)))
    return Naeherung(
        oz=position.oz, kurztext=position.kurztext, einheit=note.unit or position.einheit,
        menge=position.menge, geschaetzt=_rund(ergebnis.estimated_value), abweichung=_rund(abweichung),
        abweichung_prozent=_rund((ergebnis.factor - 1) * 100, 1), abweichung_eur=eur,
        zu_gross=abs(ergebnis.factor - 1) > ZU_GROSS_SCHWELLE, faktor=float(ergebnis.factor),
        case_ids=ids, note_id=note.id,
        warum=(f"Median actual/expected ratio {ergebnis.factor.normalize():f} over {len(ids)} similar "
               f"case(s) ({', '.join(ids)}) tagged '{tag}'; approval required."),
    ), note


def bericht_vergleich(lv: LV, db: HistoryDB) -> tuple[Bericht, set[str]]:
    db_tags = _tag_namen(_db_aufruf(db.tags))
    tags = vergleichbare_tags(lv, db_tags)
    ki_tags = [t for t in (berichte_ki.vergleiche_tags(lv, db_tags) or []) if t not in tags]  # #167
    tags = [*tags, *ki_tags]
    if not tags:
        vorschlag = neue_tags_vorschlag(lv)
        return Bericht(id="vergleich", titel=TITEL["vergleich"], status="ok", neue_tags=vorschlag,
                       meldung=(f"No comparable tag among {len(db_tags)} DB tag(s); no approximation. "
                                f"Proposed new tag(s): {', '.join(vorschlag) or 'none'}.")), set()
    faelle, gesehen = [], set()
    for tag in tags:
        for fall in _faelle(_db_aufruf(db.records_by_tag, tag, FALL_LIMIT)):
            if fall["case_id"] not in gesehen:
                gesehen.add(fall["case_id"])
                faelle.append(fall)
    oz_zaehler = Counter(p.oz for p in lv.positionen)
    naeherungen, notes = [], []
    for position in lv.positionen:
        if oz_zaehler[position.oz] > 1:
            continue  # duplicate OZ: an approximation could not be attributed to one item
        wert, note = naeherung(position, faelle, tags)
        if note is not None:
            notes.append(note.model_dump(mode="json"))
        if wert is not None:
            naeherungen.append(wert)
    probleme, von_ki = _probleme(lv, faelle, set(tags), "vergleich")
    zu_gross = sum(n.zu_gross for n in naeherungen)
    meldung = (f"{len(faelle)} similar case(s) for tag(s) {', '.join(tags)}; {len(naeherungen)} "
               f"approximation(s), {zu_gross} above ±{int(ZU_GROSS_SCHWELLE * 100)} %; "
               f"{len(probleme)} problem(s) from notes/marks.")
    if ki_tags:
        meldung += f" Claude matched tag(s) {', '.join(ki_tags)}."
    if von_ki:
        meldung += " Chances rated by Claude (model)."
    return Bericht(
        id="vergleich", titel=TITEL["vergleich"], status="ok", meldung=meldung, tags=tags, notes=notes,
        naeherungen=naeherungen, probleme=probleme,
        zaehler=Zaehler(zu_grosse_naeherungen=zu_gross, empfehlungen=sum(p.chance == "hoch" for p in probleme),
                        hinweise=sum(p.chance == "niedrig" for p in probleme)),
    ), set(tags)


def bericht_was_wenn(lv: LV, db: HistoryDB, projekt_tags: set[str]) -> Bericht:
    faelle = _faelle(_db_aufruf(db.records_latest, FALL_LIMIT))
    liste, von_ki = _probleme(lv, faelle, projekt_tags, "was_wenn")
    hoch = sum(w.chance == "hoch" for w in liste)
    return Bericht(
        id="was_wenn", titel=TITEL["was_wenn"], status="ok", probleme=liste,
        zaehler=Zaehler(empfehlungen=hoch, hinweise=len(liste) - hoch),
        meldung=(f"{len(faelle)} recent case(s); {len(liste)} problem(s) from notes/marks: {hoch} with "
                 f"high chance (recommendation), {len(liste) - hoch} for awareness. No score penalty."
                 + (" Chances rated by Claude (model)." if von_ki else "")),
    )


def bericht_regelwerk(findings: Sequence[Finding]) -> Bericht:
    gruppen = Counter(_gruppe(f.schwere) for f in findings)
    zaehler = Zaehler(**gruppen)
    return Bericht(
        id="regelwerk", titel=TITEL["regelwerk"], status="ok", finding_ids=[f.id for f in findings],
        zaehler=zaehler,
        meldung=(f"{len(findings)} finding(s) from rules, norm checks and the model: {zaehler.grosse_probleme} "
                 f"big problem(s), {zaehler.warnungen} warning(s), {zaehler.hinweise} notice(s)."),
    )


# ---------------------------------------------------------------------------------------------
# Final report
# ---------------------------------------------------------------------------------------------
def _projektbeschreibung(lv: LV, vergleich: Bericht) -> str:
    abschnitte = {tuple(p.titel_pfad) for p in lv.positionen if p.titel_pfad}
    text = f"{lv.name}: {len(lv.positionen)} item(s) in {len(abschnitte)} section(s)"
    if vergleich.tags:
        text += f"; comparable history tags: {', '.join(vergleich.tags)}"
    if vergleich.neue_tags:
        text += f"; proposed new tags: {', '.join(vergleich.neue_tags)}"
    return text + "."


def schlussbericht(lv: LV, findings: Sequence[Finding], berichte: Sequence[Bericht]) -> Schlussbericht:
    vergleich, was_wenn = berichte[1], berichte[2]
    erste = {}
    for index, p in enumerate(lv.positionen):
        erste.setdefault(p.oz, index)
    probleme: dict[int, list[ProblemVerweis]] = {}
    nachtraege: dict[int, list[str]] = {}
    allgemein = []
    for f in findings:
        verweis = ProblemVerweis(finding_id=f.id, schwere=f.schwere, titel=f.titel, quelle=f.quelle,
                                 regel_id=f.regel_id)
        if f.oz not in erste:
            allgemein.append(verweis)
            continue
        probleme.setdefault(erste[f.oz], []).append(verweis)
        if f.kategorie == "nachtrag":
            nachtraege.setdefault(erste[f.oz], []).append(f.titel)
    naeherungen = {n.oz: n for n in vergleich.naeherungen}
    empfehlungen: dict[str, list[str]] = {}
    for w in [*vergleich.probleme, *was_wenn.probleme]:
        if w.chance == "hoch" and w.oz and w.empfehlung not in empfehlungen.get(w.oz, []):
            empfehlungen.setdefault(w.oz, []).append(w.empfehlung)
    zeilen = []
    for index, p in enumerate(lv.positionen):
        erste_zeile = erste[p.oz] == index
        n = naeherungen.get(p.oz) if erste_zeile else None
        nachtrag = list(nachtraege.get(index, []))
        warnungen = []
        if n is not None:
            if n.abweichung > 0:
                nachtrag.append(f"Possible additional quantity +{n.abweichung:g} {n.einheit} from similar "
                                "projects (approval required).")
            if n.zu_gross:
                warnungen.append(f"Approximation {n.abweichung_prozent:+.1f} % exceeds "
                                 f"±{int(ZU_GROSS_SCHWELLE * 100)} %.")
        zeilen.append(SchlussPosition(
            oz=p.oz, kurztext=p.kurztext, menge=p.menge, einheit=p.einheit,
            geschaetzt=n.geschaetzt if n else None, abweichung=n.abweichung if n else None,
            abweichung_eur=n.abweichung_eur if n else None, warum=n.warum if n else "",
            nachtrag=nachtrag, probleme=probleme.get(index, []), warnungen=warnungen,
            empfehlungen=empfehlungen.get(p.oz, []) if erste_zeile else []))
    warnungen = [f"{b.titel}: {b.meldung}" for b in berichte if b.status != "ok"]
    zu_gross = sum(n.zu_gross for n in vergleich.naeherungen)
    if zu_gross:
        warnungen.append(f"{zu_gross} approximation(s) exceed ±{int(ZU_GROSS_SCHWELLE * 100)} %.")
    return Schlussbericht(projektbeschreibung=_projektbeschreibung(lv, vergleich), positionen=zeilen,
                          allgemein=allgemein, warnungen=warnungen)


# ---------------------------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------------------------
def erstelle_berichte(lv: LV, findings: Sequence[Finding], db: Any = _SEAM) -> dict[str, Any]:
    """`berichte` (always regelwerk, vergleich, was_wenn), `was_wenn` and `schlussbericht`."""
    db = history_db if db is _SEAM else db
    try:
        regelwerk = bericht_regelwerk(findings)
    except Exception:
        log.exception("Report 1 failed")
        regelwerk = _fehler("regelwerk")
    projekt_tags: set[str] = set()
    if db is None:
        vergleich, was_wenn = _nicht_verbunden("vergleich", NICHT_VERBUNDEN), _nicht_verbunden(
            "was_wenn", NICHT_VERBUNDEN)
    else:
        try:
            vergleich, projekt_tags = bericht_vergleich(lv, db)
        except _NichtErreichbar as exc:
            vergleich = _nicht_verbunden("vergleich", NICHT_ERREICHBAR.format(art=exc))
        except Exception:
            log.exception("Report 2 failed")
            vergleich = _fehler("vergleich")
        try:
            was_wenn = bericht_was_wenn(lv, db, projekt_tags)
        except _NichtErreichbar as exc:
            was_wenn = _nicht_verbunden("was_wenn", NICHT_ERREICHBAR.format(art=exc))
        except Exception:
            log.exception("Report 3 failed")
            was_wenn = _fehler("was_wenn")
    berichte = [regelwerk, vergleich, was_wenn]
    try:
        schluss = schlussbericht(lv, findings, berichte)
    except Exception:
        log.exception("Final report failed")
        schluss = None
    return {"berichte": berichte, "was_wenn": was_wenn.probleme, "schlussbericht": schluss}


def zusammenfassung_mit_berichten(findings: Sequence[Finding], berichte: Sequence[Bericht],
                                  n_positionen: int | None = None, modell: str | None = None) -> Zusammenfassung:
    """B1 summary on the B5 grouping: every finding belongs to Report 1; Report 2 approximations
    (approval-required Note 3) feed the "too big" penalty and count as recommendations, as do
    high-chance what-if items. Recommendations never cost points."""
    vergleich, was_wenn = berichte[1], berichte[2]
    ids = {n.note_id for n in vergleich.naeherungen}
    notes = [step_api.Note.model_validate(n) for n in vergleich.notes if n.get("id") in ids]
    basis = zusammenfassen(findings, notes, bericht_von=lambda f: "regelwerk",
                           n_positionen=n_positionen, modell=modell)
    hoch = sum(w.chance == "hoch" for w in [*vergleich.probleme, *was_wenn.probleme])
    eur = [n.abweichung_eur for n in vergleich.naeherungen if n.abweichung_eur is not None]
    return basis.model_copy(update={
        "empfehlungen": basis.empfehlungen + hoch,
        "schaetzung_abweichung_eur": round(sum(eur), 2) if eur else basis.schaetzung_abweichung_eur,
    })


def ergaenze_berichte(bericht: Pruefbericht, db: Any = _SEAM) -> Pruefbericht:
    """Additive: returns the report with B5 fields; on any failure the report is returned unchanged.

    An existing B1 `zusammenfassung` is recomputed on the three-report grouping."""
    try:
        teile = erstelle_berichte(bericht.lv, bericht.findings, db)
        if bericht.zusammenfassung is not None:
            try:
                teile["zusammenfassung"] = zusammenfassung_mit_berichten(
                    bericht.findings, teile["berichte"],
                    n_positionen=len(bericht.lv.positionen),
                    modell=bericht.zusammenfassung.bewertungsmodell)
            except Exception:
                log.exception("B1 summary on the B5 grouping failed; previous summary kept")
        return bericht.model_copy(update=teile)
    except Exception:
        log.exception("B5 reports failed; review report returned without them")
        return bericht

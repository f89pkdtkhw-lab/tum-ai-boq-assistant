"""Norm check, part 1 (N1): collect German standard references and look them up.

Bonus feature "norm check" (Normpruefung), purely additive. The N1 part only
collects references and builds a norm list; it creates **no** `Finding`. The N2
part at the end of this module turns register hits into hint findings and offers
the guarded hook `pruefe_normen_sicher()` for `pruefen()`, which also carries the
N3 key-value findings.

1. `extrahiere_normverweise(lv)` finds references such as "ATV DIN 18300 (2012-09)",
   "DIN EN1092-1" or "DIN 1045 Teil 2" in the short and long text of each position
   and normalises them ("DIN EN 1092-1", "DIN 1045-2", edition "2012-09"). Blanket
   references without a number ("nach DIN", "nach einschlägigen Normen") are
   collected with `pauschal=True`. "DIN A4" and numbers with fewer than three
   digits are ignored.
2. `lade_register(path)` loads and validates the curated register
   `data/normen/register.json` (metadata only, never standard text).
3. `normenliste(lv, register)` lists every referenced norm with its register
   status; norms missing from the register get `nicht_im_register` (no claim).

Normalisation rules (transparent assumptions of this tool):
- Plain DIN numbers 18299–18459 are the VOB/C ATVs, so "DIN 18300" and
  "ATV DIN 18300" both become "ATV DIN 18300".
- "VDE 0100" alone becomes "DIN VDE 0100"; a "(VDE …)" designation directly after
  another reference is the same document and is not counted again.
- The family (`familie`) is the designation without part and suffix:
  "DIN EN 1991-1-4/NA" -> "DIN EN 1991".
- Only the first number of an enumeration is read ("DIN 18300, 18320" -> DIN 18300).

The switch `NORMPRUEFUNG` (default on; `0`, `off`, `false`, `no` = off) is read by
`normpruefung_aktiv()`; callers decide what "off" skips.
"""
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Literal

from ..modelle import LV, Finding

ROOT = Path(__file__).resolve().parents[3]
REGISTER_PFAD = ROOT / "data" / "normen" / "register.json"

STATUS = ("gueltig", "zurueckgezogen", "teilweise_ersetzt", "unklar")
NICHT_IM_REGISTER = "nicht_im_register"
AUS_WERTE = {"0", "off", "false", "no"}

# VOB/C ATV numbers (DIN 18299 general rules up to DIN 18459 demolition).
ATV_BEREICH = range(18299, 18460)

_S = r"\s"  # also line breaks: long texts wrap inside designations
_WORT_SEP = rf"(?:{_S}+|{_S}*-{_S}*)"
_JAHR = r"(?:19|20)\d{2}"
_MONAT = r"(?:0[1-9]|1[0-2])"
_REIHE = r"EN(?:{sep}ISO|{sep}IEC)?|ISO|IEC|VDE|SPEC|V".format(sep=_WORT_SEP)

NORM_MUSTER = re.compile(
    rf"""
    (?<![A-Za-z0-9ÄÖÜäöüß])
    (?:(?P<atv>ATV){_WORT_SEP})?
    (?:
        DIN(?:{_WORT_SEP}?(?P<reihe>{_REIHE})(?![A-Za-z]))?
      | (?P<vde>VDE)
    )
    {_S}*-?{_S}*
    (?P<nummer>\d{{3,}}|\d{{1,2}}[ \u00a0]\d{{3}})(?![\d.,]\d)
    (?P<teile>(?:-\d{{1,3}}(?!\d))*)
    (?:{_S}*,?{_S}*Teil{_S}*(?P<teil_wort>\d{{1,3}})(?!\d))?
    (?P<zusatz>/(?:NA|A\d{{1,2}})(?![A-Za-z0-9]))?
    (?:
        {_S}*:{_S}*(?P<j1>{_JAHR})(?:-(?P<m1>{_MONAT}))?(?!\d)
      | {_S}*\({_S}*(?:Ausgabe{_S}*|Ausg\.{_S}*)?(?P<j2>{_JAHR})(?:-(?P<m2>{_MONAT}))?{_S}*\)
      | {_S}*,?{_S}*(?:Ausgabe|Ausg\.){_S}*(?P<j3>{_JAHR})(?:-(?P<m3>{_MONAT}))?(?!\d)
      | (?:{_S}+|-)(?P<j4>{_JAHR})-(?P<m4>{_MONAT})(?!\d)
    )?
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Blanket references without a standard number.
PAUSCHAL_MUSTER = re.compile(
    rf"""
        (?i:einschlägig|einschlaegig|gültig|gueltig|geltend|anerkannt)\w*{_S}+
        (?:DIN(?:{_S}*-?{_S}*(?:Norm(?:en)?|Vorschrift(?:en)?))?|Norm(?:en)?)\b(?!{_S}*-?{_S}*(?:[A-Z]{_S}*)*\d)
      | \bDIN{_S}*-?{_S}*Norm(?:en)?\b(?!{_S}*-?{_S}*\d)
      | (?i:\b(?:nach|gemäß|gemaess|gem\.|laut|lt\.|entsprechend|siehe))\s+DIN\b
        (?!{_S}*-?{_S}*(?:(?:EN|ISO|IEC|VDE|SPEC|[A-Z]){_S}*-?{_S}*)*\d)
    """,
    re.VERBOSE,
)


@dataclass(frozen=True)
class NormVerweis:
    """One standard reference in one text field of one position."""
    norm_id: str | None  # normalised designation incl. part, e.g. "DIN 1045-2"; None if blanket
    familie: str | None  # designation without part/suffix, e.g. "DIN 1045"
    teil: str | None  # e.g. "-2" or "-1-4"
    ausgabe: str | None  # edition "2012-09" or year "2012"
    oz: str
    feld: Literal["kurztext", "langtext"]
    roh: str  # matched text as written
    pauschal: bool = False


@dataclass(frozen=True)
class RegisterEintrag:
    norm_id: str
    familie: str
    titel: str
    status: str
    aktuelle_ausgabe: str | None
    ersetzt_durch: list[str]
    gewerke: list[str]
    kalkulationsrelevant: bool
    kennwerte: list[str]
    quelle: dict
    geprueft: bool
    hinweis: str
    kennwert_regeln: tuple = ()  # N3: structured key values (`Kennwert`) from the same JSON list


@dataclass
class Register:
    stand: str
    eintraege: list[RegisterEintrag] = field(default_factory=list)

    def __post_init__(self):
        self._nach_id = {e.norm_id: e for e in self.eintraege}

    def suche(self, norm_id: str, familie: str | None = None) -> RegisterEintrag | None:
        """Exact designation (incl. part) first, then the family-level entry."""
        if norm_id in self._nach_id:
            return self._nach_id[norm_id]
        if familie and familie in self._nach_id:
            return self._nach_id[familie]
        return None


def normpruefung_aktiv() -> bool:
    """Environment switch NORMPRUEFUNG: default on; 0/off/false/no switch it off."""
    return os.environ.get("NORMPRUEFUNG", "").strip().lower() not in AUS_WERTE


def _normalisiere(treffer: re.Match) -> tuple[str, str, str | None, str | None]:
    nummer = re.sub(r"\s", "", treffer["nummer"])  # old spelling "DIN 18 300"
    if treffer["vde"]:
        praefix = "DIN VDE"
    elif treffer["reihe"]:
        praefix = "DIN " + re.sub(rf"{_WORT_SEP}", " ", treffer["reihe"]).upper()
    elif treffer["atv"] or int(nummer) in ATV_BEREICH:
        praefix = "ATV DIN"
    else:
        praefix = "DIN"
    teil = treffer["teile"] or ""
    if treffer["teil_wort"]:
        teil += "-" + treffer["teil_wort"]
    zusatz = (treffer["zusatz"] or "").upper()
    familie = f"{praefix} {nummer}"
    norm_id = familie + teil + zusatz
    jahr = treffer["j1"] or treffer["j2"] or treffer["j3"] or treffer["j4"]
    monat = treffer["m1"] or treffer["m2"] or treffer["m3"] or treffer["m4"]
    ausgabe = f"{jahr}-{monat}" if jahr and monat else jahr
    return norm_id, familie, teil or None, ausgabe


def _verweise_im_text(text: str, oz: str, feld: str) -> list[NormVerweis]:
    verweise = []
    letztes_ende = None
    for treffer in NORM_MUSTER.finditer(text):
        davor = text[letztes_ende:treffer.start()].strip() if letztes_ende is not None else None
        letztes_ende = treffer.end()
        if treffer["vde"] and davor == "(":
            continue  # "DIN EN 61643-11 (VDE 0675-6-11)": same document, counted once
        norm_id, familie, teil, ausgabe = _normalisiere(treffer)
        verweise.append(NormVerweis(norm_id, familie, teil, ausgabe, oz, feld, treffer.group(0).strip()))
    for treffer in PAUSCHAL_MUSTER.finditer(text):
        verweise.append(NormVerweis(None, None, None, None, oz, feld, treffer.group(0).strip(), pauschal=True))
    return verweise


def extrahiere_normverweise(lv: LV) -> list[NormVerweis]:
    """All standard references in kurztext and langtext, in position order."""
    verweise = []
    for position in lv.positionen:
        verweise += _verweise_im_text(position.kurztext, position.oz, "kurztext")
        verweise += _verweise_im_text(position.langtext, position.oz, "langtext")
    return verweise


def _pruefe_eintrag(roh: dict, index: int) -> RegisterEintrag:
    name = roh.get("norm_id", f"entry {index}") if isinstance(roh, dict) else f"entry {index}"
    if not isinstance(roh, dict):
        raise ValueError(f"Norm register: {name} is not an object.")
    pflicht = {
        "norm_id": str, "familie": str, "titel": str, "status": str, "ersetzt_durch": list,
        "gewerke": list, "kalkulationsrelevant": bool, "kennwerte": list, "quelle": dict,
        "geprueft": bool, "hinweis": str,
    }
    for schluessel, typ in pflicht.items():
        if not isinstance(roh.get(schluessel), typ):
            raise ValueError(f"Norm register: {name} needs '{schluessel}' of type {typ.__name__}.")
    unbekannt = set(roh) - set(pflicht) - {"aktuelle_ausgabe"}
    if unbekannt:
        raise ValueError(f"Norm register: {name} has unknown fields {sorted(unbekannt)}.")
    if roh["status"] not in STATUS:
        raise ValueError(f"Norm register: {name} has unknown status '{roh['status']}' (allowed: {', '.join(STATUS)}).")
    ausgabe = roh.get("aktuelle_ausgabe")
    if ausgabe is not None and not (isinstance(ausgabe, str) and re.fullmatch(rf"{_JAHR}(?:-{_MONAT})?", ausgabe)):
        raise ValueError(f"Norm register: {name} has an invalid 'aktuelle_ausgabe' (YYYY-MM or null).")
    for liste in ("ersetzt_durch", "gewerke", "kennwerte"):
        if not all(isinstance(wert, str) and wert.strip() or liste == "kennwerte" and isinstance(wert, dict)
                   for wert in roh[liste]):
            raise ValueError(f"Norm register: {name} needs non-empty strings in '{liste}'.")
    quelle = roh["quelle"]
    url = quelle.get("url")
    if not (isinstance(url, str) and url.startswith(("https://", "http://"))):
        raise ValueError(f"Norm register: {name} needs 'quelle.url' (http/https).")
    try:
        date.fromisoformat(quelle.get("abgerufen", ""))
    except (TypeError, ValueError):
        raise ValueError(f"Norm register: {name} needs 'quelle.abgerufen' as YYYY-MM-DD.") from None
    # The designation must survive our own normalisation, otherwise lookups would never match.
    gelesen = [t for t in NORM_MUSTER.finditer(roh["norm_id"])]
    if len(gelesen) != 1 or gelesen[0].group(0).strip() != roh["norm_id"]:
        raise ValueError(f"Norm register: '{roh['norm_id']}' is not a single standard designation.")
    norm_id, familie, _, _ = _normalisiere(gelesen[0])
    if (norm_id, familie) != (roh["norm_id"], roh["familie"]):
        raise ValueError(
            f"Norm register: '{roh['norm_id']}' must be written as '{norm_id}' with family '{familie}'."
        )
    kennwerte = [w for w in roh["kennwerte"] if isinstance(w, str)]
    regeln = tuple(_pruefe_kennwert(w, name) for w in roh["kennwerte"] if isinstance(w, dict))
    return RegisterEintrag(**{**roh, "aktuelle_ausgabe": ausgabe, "kennwerte": kennwerte, "kennwert_regeln": regeln})


def lade_register(path: str | Path | None = None) -> Register:
    """Load and validate the curated register; raises ValueError on invalid content."""
    daten = json.loads(Path(path or REGISTER_PFAD).read_text(encoding="utf-8"))
    if not isinstance(daten, dict) or not isinstance(daten.get("stand"), str) or not isinstance(daten.get("eintraege"), list):
        raise ValueError("Norm register: needs 'stand' (string) and 'eintraege' (list).")
    eintraege = [_pruefe_eintrag(roh, i) for i, roh in enumerate(daten["eintraege"])]
    doppelt = sorted({e.norm_id for e in eintraege if [x.norm_id for x in eintraege].count(e.norm_id) > 1})
    if doppelt:
        raise ValueError(f"Norm register: duplicate entries {doppelt}.")
    return Register(stand=daten["stand"], eintraege=eintraege)


def normenliste(lv: LV, register: Register) -> list[dict]:
    """One row per referenced norm (first occurrence order); blanket references are not listed.

    Rows: {norm_id, status, ersetzt_durch, anzahl, oz[]}. Norms missing from the register
    get status `nicht_im_register` and no replacement: the tool makes no claim about them.
    """
    zeilen: dict[str, dict] = {}
    for verweis in extrahiere_normverweise(lv):
        if verweis.pauschal:
            continue
        zeile = zeilen.get(verweis.norm_id)
        if zeile is None:
            eintrag = register.suche(verweis.norm_id, verweis.familie)
            zeile = zeilen[verweis.norm_id] = {
                "norm_id": verweis.norm_id,
                "status": eintrag.status if eintrag else NICHT_IM_REGISTER,
                "ersetzt_durch": list(eintrag.ersetzt_durch) if eintrag else [],
                "anzahl": 0,
                "oz": [],
            }
        zeile["anzahl"] += 1
        if verweis.oz not in zeile["oz"]:
            zeile["oz"].append(verweis.oz)
    return list(zeilen.values())


# ---------------------------------------------------------------------------
# Norm check, part 3 (N3, issue #82): key-value comparison, assumption or bidder question.
#
# 1. `pruefe_kennwerte(lv, register)` compares the concrete strength class of a position with
#    the structured register key values (`kennwerte` objects) of a `gueltig` register entry.
#    First rule: exposure class -> minimum strength class. Designations are read with the
#    existing patterns of `regeln.py` (imported, not copied). Code NORM_KENNWERT_ABWEICHUNG.
# 2. `entscheide(...)` turns a finding into a visible, approval-required assumption only for a
#    deterministic register rule of a person-checked entry (`geprueft: true`) on a normal
#    position with known quantity and unit; everything else is a bidder question.
# 3. `annahme_note(...)` writes that assumption as a Note (step "standards"); no euro amount
#    unless an estimator-approved unit price is supplied. `euro_wirkung` stays None.
# 4. `register_als_quellen(verweise, register)` turns cited register key values into
#    `SourceRecord`s for the existing Note 2 logic (`build_specification_context` ->
#    `standards_note`), so unverified entries stay priority 4 (hint only).
# `pruefe_kennwerte_sicher(lv)` is the guarded entry point: switch NORMPRUEFUNG, try/except.
# ---------------------------------------------------------------------------
import logging
from collections.abc import Iterable

from ..ai.step_api import Evidence, Note, Requirement, SourceRecord, SourceScope, UnitPrice
from ..modelle import Finding, Position
from .regeln import BEZEICHNUNG_MUSTER, _bezeichnung_beton, _bezeichnung_exposition

NORM_KENNWERT_ABWEICHUNG = "NORM_KENNWERT_ABWEICHUNG"
KEIN_NORMGUTACHTEN = ("Hint, not a standards expert opinion (kein Normgutachten); contractual validity "
                      "is decided by a person (VOB/B § 1 (2)).")
ANNAHME_PRAEFIX = "Assumption – approval required"
# Parameters whose deviation means extra work or a higher class (assumption allowed when checked).
HOEHERE_KLASSE_PARAMETER = {"min_strength_class"}
KENNWERT_PARAMETER = HOEHERE_KLASSE_PARAMETER
_FESTIGKEIT = re.compile(r"C(\d{1,3})/(\d{1,3})")
_EXPOSITION = re.compile(r"X[CDFASM]\d")


@dataclass(frozen=True)
class Kennwert:
    """One structured register key value, e.g. min_strength_class for XC4 = C25/30."""
    parameter: str
    bedingung: str
    value: str
    fundstelle: str  # where the value is stated, incl. edition uncertainty
    quelle: dict  # {url, abgerufen}


@dataclass(frozen=True)
class KennwertTreffer:
    oz: str
    gegeben: str  # stated strength class
    bedingung: str  # exposure class that sets the requirement
    eintrag: RegisterEintrag
    kennwert: Kennwert


def _pruefe_kennwert(roh: dict, name: str) -> Kennwert:
    pflicht = {"parameter": str, "bedingung": str, "value": str, "fundstelle": str, "quelle": dict}
    for schluessel, typ in pflicht.items():
        if not (isinstance(roh.get(schluessel), typ) and roh[schluessel]):
            raise ValueError(f"Norm register: {name} key value needs '{schluessel}' of type {typ.__name__}.")
    unbekannt = set(roh) - set(pflicht)
    if unbekannt:
        raise ValueError(f"Norm register: {name} key value has unknown fields {sorted(unbekannt)}.")
    if roh["parameter"] not in KENNWERT_PARAMETER:
        raise ValueError(f"Norm register: {name} key value has unknown parameter '{roh['parameter']}'.")
    if not _EXPOSITION.fullmatch(roh["bedingung"]) or not _FESTIGKEIT.fullmatch(roh["value"]):
        raise ValueError(f"Norm register: {name} key value needs an exposure class (e.g. XC4) and a "
                         "strength class (e.g. C25/30).")
    url = roh["quelle"].get("url")
    if not (isinstance(url, str) and url.startswith("https://")):
        raise ValueError(f"Norm register: {name} key value needs 'quelle.url' (https).")
    try:
        date.fromisoformat(roh["quelle"].get("abgerufen", ""))
    except (TypeError, ValueError):
        raise ValueError(f"Norm register: {name} key value needs 'quelle.abgerufen' as YYYY-MM-DD.") from None
    return Kennwert(**roh)


def _festigkeit(klasse: str) -> tuple[int, int]:
    treffer = _FESTIGKEIT.fullmatch(klasse)
    return int(treffer[1]), int(treffer[2])


def _klassen(position: Position) -> tuple[list[str], list[str]]:
    """Normal-weight strength classes and exposure classes stated in short and long text."""
    text = f"{position.kurztext}\n{position.langtext}"
    beton, exposition = [], []
    for muster, deuten in BEZEICHNUNG_MUSTER:
        if deuten is _bezeichnung_beton:
            beton += [deuten(m)[1] for m in muster.finditer(text)]
        elif deuten is _bezeichnung_exposition:
            exposition += [deuten(m)[1] for m in muster.finditer(text)]
    beton = [k for k in dict.fromkeys(beton) if _FESTIGKEIT.fullmatch(k)]  # LC (lightweight) not covered
    return beton, list(dict.fromkeys(exposition))


def _kennwert_treffer(position: Position, register: Register) -> KennwertTreffer | None:
    """The strictest applicable key value when every stated strength class is below it."""
    beton, exposition = _klassen(position)
    if not beton or not exposition:
        return None
    regeln = [(e, k) for e in register.eintraege if e.status == "gueltig" for k in e.kennwert_regeln
              if k.parameter == "min_strength_class" and k.bedingung in exposition]
    if not regeln:
        return None
    eintrag, kennwert = max(regeln, key=lambda ek: _festigkeit(ek[1].value))
    gegeben = max(beton, key=_festigkeit)
    if _festigkeit(gegeben) >= _festigkeit(kennwert.value):
        return None
    return KennwertTreffer(position.oz, gegeben, kennwert.bedingung, eintrag, kennwert)


def _quellenangabe(treffer: KennwertTreffer) -> str:
    k, e = treffer.kennwert, treffer.eintrag
    status = "checked by a person" if e.geprueft else "not yet checked by a person (geprueft: false)"
    return (f"norm register {e.norm_id}, key value {k.parameter} {k.bedingung} = {k.value} ({k.fundstelle}); "
            f"{k.quelle['url']}, retrieved {k.quelle['abgerufen']}; register entry {status}")


def pruefe_kennwerte(lv: LV, register: Register) -> list[Finding]:
    """One NORM_KENNWERT_ABWEICHUNG finding per position whose strength class is below the
    register key value for its exposure class. The bidder question is the `vorschlag`."""
    findings = []
    for position in lv.positionen:
        treffer = _kennwert_treffer(position, register)
        if treffer is None:
            continue
        k, quelle = treffer.kennwert, _quellenangabe(treffer)
        findings.append(Finding(
            id=f"{NORM_KENNWERT_ABWEICHUNG}:{position.oz}", oz=position.oz, kategorie="risiko", schwere="hoch",
            titel=f"Strength class {treffer.gegeben} below register key value {k.value} for {k.bedingung}",
            begruendung=(f"OZ {position.oz} states {treffer.gegeben} together with exposure class {k.bedingung}; "
                         f"the norm register lists at least {k.value} for {k.bedingung}. Source: {quelle}. "
                         f"{KEIN_NORMGUTACHTEN}"),
            vorschlag=(f"Bidder question (Bieterfrage): for OZ {position.oz} the LV specifies {treffer.gegeben} "
                       f"with exposure class {k.bedingung}, while the norm register lists at least {k.value}. "
                       f"Which strength class is to be priced? Source: {k.quelle['url']}, retrieved "
                       f"{k.quelle['abgerufen']}. {KEIN_NORMGUTACHTEN}"),
            quelle="regel", regel_id=NORM_KENNWERT_ABWEICHUNG, euro_wirkung=None,
        ))
    return findings


def entscheide(finding: Finding, register: Register, position: Position) -> Literal["annahme", "rueckfrage"]:
    """Assumption only for a deterministic, person-checked register rule on a normal position with
    known quantity and unit whose effect is a higher class; everything else is a bidder question."""
    if finding.regel_id != NORM_KENNWERT_ABWEICHUNG or finding.quelle != "regel" or finding.oz != position.oz:
        return "rueckfrage"
    treffer = _kennwert_treffer(position, register)
    if treffer is None or not treffer.eintrag.geprueft:
        return "rueckfrage"
    if not (position.menge and position.menge > 0 and (position.einheit or "").strip()):
        return "rueckfrage"
    if position.typ != "normal" or treffer.kennwert.parameter not in HOEHERE_KLASSE_PARAMETER:
        return "rueckfrage"  # optional/alternative/lump-sum items: contractual question
    return "annahme"


def _zahl(wert: float) -> str:
    return f"{wert:g}" if float(wert) != int(wert) else str(int(wert))


def annahme_note(finding: Finding, register: Register, position: Position,
                 preis: UnitPrice | None = None) -> Note | None:
    """The visible, approval-required assumption for `finding`, or None for a bidder question.

    A euro amount appears only with an estimator-approved unit price for the same unit; the
    original estimate and the finding's `euro_wirkung` are never changed."""
    if entscheide(finding, register, position) != "annahme":
        return None
    treffer = _kennwert_treffer(position, register)
    k, menge, einheit = treffer.kennwert, _zahl(position.menge), position.einheit.strip()
    delta = _festigkeit(k.value)[0] - _festigkeit(treffer.gegeben)[0]
    annahme = (f"{ANNAHME_PRAEFIX}: for {menge} {einheit} (OZ {position.oz}) {k.value} instead of "
               f"{treffer.gegeben} is assumed ({k.bedingung}).")
    text = (f"{annahme} Class delta: {treffer.gegeben} -> {k.value} (f_ck +{delta} N/mm²) for {menge} {einheit}. "
            f"Source: {_quellenangabe(treffer)}.")
    evidence = [Evidence(reference_id=f"NORM:{treffer.eintrag.norm_id}:{k.parameter}:{k.bedingung}",
                         oz=position.oz, source="norm_register", detail=_quellenangabe(treffer))]
    if (preis is not None and preis.approved and preis.value is not None
            and preis.per_unit.strip() == einheit):
        betrag = round(preis.value * position.menge, 2)
        text += (f" Estimator-approved supplement ({preis.source}): {_zahl(preis.value)} {preis.currency}/{einheit}"
                 f" × {menge} {einheit} = {_zahl(betrag)} {preis.currency}, also an assumption requiring approval.")
        evidence.append(Evidence(reference_id="unit_price", oz=position.oz, source=preis.source,
                                 detail=f"approved {_zahl(preis.value)} {preis.currency}/{einheit}"))
    else:
        text += " No euro amount without an estimator-approved price."
    text += f" The original estimate stays unchanged; manual review required. {KEIN_NORMGUTACHTEN}"
    return Note(id=f"NormAssumption:{position.oz}", step="standards", oz=position.oz, source="rule",
                placeholder=False, text=text, manual_review=True, evidence=evidence, unit=einheit,
                assumption=annahme, uncertainty=k.fundstelle, approval_required=True)


def register_als_quellen(verweise: Iterable[NormVerweis], register: Register,
                         lv: LV | None = None) -> list[SourceRecord]:
    """SourceRecords for the structured key values of `gueltig` register entries, scoped to the
    OZ that cite the entry (with `lv`, only OZ stating the key value's exposure class).
    `verified` is the register's `geprueft`, so unchecked entries stay priority 4 in Note 2."""
    zitiert: dict[str, tuple[RegisterEintrag, list[str]]] = {}
    for verweis in verweise:
        if verweis.pauschal:
            continue
        eintrag = register.suche(verweis.norm_id, verweis.familie)
        if eintrag is None or eintrag.status != "gueltig" or not eintrag.kennwert_regeln:
            continue
        oz_liste = zitiert.setdefault(eintrag.norm_id, (eintrag, []))[1]
        if verweis.oz not in oz_liste:
            oz_liste.append(verweis.oz)
    expositionen = {p.oz: _klassen(p)[1] for p in lv.positionen} if lv is not None else None
    quellen = []
    for eintrag, oz_liste in zitiert.values():
        for k in eintrag.kennwert_regeln:
            scope = [oz for oz in oz_liste if expositionen is None or k.bedingung in expositionen.get(oz, [])]
            if not scope:
                continue
            quellen.append(SourceRecord(
                spec_id=f"NORM:{eintrag.norm_id}:{k.parameter}:{k.bedingung}", source_type="internet",
                category="german_standard", title=eintrag.titel, source_url=k.quelle["url"],
                document_ref=eintrag.norm_id, location=k.fundstelle, as_of=k.quelle["abgerufen"],
                scope=SourceScope(oz=scope, description=f"exposure class {k.bedingung}"),
                text=f"Register key value {k.parameter} {k.bedingung} = {k.value}. {KEIN_NORMGUTACHTEN}",
                requirement=Requirement(parameter=f"concrete strength f_ck,cyl for exposure class {k.bedingung}",
                                        comparator="min", value=float(_festigkeit(k.value)[0]), unit="N/mm²"),
                verified=eintrag.geprueft,
            ))
    return quellen


def pruefe_kennwerte_sicher(lv: LV, register: Register | None = None,
                            preise: dict[str, UnitPrice] | None = None) -> tuple[list[Finding], list[Note]]:
    """Guarded N3 entry point: nothing runs with NORMPRUEFUNG off; any error is logged and the
    check is skipped (empty result), so the normal report is never affected."""
    if not normpruefung_aktiv():
        return [], []
    try:
        register = register or lade_register()
        positionen = {p.oz: p for p in lv.positionen}
        findings = pruefe_kennwerte(lv, register)
        notes = [note for f in findings
                 if (note := annahme_note(f, register, positionen[f.oz], (preise or {}).get(f.oz)))]
        return findings, notes
    except Exception:
        logging.getLogger(__name__).exception("Norm check N3 (key values) failed; check skipped.")
        return [], []


# ---------------------------------------------------------------------------
# Norm check, part 2 (N2): status findings and the guarded hook for pruefen().
#
# Deterministic, no model, no internet. Only register entries with an assessed
# status (gueltig, zurueckgezogen, teilweise_ersetzt) create findings; entries
# with status `unklar` and norms missing from the register never do. Every
# finding is a hint with a ready-to-copy bidder question, cites its source and
# carries the HINWEIS note. `euro_wirkung` always stays None.
#
# Transparent assumptions of this part:
# - A reference without part and edition (e.g. "DIN 1045", "DIN 4094") is unclear
#   when the register holds at least one assessed part entry of that family
#   (NORM_AUSGABE_UNKLAR); the family-level entry itself is `unklar`, so it never
#   yields NORM_ZURUECKGEZOGEN.
# - The Bodenklassen -> Homogenbereiche switch is a VOB/C fact; its source is the
#   register entry of ATV DIN 18300, also for ATV DIN 18301 and ATV DIN 18319.
# - A replacement counts as present when the LV cites it exactly or cites a part
#   of a replacement family ("DIN EN 1996-1-1" for "DIN EN 1996").
# - Blanket references are grouped per LV section (title path, else the OZ
#   prefix), one finding per section.
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)

HINWEIS = KEIN_NORMGUTACHTEN  # same note as N3
BEWERTET = ("gueltig", "zurueckgezogen", "teilweise_ersetzt")  # register status values that may create findings
STATUS_TEXT = {"gueltig": "valid", "zurueckgezogen": "withdrawn", "teilweise_ersetzt": "partly replaced"}
BODEN_ATVS = ("ATV DIN 18300", "ATV DIN 18301", "ATV DIN 18319")
BODEN_QUELLE = "ATV DIN 18300"
_BODENKLASSE = re.compile(r"bodenklasse", re.IGNORECASE)
_HOMOGENBEREICH = re.compile(r"homogenbereich", re.IGNORECASE)


class _Ids:
    """Finding ids `CODE:oz`, with `:2`, `:3`, … when a code repeats on the same OZ."""

    def __init__(self):
        self._gesehen: dict[str, int] = {}

    def __call__(self, code: str, oz: str) -> str:
        basis = f"{code}:{oz}"
        anzahl = self._gesehen[basis] = self._gesehen.get(basis, 0) + 1
        return basis if anzahl == 1 else f"{basis}:{anzahl}"


def _bewerteter_eintrag(register: Register, norm_id: str, familie: str | None) -> RegisterEintrag | None:
    eintrag = register.suche(norm_id, familie)
    return eintrag if eintrag and eintrag.status in BEWERTET else None


def _ausgabe_tupel(ausgabe: str) -> tuple[int, int | None]:
    jahr, _, monat = ausgabe.partition("-")
    return int(jahr), int(monat) if monat else None


def _aelter(zitiert: str, aktuell: str) -> bool:
    """True when the cited edition is clearly older ("2012" vs "2019-09"; same year without month is not)."""
    (j1, m1), (j2, m2) = _ausgabe_tupel(zitiert), _ausgabe_tupel(aktuell)
    if j1 != j2:
        return j1 < j2
    return m1 is not None and m2 is not None and m1 < m2


def _quelle(eintrag: RegisterEintrag) -> str:
    return (f"Source: norm register entry {eintrag.norm_id}, {eintrag.quelle['url']} "
            f"(retrieved {eintrag.quelle['abgerufen']}).")


def _begruendung(text: str, *eintraege: RegisterEintrag) -> str:
    teile = [text]
    for eintrag in eintraege:
        if eintrag.ersetzt_durch:
            teile.append(f"Register: {eintrag.norm_id} is replaced by {', '.join(eintrag.ersetzt_durch)}.")
        if eintrag.hinweis:
            teile.append(f"Register note: {eintrag.hinweis.rstrip('.')}.")
        teile.append(_quelle(eintrag))
    teile.append(HINWEIS)
    return " ".join(teile)


def _finding(id_: str, oz: str, kategorie: str, schwere: str, titel: str, begruendung: str, vorschlag: str,
             regel_id: str) -> Finding:
    return Finding(id=id_, oz=oz, kategorie=kategorie, schwere=schwere, titel=titel, begruendung=begruendung,
                   vorschlag=vorschlag, quelle="regel", regel_id=regel_id, euro_wirkung=None)


def _abschnitt(oz: str, positionen: dict) -> str:
    position = positionen.get(oz)
    if position is not None and position.titel_pfad:
        return " / ".join(position.titel_pfad)
    return oz.rpartition(".")[0] or oz


def _status_findings(gruppen: dict, register: Register, ids: _Ids) -> list[Finding]:
    """NORM_ZURUECKGEZOGEN, NORM_AUSGABE_VERALTET and NORM_AUSGABE_UNKLAR, once per OZ and norm."""
    findings = []
    for (oz, norm_id), verweise in gruppen.items():
        familie = verweise[0].familie
        ausgaben = sorted({v.ausgabe for v in verweise if v.ausgabe}, key=_ausgabe_tupel)
        eintrag = _bewerteter_eintrag(register, norm_id, familie)
        if eintrag and eintrag.status == "zurueckgezogen":
            ersatz = " / ".join(eintrag.ersetzt_durch)
            frage = f"Does {ersatz} apply instead?" if ersatz else "Which standard applies instead?"
            findings.append(_finding(
                ids("NORM_ZURUECKGEZOGEN", oz), oz, "risiko", "hoch" if eintrag.kalkulationsrelevant else "mittel",
                f"Withdrawn standard referenced: {norm_id}",
                _begruendung(f"The item refers to {norm_id}; the norm register lists it as withdrawn.", eintrag),
                f"OZ {oz}: The item refers to {norm_id} (withdrawn). {frage} Please confirm.",
                "NORM_ZURUECKGEZOGEN",
            ))
        elif eintrag and eintrag.aktuelle_ausgabe and ausgaben and _aelter(ausgaben[0], eintrag.aktuelle_ausgabe):
            findings.append(_finding(
                ids("NORM_AUSGABE_VERALTET", oz), oz, "risiko", "mittel",
                f"Outdated edition referenced: {norm_id} ({ausgaben[0]})",
                _begruendung(
                    f"The item refers to {norm_id} edition {ausgaben[0]}; the norm register lists edition "
                    f"{eintrag.aktuelle_ausgabe} as current.", eintrag,
                ),
                f"OZ {oz}: The item refers to {norm_id} edition {ausgaben[0]}; the current edition is "
                f"{eintrag.aktuelle_ausgabe}. Which edition applies? Please confirm.",
                "NORM_AUSGABE_VERALTET",
            ))
        elif eintrag is None and verweise[0].teil is None and not ausgaben:
            teile = [e for e in register.eintraege
                     if e.familie == familie and e.norm_id != norm_id and e.status in BEWERTET]
            if not teile:
                continue
            liste = ", ".join(f"{e.norm_id} ({STATUS_TEXT[e.status]})" for e in teile)
            findings.append(_finding(
                ids("NORM_AUSGABE_UNKLAR", oz), oz, "risiko", "niedrig",
                f"Standard referenced without part or edition: {norm_id}",
                _begruendung(
                    f"The item refers to {norm_id} without part or edition; the norm register lists these "
                    f"parts of the family: {liste}.", *teile,
                ),
                f"OZ {oz}: The item refers to {norm_id} without part or edition. Which part and edition apply "
                f"(register: {liste})? Please confirm.",
                "NORM_AUSGABE_UNKLAR",
            ))
    return findings


def _bodenklassen_findings(verweise: list[NormVerweis], register: Register, lv: LV, ids: _Ids) -> list[Finding]:
    quelle = _bewerteter_eintrag(register, BODEN_QUELLE, BODEN_QUELLE)
    if quelle is None:
        return []
    findings = []
    for position in lv.positionen:
        atvs = list(dict.fromkeys(v.familie for v in verweise if v.oz == position.oz and v.familie in BODEN_ATVS))
        text = f"{position.kurztext}\n{position.langtext}"
        if not atvs or not _BODENKLASSE.search(text) or _HOMOGENBEREICH.search(text):
            continue
        kennwerte = " ".join(k.rstrip(".") + "." for k in quelle.kennwerte)
        findings.append(_finding(
            ids("NORM_BODENKLASSEN", position.oz), position.oz, "nachtrag", "hoch",
            f"Bodenklassen without Homogenbereiche ({', '.join(atvs)})",
            _begruendung(
                f"The item describes the soil in Bodenklassen together with {', '.join(atvs)} and names no "
                f"Homogenbereich. {kennwerte} Nachtrag potential is possible if the classification does not "
                f"match the current VOB/C; this does not establish an entitlement to additional payment.", quelle,
            ),
            f"OZ {position.oz}: The item describes the soil in Bodenklassen ({', '.join(atvs)}). Please provide "
            f"the Homogenbereich description per current VOB/C, or confirm which edition and classification apply.",
            "NORM_BODENKLASSEN",
        ))
    return findings


def _passt_zu_ersatz(verweis: NormVerweis, ersatz: str) -> bool:
    return verweis.norm_id == ersatz or verweis.familie == ersatz


def _doppelt_findings(gruppen: dict, register: Register, ids: _Ids) -> list[Finding]:
    """NORM_DOPPELT_ALT_NEU once per withdrawn norm whose replacement is also cited in the LV."""
    alle = [v for verweise in gruppen.values() for v in verweise]
    findings, gesehen = [], set()
    for (oz, norm_id), verweise in gruppen.items():
        eintrag = _bewerteter_eintrag(register, norm_id, verweise[0].familie)
        if norm_id in gesehen or not eintrag or eintrag.status != "zurueckgezogen":
            continue
        gesehen.add(norm_id)
        neu = [(e, v) for e in eintrag.ersetzt_durch for v in alle if _passt_zu_ersatz(v, e)]
        if not neu:
            continue
        zitiert = ", ".join(dict.fromkeys(f"{v.norm_id} (OZ {v.oz})" for _, v in neu))
        alt_oz = ", ".join(dict.fromkeys(v.oz for v in alle if v.norm_id == norm_id))
        findings.append(_finding(
            ids("NORM_DOPPELT_ALT_NEU", oz), oz, "risiko", "mittel",
            f"Withdrawn standard and its replacement both referenced: {norm_id}",
            _begruendung(
                f"The LV refers to the withdrawn {norm_id} (OZ {alt_oz}) and to its replacement {zitiert}.", eintrag,
            ),
            f"OZ {alt_oz}: The LV refers to {norm_id} (withdrawn) and elsewhere to {zitiert}. Which standard "
            f"applies to these items? Please confirm.",
            "NORM_DOPPELT_ALT_NEU",
        ))
    return findings


def _ohne_referenz_findings(verweise: list[NormVerweis], positionen: dict, ids: _Ids) -> list[Finding]:
    """NORM_OHNE_REFERENZ: one grouped finding per LV section, not one per line."""
    abschnitte: dict[str, list[str]] = {}
    for verweis in verweise:
        if verweis.pauschal:
            oz_liste = abschnitte.setdefault(_abschnitt(verweis.oz, positionen), [])
            if verweis.oz not in oz_liste:
                oz_liste.append(verweis.oz)
    findings = []
    for abschnitt, oz_liste in abschnitte.items():
        oz_text = ", ".join(oz_liste)
        findings.append(_finding(
            ids("NORM_OHNE_REFERENZ", oz_liste[0]), oz_liste[0], "risiko", "niedrig",
            f"Blanket standard reference without number in section {abschnitt} ({len(oz_liste)} items)",
            f"OZ {oz_text} refer to standards in general terms (e.g. \"nach DIN\") without naming a number or "
            f"edition, so the agreed standard cannot be determined from the LV. Source: LV text of these items "
            f"(no register entry applies; cf. VOB/A § 7 (1): clear and exhaustive description). {HINWEIS}",
            f"OZ {oz_text}: The items refer to standards without a number (e.g. \"nach DIN\"). Which standards "
            f"and editions apply? Please name them.",
            "NORM_OHNE_REFERENZ",
        ))
    return findings


def pruefe_status(verweise: list[NormVerweis], register: Register, lv: LV | None = None) -> list[Finding]:
    """Deterministic status findings for the collected references, in position order.

    `lv` is optional: with it, NORM_BODENKLASSEN reads the position texts and blanket references are
    grouped by title path; without it, NORM_BODENKLASSEN is skipped and grouping uses the OZ prefix.
    """
    ids = _Ids()
    positionen = {p.oz: p for p in lv.positionen} if lv else {}
    gruppen: dict[tuple[str, str], list[NormVerweis]] = {}
    for verweis in verweise:
        if not verweis.pauschal:
            gruppen.setdefault((verweis.oz, verweis.norm_id), []).append(verweis)
    findings = _status_findings(gruppen, register, ids)
    if lv is not None:
        findings += _bodenklassen_findings(verweise, register, lv, ids)
    findings += _doppelt_findings(gruppen, register, ids)
    findings += _ohne_referenz_findings(verweise, positionen, ids)
    reihenfolge = {oz: i for i, oz in enumerate(dict.fromkeys(
        [p.oz for p in lv.positionen] if lv else [v.oz for v in verweise]
    ))}
    return sorted(findings, key=lambda f: reihenfolge.get(f.oz, len(reihenfolge)))  # stable: rule order per OZ


def pruefe_normen(lv: LV, register: Register | None = None) -> list[Finding]:
    """N1 extraction + curated register + `pruefe_status` (N2), followed by the N3 key-value
    findings of `pruefe_kennwerte`, in position order (stable: N2 before N3 on the same OZ)."""
    register = register or lade_register()
    findings = pruefe_status(extrahiere_normverweise(lv), register, lv) + pruefe_kennwerte(lv, register)
    reihenfolge = {oz: i for i, oz in enumerate(dict.fromkeys(p.oz for p in lv.positionen))}
    return sorted(findings, key=lambda f: reihenfolge.get(f.oz, len(reihenfolge)))


def pruefe_normen_sicher(lv: LV) -> list[Finding]:
    """Hook for `pruefen()` (N2 + N3 findings): [] when NORMPRUEFUNG is off or the norm check fails
    (the error is logged)."""
    if not normpruefung_aktiv():
        return []
    try:
        return pruefe_normen(lv)
    except Exception:
        logger.exception("Norm check failed; the report is returned without norm findings.")
        return []

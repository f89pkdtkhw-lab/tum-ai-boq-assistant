"""Norm check, part 1 (N1): collect German standard references and look them up.

Bonus feature "norm check" (Normpruefung), purely additive. This module only
collects references and builds a norm list; it creates **no** `Finding` and is
not wired into `pruefen()` (that is part 2, N2).

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
import os
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Literal

from ..modelle import LV

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
        if not all(isinstance(wert, str) and wert.strip() for wert in roh[liste]):
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
    return RegisterEintrag(**{**roh, "aktuelle_ausgabe": ausgabe})


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

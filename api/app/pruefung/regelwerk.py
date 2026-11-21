"""Regulation document import (B3, issue #96): norm references and key values from an uploaded file.

The user can upload a regulation document (PDF, TXT or MD) next to the bill. This module reads it
**deterministically** (no model, no internet) and returns a `Regelwerk`:

1. Text: TXT/MD are decoded as UTF-8 (cp1252 as fallback, with a warning); PDF pages are read with
   pdfplumber's text layer, never with OCR. Unreadable, scanned or binary files raise `ValueError`
   (the route turns that into 422, like `/api/lv/import`).
2. Norm references: every paragraph (lines up to the next blank line) is read with the existing
   `extrahiere_normverweise()` of `normen.py`; one entry per designation, first occurrence wins.
   Blanket references ("nach DIN") are not listed.
3. Key values (`kennwerte`), only from lines that state an explicit comparison:
   - minimum concrete strength class per exposure class, e.g. "Expositionsklasse XC4: mindestens
     C30/37" -> `kennwert="min_strength_class"`, `bedingung="XC4"`, `wert="C30/37"`. Each exposure
     class takes the next strength class on the same line (normal-weight classes only, as in
     `normen._klassen`); the word "mindestens" (or "min.", "≥", "at least", "Mindest…") must appear
     in the same paragraph.
   - a number with a unit after "mindestens/min./≥" or "höchstens/max./≤", e.g. "Betondeckung
     c_nom mindestens 40 mm" -> `kennwert="Betondeckung c_nom"`, `vergleich="min"`, `wert="40"`,
     `einheit="mm"`. The name is the text of the same clause before the comparison (at most five
     words). Decimal commas become dots.
   The key value's `norm` is the last norm reference read so far in the document (same line or
   earlier), or None. `fundstelle` is "<file>, page <p>, line <l>" (page only for PDF).
4. Warnings: no references, no key values, fallback encoding.

`/api/lv/analyse` feeds the result into check 1 through B2's `normen.vorgaben_aus_regelwerk()`:
the uploaded `min_strength_class` values become user-specified sources for the lower/bigger cases
(`NORM_KENNWERT_ABWEICHUNG` / `NORM_KENNWERT_HOEHER`), citing the uploaded file and line.
"""
import hashlib
import io
import re
from dataclasses import dataclass
from pathlib import PurePath

from ..modelle import LV, Position, Regelwerk, RegelwerkKennwert, RegelwerkNormverweis
from .normen import extrahiere_normverweise


ENDUNGEN = (".pdf", ".txt", ".md")
MIN_STRENGTH_CLASS = "min_strength_class"

_MIN = r"(?<!\w)(?:mindestens|mind\.|min\.|minimal|minimum|at\s+least)|≥|>="
_MAX = r"(?<!\w)(?:höchstens|hoechstens|max\.|maximal|maximum|at\s+most)|≤|<="
_MIN_HINWEIS = re.compile(rf"(?:{_MIN})|\bmindest\w*|\bminimum\b", re.IGNORECASE)
_EINHEIT = r"N/mm²|N/mm2|kN/m²|kN/m2|kN/m|W/\(m²K\)|W/\(m2K\)|W/\(mK\)|kg/m³|kg/m3|MPa|mm|cm|m²|m2|m|dB|°C|%"
_ZAHL_MUSTER = re.compile(
    rf"(?P<vgl>{_MIN}|{_MAX})\s*(?P<zahl>\d+(?:[.,]\d+)?)\s*(?P<einheit>{_EINHEIT})(?![\w/²³])",
    re.IGNORECASE,
)
_MAX_MUSTER = re.compile(rf"^(?:{_MAX})$", re.IGNORECASE)
_KLAUSEL_GRENZE = re.compile(r"[.;!?()\[\]]\s|,\s|\s[-–]\s")
_FUELLWOERTER = {"ist", "sind", "beträgt", "betraegt", "muss", "müssen", "muessen", "soll", "sollen", "von", "mit",
                 "eine", "einer", "einen", "ein", "der", "die", "das", "den", "is", "are", "must", "be", "of", "the",
                 "a", "an", "shall", "betragen", "haben", "hat", "zu", "werden", "wird"}
_NUMMERIERUNG = re.compile(r"^\s*(?:\d+(?:\.\d+)*\.?|[-*•#]+|[a-z]\))\s+")
_EXPOSITION = re.compile(r"\bX[CDFASM]\d\b")
_KLASSE = re.compile(r"(?<![A-Za-z])C\d{1,3}/\d{1,3}\b")  # normal-weight only, like normen._FESTIGKEIT


@dataclass(frozen=True)
class _Zeile:
    seite: int | None  # PDF page, None for text files
    nummer: int  # line number on the page (text files: in the file)
    text: str


def _fundstelle(dateiname: str, zeile: _Zeile) -> str:
    seite = f", page {zeile.seite}" if zeile.seite is not None else ""
    return f"{dateiname}{seite}, line {zeile.nummer}"


def _pdf_zeilen(inhalt: bytes) -> list[_Zeile]:
    import pdfplumber
    from ..lv.pdf import _open_error  # same readable messages as the bill PDF import
    try:
        pdf = pdfplumber.open(io.BytesIO(inhalt))
    except Exception as exc:
        raise ValueError(_open_error(exc)) from None
    zeilen: list[_Zeile] = []
    with pdf:
        try:
            seiten = list(pdf.pages)
            for nummer, seite in enumerate(seiten, 1):
                text = seite.extract_text() or ""
                seite.close()
                zeilen += [_Zeile(nummer, i, z) for i, z in enumerate(text.splitlines(), 1)]
        except Exception as exc:
            raise ValueError(_open_error(exc)) from None
    if not seiten:
        raise ValueError("The PDF has no pages.")
    if not any(z.text.strip() for z in zeilen):
        raise ValueError("The PDF contains no extractable text; it is probably scanned or image-only. "
                         "OCR is not supported. Please upload a text PDF, TXT or MD file.")
    return zeilen


def _text_zeilen(inhalt: bytes, warnungen: list[str]) -> list[_Zeile]:
    if b"\x00" in inhalt:
        raise ValueError("The file is not a text file. Please upload a PDF, TXT or MD file.")
    try:
        text = inhalt.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = inhalt.decode("cp1252", errors="replace")
        warnungen.append("The file is not UTF-8; it was read as Windows-1252. Please check special characters.")
    if not text.strip():
        raise ValueError("The uploaded file contains no text.")
    return [_Zeile(None, i, z) for i, z in enumerate(text.splitlines(), 1)]


def lese_zeilen(dateiname: str, inhalt: bytes, warnungen: list[str] | None = None) -> list[_Zeile]:
    """All text lines of the document; ValueError for unsupported, unreadable or textless files."""
    endung = PurePath(dateiname).suffix.lower()
    if endung not in ENDUNGEN:
        raise ValueError("Unsupported format for a regulation document. Allowed: PDF, TXT, MD.")
    if endung == ".pdf":
        return _pdf_zeilen(inhalt)
    return _text_zeilen(inhalt, warnungen if warnungen is not None else [])


def _absaetze(zeilen: list[_Zeile]) -> list[list[_Zeile]]:
    """Consecutive non-blank lines of one page form a paragraph."""
    absaetze, aktuell = [], []
    for zeile in zeilen:
        if aktuell and (not zeile.text.strip() or zeile.seite != aktuell[-1].seite):
            absaetze.append(aktuell)
            aktuell = []
        if zeile.text.strip():
            aktuell.append(zeile)
    if aktuell:
        absaetze.append(aktuell)
    return absaetze


def _normen_im_text(text: str) -> list:
    """Norm references of one text via the existing N1 extractor (pseudo position, no blanket refs)."""
    lv = LV(name="Regelwerk", quelle="upload", positionen=[Position(oz="-", langtext=text)])
    return [v for v in extrahiere_normverweise(lv) if not v.pauschal]


def _festigkeit_kennwerte(zeile: str) -> list[tuple[str, str]]:
    """(exposure class, strength class) pairs of one line: each exposure class takes the next strength
    class after it (before the next exposure class), else the only strength class of the line."""
    klassen = [(m.start(), m.group(0)) for m in _KLASSE.finditer(zeile)]
    if not klassen:
        return []
    expositionen = [(m.start(), m.group(0)) for m in _EXPOSITION.finditer(zeile)]
    paare = []
    for i, (start, exposition) in enumerate(expositionen):
        ende = expositionen[i + 1][0] if i + 1 < len(expositionen) else len(zeile)
        danach = [k for pos, k in klassen if start < pos < ende]
        if danach:
            paare.append((exposition, danach[0]))
        elif len(set(k for _, k in klassen)) == 1:
            paare.append((exposition, klassen[0][1]))
    return list(dict.fromkeys(paare))


def _kennwert_name(davor: str) -> str | None:
    klausel = _KLAUSEL_GRENZE.split(davor)[-1]
    klausel = _NUMMERIERUNG.sub("", klausel.replace(":", " ").replace("=", " "))
    woerter = [w for w in klausel.split() if w.lower() not in _FUELLWOERTER]
    while woerter and woerter[-1].lower() in _FUELLWOERTER:
        woerter.pop()
    name = " ".join(woerter[-5:]).strip(" ,;:")
    return name or None


def _zahl_kennwerte(zeile: str) -> list[tuple[str, str, str, str]]:
    """(name, comparison, value, unit) for "<name> mindestens/höchstens <number> <unit>"."""
    werte = []
    for treffer in _ZAHL_MUSTER.finditer(zeile):
        name = _kennwert_name(zeile[:treffer.start()])
        if name is None:
            continue
        vergleich = "max" if _MAX_MUSTER.fullmatch(treffer["vgl"].strip()) else "min"
        werte.append((name, vergleich, treffer["zahl"].replace(",", "."), treffer["einheit"]))
    return werte


def importiere_regelwerk(dateiname: str, inhalt: bytes) -> Regelwerk:
    """Read the uploaded regulation document; ValueError (-> 422) for unusable files."""
    if not inhalt:
        raise ValueError("The uploaded file is empty.")
    name = PurePath(dateiname or "").name or "regelwerk"
    warnungen: list[str] = []
    zeilen = lese_zeilen(name, inhalt, warnungen)
    normverweise: dict[str, RegelwerkNormverweis] = {}
    kennwerte: list[RegelwerkKennwert] = []
    letzte_norm: str | None = None
    for absatz in _absaetze(zeilen):
        absatz_text = "\n".join(z.text for z in absatz)
        min_im_absatz = bool(_MIN_HINWEIS.search(absatz_text))
        for zeile in absatz:
            fundstelle = _fundstelle(name, zeile)
            normen_der_zeile = _normen_im_text(zeile.text)
            for verweis in normen_der_zeile:
                normverweise.setdefault(verweis.norm_id, RegelwerkNormverweis(
                    norm_id=verweis.norm_id, ausgabe=verweis.ausgabe, fundstelle=fundstelle))
            if normen_der_zeile:
                letzte_norm = normen_der_zeile[-1].norm_id
            if min_im_absatz:
                for exposition, klasse in _festigkeit_kennwerte(zeile.text):
                    kennwerte.append(RegelwerkKennwert(
                        norm=letzte_norm, kennwert=MIN_STRENGTH_CLASS, wert=klasse, einheit=None,
                        fundstelle=fundstelle, bedingung=exposition, vergleich="min"))
            for kennwert, vergleich, wert, einheit in _zahl_kennwerte(zeile.text):
                kennwerte.append(RegelwerkKennwert(
                    norm=letzte_norm, kennwert=kennwert, wert=wert, einheit=einheit,
                    fundstelle=fundstelle, vergleich=vergleich))
        for verweis in _normen_im_text(absatz_text):  # designations wrapped across lines
            normverweise.setdefault(verweis.norm_id, RegelwerkNormverweis(
                norm_id=verweis.norm_id, ausgabe=verweis.ausgabe, fundstelle=_fundstelle(name, absatz[0])))
    if not normverweise:
        warnungen.append("No standard references (DIN, EN, ISO, VDE) were recognised in the document.")
    if not kennwerte:
        warnungen.append("No key values with an explicit minimum or maximum were recognised; check 1 uses "
                         "the curated norm register only.")
    return Regelwerk(id="rw-" + hashlib.sha256(inhalt).hexdigest()[:12], dateiname=name,
                     normverweise=list(normverweise.values()), kennwerte=kennwerte, warnungen=warnungen)


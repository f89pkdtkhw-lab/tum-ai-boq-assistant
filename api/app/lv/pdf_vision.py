"""#192: AI vision fallback for PDF pages the text parser could not read completely.

When the text parser (``pdf.py``) leaves items without quantity, unit or short text, or recognizes no item at all,
the affected pages are rendered as JPEG and sent to Claude (``llm.complete(..., bilder=...)``) together with the
following page, because a quantity line often continues after a page break. The answer only fills gaps, and every
value is checked against the text layer of those pages, so nothing is invented:

* the OZ must be printed on the page, otherwise the item is dropped;
* a quantity must be a number printed on the page or the following page, a unit must be printed there, a short
  text must appear in the page text (spaces ignored); anything else becomes null;
* ``bedarf`` / ``alternativ`` need a Bedarf/Eventual or Wahl/Alternativ marker in the page text.

Values the parser read stay unchanged. Items filled or found this way carry ``quelle.ki = True`` so the report can
show that the AI read them. Mock/offline mode (no Claude key), ``PDF_VISION=off``, scanned pages without a text
layer, or any model error: the parser result is returned unchanged (or its error raised), so tests and the demo
stay offline and free. Brakes: ``PDF_VISION_MAX_SEITEN`` pages (default 20), ``PDF_VISION_TIMEOUT`` seconds in
total (default 90), ``PDF_VISION_PARALLEL`` requests at once (default 4).
"""
from __future__ import annotations

import contextvars
import io
import logging
import os
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout, as_completed
from dataclasses import dataclass
from pathlib import Path

from ..ai import llm
from ..ai.sprache import ohne_hinweis
from ..modelle import LV, Position, PositionQuelle

log = logging.getLogger(__name__)

AUFLOESUNG = 110          # dpi; an A4 page becomes about 910 x 1290 px, well inside the image limits
JPEG_QUALITAET = 80
MAX_TOKENS = 8000
TYPEN = {"normal", "bedarf", "alternativ", "zulage", "pauschal", "stundenlohn"}
PAUSCHAL = {"psch", "psch.", "pauschal", "pausch", "pausch.", "pschl", "pschl."}

SYSTEM = (
    "You read pages of German construction bills of quantities (Leistungsverzeichnis, LV) from images. "
    "Copy item numbers, texts, quantities and units exactly as printed; never translate, never invent an item "
    "or a number. Answer with JSON only."
)


def _zahl_env(name: str, standard: float) -> float:
    try:
        wert = float(os.environ.get(name, ""))
    except ValueError:
        return standard
    return wert if wert > 0 else standard


def aktiv() -> bool:
    """True when a real Claude call would be made and the fallback is not switched off."""
    if os.environ.get("PDF_VISION", "on").strip().lower() in ("off", "0", "false", "aus", "no"):
        return False
    zustand = llm.status()
    return not zustand["mock"] and zustand["provider"] == "anthropic"


def luecke(position: Position) -> bool:
    """An item the parser could not read completely."""
    return position.menge is None or not position.einheit or not position.kurztext.strip() \
        or position.kurztext.lstrip().startswith("***")


def ergaenze(dateiname: str, inhalt: bytes, lv: LV | None, fehler: ValueError | None = None) -> LV:
    """Fill parser gaps from the page images; without a usable model the parser result (or error) is returned."""
    if lv is not None and not any(luecke(p) for p in lv.positionen):
        return lv
    if not aktiv():
        return _oder_fehler(lv, fehler)
    try:
        ergebnis = _ergaenze(dateiname, inhalt, lv)
    except Exception:  # the import must never fail because of the optional AI step
        log.exception("PDF vision fallback failed for %s", dateiname)
        ergebnis = None
    return ergebnis if ergebnis is not None else _oder_fehler(lv, fehler)


def _oder_fehler(lv: LV | None, fehler: ValueError | None) -> LV:
    if lv is not None:
        return lv
    raise fehler or ValueError("No BoQ positions were recognized in the PDF.")


# ---------- pages ----------

@dataclass
class _Seite:
    nummer: int
    text: str                 # text layer of this page
    folgetext: str            # text layer of the following page ("" on the last page)
    bilder: list[bytes]       # JPEG of this page, plus the following page when it exists
    groesse: tuple[float, float]
    bekannte_oz: list[str]


def _jpeg(page) -> bytes:
    bild = page.to_image(resolution=AUFLOESUNG).original.convert("RGB")
    puffer = io.BytesIO()
    bild.save(puffer, format="JPEG", quality=JPEG_QUALITAET)
    return puffer.getvalue()


def _seiten(inhalt: bytes, lv: LV | None) -> list[_Seite]:
    import pdfplumber
    maximal = int(_zahl_env("PDF_VISION_MAX_SEITEN", 20))
    with pdfplumber.open(io.BytesIO(inhalt)) as pdf:
        anzahl = len(pdf.pages)
        texte: dict[int, str] = {}

        def text(nummer: int) -> str:
            if nummer not in texte:
                texte[nummer] = (pdf.pages[nummer - 1].extract_text() or "") if 1 <= nummer <= anzahl else ""
            return texte[nummer]

        if lv is None:
            kandidaten = [n for n in range(1, anzahl + 1) if text(n).strip()]
        else:
            zaehler = Counter(p.quelle.seite for p in lv.positionen if luecke(p) and p.quelle and p.quelle.seite)
            kandidaten = [n for n, _ in zaehler.most_common() if text(n).strip()]
        auswahl = sorted(kandidaten[:maximal])
        bekannte: dict[int, list[str]] = {}
        for p in (lv.positionen if lv is not None else []):
            if p.quelle and p.quelle.seite:
                bekannte.setdefault(p.quelle.seite, []).append(p.oz)
        seiten = []
        for nummer in auswahl:
            page = pdf.pages[nummer - 1]
            bilder = [_jpeg(page)] + ([_jpeg(pdf.pages[nummer])] if nummer < anzahl else [])
            seiten.append(_Seite(nummer, text(nummer), text(nummer + 1), bilder,
                                 (round(float(page.width), 1), round(float(page.height), 1)),
                                 bekannte.get(nummer, [])))
        return seiten


def _prompt(seite: _Seite) -> str:
    folge = " Image 2 is the following page." if len(seite.bilder) > 1 else ""
    bekannt = (f" Item numbers the text layer found on this page: {', '.join(seite.bekannte_oz[:80])}."
               if seite.bekannte_oz else "")
    return (
        f"Image 1 is page {seite.nummer} of a German bill of quantities (LV).{folge} List every BoQ item "
        f"(Position) whose item number (OZ) is printed on page {seite.nummer} (image 1), in reading order. When the "
        "quantity line of an item continues on the following page, take quantity and unit from image 2. Skip "
        "section titles, sums (Summe, Übertrag), headers, footers and preliminary remarks." + bekannt +
        ' Answer with JSON only: {"positionen": [{"oz": "OZ as printed", "kurztext": "first title line of the '
        'item as printed", "menge": number or null, "einheit": "unit as printed or null", "typ": "normal|bedarf|'
        'alternativ|pauschal|zulage|stundenlohn"}]}. Use null for anything not printed. typ is bedarf for a '
        "Bedarfs-/Eventualposition, alternativ for a Wahl-/Alternativposition, otherwise normal."
    )


def _frage(seite: _Seite, timeout: float) -> list[dict]:
    with ohne_hinweis():  # #196: printed texts are copied, never translated
        antwort = llm.complete(_prompt(seite), system=SYSTEM, max_tokens=MAX_TOKENS, timeout=timeout,
                               bilder=seite.bilder)
    daten = llm.parse_json(antwort.text)
    eintraege = daten.get("positionen") if isinstance(daten, dict) else daten
    return [e for e in eintraege if isinstance(e, dict)] if isinstance(eintraege, list) else []


# ---------- validation against the text layer ----------

def _oz_norm(text: str) -> str:
    return str(text).strip().rstrip(".:")


def _woerter(text: str) -> list[str]:
    return text.split()


_ZAHL = re.compile(r"^(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d+))?")


def _zahlen(text: str) -> set[float]:
    """Every number printed in the text (German format), also split digits such as ``9 4,000`` and ``4Jahre``."""
    werte = set()
    woerter = _woerter(text)
    for i, wort in enumerate(woerter):
        kandidaten = [wort]
        if wort.isdigit() and i + 1 < len(woerter):
            kandidaten.append(wort + woerter[i + 1])
        for k in kandidaten:
            treffer = _ZAHL.match(k)
            if treffer:
                ganz = treffer.group(1).replace(".", "")
                werte.add(float(ganz + ("." + treffer.group(2) if treffer.group(2) else "")))
    return werte


def _gedruckt(wert: str, text: str) -> bool:
    return bool(re.search(r"(?<![A-Za-zÄÖÜäöüß])" + re.escape(wert) + r"(?![A-Za-zÄÖÜäöüß])", text, re.I))


def _gestaucht(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def _pruefe(eintrag: dict, seite: _Seite) -> dict | None:
    """The validated item, or None when its OZ is not printed on the page."""
    oz = _oz_norm(eintrag.get("oz") or "")
    if not oz or oz not in {_oz_norm(w) for w in _woerter(seite.text)}:
        return None
    beide = seite.text + "\n" + seite.folgetext
    menge = eintrag.get("menge")
    if isinstance(menge, str):
        try:
            menge = float(menge.replace(".", "").replace(",", "."))
        except ValueError:
            menge = None
    if not isinstance(menge, (int, float)) or isinstance(menge, bool) or \
            not any(abs(z - float(menge)) < 1e-6 for z in _zahlen(beide)):
        menge = None
    einheit = str(eintrag.get("einheit") or "").strip()
    if not einheit or len(einheit) > 12 or not _gedruckt(einheit, beide):
        einheit = None
    kurztext = re.sub(r"\s+", " ", str(eintrag.get("kurztext") or "")).strip()
    if len(kurztext) < 3 or kurztext.startswith("***") or _gestaucht(kurztext) not in _gestaucht(beide):
        kurztext = ""
    typ = str(eintrag.get("typ") or "normal").strip().lower()
    if typ not in TYPEN \
            or (typ == "bedarf" and not re.search(r"bedarf|eventual", seite.text, re.I)) \
            or (typ == "alternativ" and not re.search(r"wahl|alternativ", seite.text, re.I)) \
            or (typ == "pauschal" and (einheit or "").lower() not in PAUSCHAL):
        typ = "normal"
    return {"oz": oz, "menge": float(menge) if menge is not None else None, "einheit": einheit,
            "kurztext": kurztext, "typ": typ}


# ---------- merge ----------

def _ergaenze(dateiname: str, inhalt: bytes, lv: LV | None) -> LV | None:
    seiten = _seiten(inhalt, lv)
    if not seiten:
        return None
    gesamt = _zahl_env("PDF_VISION_TIMEOUT", 90)
    parallel = int(_zahl_env("PDF_VISION_PARALLEL", 4))
    antworten: dict[int, list[dict]] = {}
    pool = ThreadPoolExecutor(max_workers=min(parallel, len(seiten)), thread_name_prefix="pdf-vision")
    try:
        auftraege = {pool.submit(contextvars.copy_context().run, _frage, s, gesamt): s for s in seiten}
        try:
            for auftrag in as_completed(auftraege, timeout=gesamt + 1):
                seite = auftraege[auftrag]
                try:
                    roh = auftrag.result()
                except Exception as exc:  # one page failing keeps the others
                    log.warning("PDF vision: page %s failed: %s", seite.nummer, exc)
                    continue
                antworten[seite.nummer] = [g for g in (_pruefe(e, seite) for e in roh) if g is not None]
        except FutureTimeout:
            log.warning("PDF vision: total time limit of %ss reached; keeping the finished pages", gesamt)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    if not antworten:
        return None
    if lv is None:
        return _neues_lv(dateiname, seiten, antworten)
    return _fuelle(lv, antworten)


def _fuelle(lv: LV, antworten: dict[int, list[dict]]) -> LV:
    neu = list(lv.positionen)
    for seite, eintraege in antworten.items():
        for e in eintraege:
            index = next((i for i, p in enumerate(neu) if _oz_norm(p.oz) == e["oz"] and p.quelle
                          and p.quelle.seite == seite), None)
            if index is None:
                continue
            p, aenderung = neu[index], {}
            if p.menge is None and e["menge"] is not None:
                aenderung["menge"] = e["menge"]
            if not p.einheit and e["einheit"]:
                aenderung["einheit"] = e["einheit"]
            if (not p.kurztext.strip() or p.kurztext.lstrip().startswith("***")) and e["kurztext"]:
                aenderung["kurztext"] = e["kurztext"]
            if p.typ == "normal" and e["typ"] in ("bedarf", "alternativ", "pauschal"):
                aenderung["typ"] = e["typ"]
            if aenderung:
                aenderung["quelle"] = p.quelle.model_copy(update={"ki": True})
                neu[index] = p.model_copy(update=aenderung)
    return lv.model_copy(update={"positionen": neu})


def _neues_lv(dateiname: str, seiten: list[_Seite], antworten: dict[int, list[dict]]) -> LV | None:
    groesse = {s.nummer: s.groesse for s in seiten}
    positionen, gesehen = [], set()
    for seite in sorted(antworten):
        for e in antworten[seite]:
            if (seite, e["oz"]) in gesehen:
                continue
            gesehen.add((seite, e["oz"]))
            positionen.append(Position(oz=e["oz"], kurztext=e["kurztext"], menge=e["menge"], einheit=e["einheit"],
                                       typ=e["typ"],
                                       quelle=PositionQuelle(seite=seite, seite_groesse=groesse[seite], ki=True)))
    if not positionen:
        return None
    return LV(name=Path(dateiname).stem or "PDF BoQ", quelle=dateiname or "upload.pdf", positionen=positionen)

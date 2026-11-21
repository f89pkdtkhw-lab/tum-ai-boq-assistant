"""Excel BoQ import (#9): the model reads the sheet; there is no fixed column layout.

Flow:
1. Read the XLSX with the standard library (zipfile + XML; no Excel dependency). Every visible sheet
   becomes a list of rows of cell texts: shared/inline strings as written, numbers as stored,
   formulas only through their cached result. A formula without a cached result stays empty; it is
   never evaluated, so no number is invented. Hidden sheets are skipped.
2. Each sheet is rendered as semicolon CSV (first field = spreadsheet row number) and sent in bounded
   blocks (`MAX_ZEILEN_BLOCK` rows, `MAX_ZEICHEN_BLOCK` characters; the first rows of the sheet are
   repeated as header context) through `app.ai.llm.complete` with a strict JSON-output prompt.
3. Every answer is validated against the sheet before it becomes a `Position`:
   - the OZ must be a cell value of the cited row (otherwise the row is looked up by OZ, otherwise
     the item is dropped), so no item is invented; duplicate OZ on different rows stay separate;
   - quantity, EP and GP must be numbers present in the item's rows (the cited row up to the next
     item); anything else becomes null, never zero and never a computed value;
   - `typ` outside the contract becomes "normal".
4. Mock/offline mode (`llm.config()["mock"]`, the same switch as the rest of the app) makes no call:
   a deterministic header-based reader answers in the same JSON shape and passes the same
   validation, so tests and the demo run offline and free.

Errors (not an XLSX, no item numbers found, model unreachable or unreadable) raise ValueError with a
message the UI can show; `/api/lv/import` turns it into HTTP 422.
"""
import csv
import io
import json
import logging
import re
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

from ..ai import llm
from ..modelle import LV, Position, PositionQuelle

logger = logging.getLogger(__name__)

MAX_ENTPACKT = 50 * 1024 * 1024  # bytes per XML part after decompression (zip-bomb guard)
MAX_ZEILEN = 10_000              # non-empty rows over all sheets
MAX_ZEILEN_BLOCK = 40            # rows per model call
MAX_ZEICHEN_BLOCK = 12_000       # CSV characters per model call
KOPF_ZEILEN = 3                  # first non-empty rows of a sheet, repeated as context in later blocks
MAX_TOKENS = 8000
TYPEN = {"normal", "bedarf", "alternativ", "zulage", "pauschal", "stundenlohn"}

Client = Callable[..., object]  # (prompt, system=..., max_tokens=...) -> llm.Answer or str

_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_REL_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
_REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"
_ZELLE = re.compile(r"^([A-Z]+)(\d+)$")

SYSTEM = (
    "You extract bill-of-quantities items (German LV positions) from one block of a spreadsheet. "
    "Rows are semicolon-separated CSV; the first field of every row is its spreadsheet row number. "
    "There is no fixed column layout: work out the columns from the header rows and the content. "
    "Answer with JSON only, no prose: "
    '{"positionen": [{"zeile": 12, "oz": "01.02", "kurztext": "short text", "langtext": "long text", '
    '"menge": "2", "einheit": "m2", "ep": "12,50", "gp": "25,00", "typ": "normal", '
    '"titel_pfad": ["01 Earthworks"]}], "fehler": null}. '
    "Rules: one entry per item row, in row order; `zeile` is the row number of the item's OZ cell. "
    "Copy `oz` exactly as written in its cell. Keep items with the same OZ on different rows as separate "
    "entries. Copy quantity (`menge`), unit price (`ep`) and total price (`gp`) exactly as they appear in "
    "the cells; an empty, missing or non-numeric cell is null, never 0; never calculate a value (no "
    "quantity x price). Skip empty rows, header rows, section headings, sums, subtotals and notes, but use "
    "section headings (or a section/title column) for `titel_pfad`. `langtext` may join continuation rows "
    "below the item that have no OZ. `typ` is one of normal, bedarf (contingency/Eventual), alternativ "
    "(Wahl/alternative), zulage, pauschal (lump sum), stundenlohn (daywork); otherwise normal. "
    "Rows under 'Context' are only repeated headers: never return them. If the block has no item numbers "
    'at all, answer {"positionen": [], "fehler": "short reason"}.'
)


@dataclass
class Blatt:
    name: str
    zeilen: list[tuple[int, list[str]]]  # (row number, cell texts by column); empty rows removed


@dataclass
class Block:
    blatt: Blatt
    zeilen: list[tuple[int, list[str]]]
    kontext: list[tuple[int, list[str]]] = field(default_factory=list)
    titel_pfad: list[str] = field(default_factory=list)  # section path in effect at the block start


# ---------- reading the workbook ----------

def _xml(archiv: zipfile.ZipFile, name: str) -> ET.Element | None:
    try:
        info = archiv.getinfo(name)
    except KeyError:
        return None
    if info.file_size > MAX_ENTPACKT:
        raise ValueError("The Excel file is too large to import.")
    with archiv.open(info) as datei:
        daten = datei.read(MAX_ENTPACKT + 1)
    if len(daten) > MAX_ENTPACKT:
        raise ValueError("The Excel file is too large to import.")
    if b"<!DOCTYPE" in daten or b"<!ENTITY" in daten:
        raise ValueError("Excel files with DTDs or entities are not supported.")
    try:
        return ET.fromstring(daten)
    except ET.ParseError:
        raise ValueError("Invalid Excel file: a workbook part is damaged. Please save it again as .xlsx.") from None


def _text(element: ET.Element) -> str:
    """Visible text of a shared or inline string, including rich-text runs, without phonetic hints."""
    teile = []
    for kind in element:
        tag = kind.tag.rsplit("}", 1)[-1]
        if tag == "t":
            teile.append(kind.text or "")
        elif tag == "r":
            teile.extend(t.text or "" for t in kind.findall("m:t", _NS))
    return "".join(teile)


def _spalte(buchstaben: str) -> int:
    nummer = 0
    for zeichen in buchstaben:
        nummer = nummer * 26 + ord(zeichen) - 64
    return nummer - 1


def _zahl_text(wert: str) -> str:
    """A stored number without binary noise: '2.4999999999999996' -> '2.5', '25.0' -> '25'."""
    try:
        zahl = float(wert)
    except ValueError:
        return wert.strip()
    return format(zahl, ".15g")


def _zellwert(zelle: ET.Element, strings: list[str]) -> str:
    typ = zelle.get("t", "n")
    wert = zelle.find("m:v", _NS)
    if typ == "inlineStr":
        inline = zelle.find("m:is", _NS)
        return _text(inline) if inline is not None else ""
    if wert is None or wert.text is None:
        return ""  # includes formulas without a cached result: never evaluated
    if typ == "s":
        try:
            return strings[int(wert.text)]
        except (ValueError, IndexError):
            raise ValueError("Invalid Excel file: a text cell points to a missing string.") from None
    if typ == "b":
        return "TRUE" if wert.text.strip() == "1" else "FALSE"
    if typ == "e":
        return ""  # error values such as #DIV/0! carry no number
    if typ == "str":
        return wert.text
    return _zahl_text(wert.text)


def _ziel(target: str) -> str:
    target = target.lstrip("/")
    return target if target.startswith("xl/") else f"xl/{target}"


def lese_blaetter(inhalt: bytes) -> list[Blatt]:
    """All visible sheets in workbook order, with empty rows removed."""
    try:
        archiv = zipfile.ZipFile(io.BytesIO(inhalt))
    except (zipfile.BadZipFile, ValueError):
        raise ValueError("Invalid Excel file. Please upload an .xlsx workbook (Excel 2007 or later).") from None
    with archiv:
        mappe = _xml(archiv, "xl/workbook.xml")
        beziehungen = _xml(archiv, "xl/_rels/workbook.xml.rels")
        if mappe is None or beziehungen is None:
            raise ValueError("Invalid Excel file: no workbook found. Please upload an .xlsx workbook.")
        ziele = {rel.get("Id"): _ziel(rel.get("Target", "")) for rel in beziehungen.iter(f"{_REL_NS}Relationship")}
        geteilt = _xml(archiv, "xl/sharedStrings.xml")
        strings = [_text(si) for si in geteilt.findall("m:si", _NS)] if geteilt is not None else []
        blaetter, anzahl = [], 0
        for eintrag in mappe.iterfind("m:sheets/m:sheet", _NS):
            if eintrag.get("state") in ("hidden", "veryHidden"):
                continue
            blatt = _xml(archiv, ziele.get(eintrag.get(_REL_ID), ""))
            if blatt is None:
                continue
            zeilen = []
            for nummer, zeile in enumerate(blatt.iterfind("m:sheetData/m:row", _NS), start=1):
                nummer = int(zeile.get("r") or nummer)
                zellen: dict[int, str] = {}
                for position, zelle in enumerate(zeile.iterfind("m:c", _NS)):
                    treffer = _ZELLE.match(zelle.get("r", ""))
                    spalte = _spalte(treffer.group(1)) if treffer else position
                    zellen[spalte] = _zellwert(zelle, strings).strip()
                if any(zellen.values()):
                    breite = max(spalte for spalte, wert in zellen.items() if wert) + 1
                    zeilen.append((nummer, [zellen.get(spalte, "") for spalte in range(breite)]))
            anzahl += len(zeilen)
            if anzahl > MAX_ZEILEN:
                raise ValueError(f"The Excel file has more than {MAX_ZEILEN} filled rows; please split it.")
            if zeilen:
                blaetter.append(Blatt(eintrag.get("name") or f"Sheet {len(blaetter) + 1}", zeilen))
    if not blaetter:
        raise ValueError("The Excel file contains no filled cells.")
    return blaetter


# ---------- numbers ----------

def zahl(wert) -> float | None:
    """A number as written in a cell or model answer: '12,50', '1.234,56', '12.5', 2 -> float; else None."""
    if isinstance(wert, bool) or wert is None:
        return None
    if isinstance(wert, (int, float)):
        return float(wert) if wert == wert and abs(wert) != float("inf") else None
    if not isinstance(wert, str):
        return None
    text = re.sub(r"[\s '€]|EUR", "", wert)
    if not re.fullmatch(r"[+-]?(\d[\d.,]*)", text):
        return None
    if "," in text and "." in text:
        dezimal = "," if text.rfind(",") > text.rfind(".") else "."
        text = text.replace("." if dezimal == "," else ",", "").replace(",", ".")
    elif text.count(",") == 1:
        text = text.replace(",", ".")
    elif text.count(",") > 1 or text.count(".") > 1:
        text = text.replace(",", "").replace(".", "")
    try:
        return float(text)
    except ValueError:
        return None


def _gleich(a: float, b: float) -> bool:
    return abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))


# ---------- blocks and prompt ----------

def _bloecke(blatt: Blatt) -> list[Block]:
    kopf = blatt.zeilen[:KOPF_ZEILEN]
    bloecke, aktuell, zeichen = [], [], 0
    for zeile in blatt.zeilen:
        laenge = len(_csv([zeile]))
        if aktuell and (len(aktuell) >= MAX_ZEILEN_BLOCK or zeichen + laenge > MAX_ZEICHEN_BLOCK):
            bloecke.append(aktuell)
            aktuell, zeichen = [], 0
        aktuell.append(zeile)
        zeichen += laenge
    if aktuell:
        bloecke.append(aktuell)
    return [Block(blatt, zeilen, [] if i == 0 else [z for z in kopf if z[0] < zeilen[0][0]])
            for i, zeilen in enumerate(bloecke)]


def _csv(zeilen) -> str:
    puffer = io.StringIO()
    schreiber = csv.writer(puffer, delimiter=";", lineterminator="\n")
    for nummer, zellen in zeilen:
        schreiber.writerow([nummer] + [re.sub(r"\s*[\r\n]+\s*", " ", zelle)[:2000] for zelle in zellen])
    return puffer.getvalue()


def prompt(block: Block) -> str:
    von, bis = block.zeilen[0][0], block.zeilen[-1][0]
    teile = [f'Sheet "{block.blatt.name}", rows {von} to {bis}.']
    if block.titel_pfad:
        teile.append("Section path in effect at the start of this block: " + json.dumps(block.titel_pfad, ensure_ascii=False))
    if block.kontext:
        teile.append("Context (repeated header rows, never return them):\n" + _csv(block.kontext))
    teile.append("Rows:\n" + _csv(block.zeilen))
    return "\n\n".join(teile)


def _json(text: str):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[A-Za-z]*\s*|\s*```$", "", text)
    start, stop = text.find("{"), text.rfind("}")
    if start == -1 or stop <= start:
        return None
    try:
        return json.loads(text[start:stop + 1])
    except ValueError:
        return None


# ---------- deterministic offline reader (mock mode) ----------

def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9äöüß]", "", text.lower())


_KOEPFE = {
    "oz": ("oz", "ordnungszahl", "pos", "posnr", "position", "positionsnr", "positionsnummer", "nr", "itemno", "item"),
    "kurztext": ("kurztext", "bezeichnung", "beschreibung", "leistung", "leistungsbeschreibung", "text",
                 "shorttext", "description"),
    "langtext": ("langtext", "longtext", "langbeschreibung"),
    "menge": ("menge", "mengen", "qty", "quantity", "anzahl", "lvmenge"),
    "einheit": ("einheit", "eh", "me", "unit", "einh", "mengeneinheit"),
    "ep": ("ep", "einheitspreis", "unitprice", "preisjeeinheit", "epeur", "ep€"),
    "gp": ("gp", "gesamtpreis", "gesamtbetrag", "totalprice", "total", "gpeur", "gp€", "betrag"),
    "typ": ("typ", "art", "positionsart", "type", "kind"),
    "titel": ("titel", "abschnitt", "section", "gewerk", "bereich", "title", "titelpfad"),
}
_TYP_WORTE = {"bedarf": "bedarf", "bedarfsposition": "bedarf", "eventual": "bedarf", "eventualposition": "bedarf",
              "contingency": "bedarf", "alternativ": "alternativ", "alternative": "alternativ", "wahl": "alternativ",
              "wahlposition": "alternativ", "zulage": "zulage", "pauschal": "pauschal", "lumpsum": "pauschal",
              "stundenlohn": "stundenlohn", "stundenlohnarbeiten": "stundenlohn", "daywork": "stundenlohn",
              "normal": "normal", "normalposition": "normal"}
_TITEL_TYPEN = {"titel", "bereich", "abschnitt", "title", "section", "los", "gewerk"}
_SUMMEN = re.compile(r"^(summe|gesamt|total|übertrag|zwischensumme)", re.IGNORECASE)


def _kopf(blatt: Blatt) -> tuple[int, dict[str, int]] | None:
    """Header row number and column per field, found by header words (any order, any position)."""
    for nummer, zellen in blatt.zeilen[:20]:
        spalten: dict[str, int] = {}
        for spalte, zelle in enumerate(zellen):
            wort = _norm(zelle)
            for feld, namen in _KOEPFE.items():
                if feld not in spalten and wort in namen:
                    spalten[feld] = spalte
                    break
        if "oz" in spalten and len(spalten) >= 2:
            return nummer, spalten
    return None


def mock_antwort(block: Block) -> dict:
    """What the offline reader 'answers' for one block, in the model's JSON shape."""
    kopf = _kopf(block.blatt)
    if kopf is None:
        return {"positionen": [], "fehler": f'sheet "{block.blatt.name}" has no OZ column (item number); '
                                            "add a header such as 'OZ' or 'Pos.' above the items"}
    kopfzeile, spalten = kopf
    pfad, positionen = list(block.titel_pfad), []

    def zelle(zellen, feld):
        spalte = spalten.get(feld)
        return zellen[spalte] if spalte is not None and spalte < len(zellen) else ""

    zeilen = [(n, z) for n, z in block.zeilen if n > kopfzeile and zelle(z, "oz") and not _SUMMEN.match(zelle(z, "oz"))]
    for index, (nummer, zellen) in enumerate(zeilen):
        oz = zelle(zellen, "oz")
        typ_wort = _norm(zelle(zellen, "typ"))
        folgende = zelle(zeilen[index + 1][1], "oz") if index + 1 < len(zeilen) else ""
        ohne_werte = not any(zelle(zellen, f) for f in ("menge", "einheit", "ep", "gp"))
        if typ_wort in _TITEL_TYPEN or (ohne_werte and folgende.startswith(oz.rstrip(".") + ".")):
            # nested sections: keep the headings whose OZ is a prefix of this one ("01" above "01.02")
            pfad = [t for t in pfad if oz.startswith(t.split(" ", 1)[0].rstrip(".") + ".")]
            pfad.append(f"{oz} {zelle(zellen, 'kurztext')}".strip())
            continue
        titel = zelle(zellen, "titel")
        positionen.append({
            "zeile": nummer, "oz": oz, "kurztext": zelle(zellen, "kurztext"), "langtext": zelle(zellen, "langtext"),
            "menge": zelle(zellen, "menge") or None, "einheit": zelle(zellen, "einheit") or None,
            "ep": zelle(zellen, "ep") or None, "gp": zelle(zellen, "gp") or None,
            "typ": _TYP_WORTE.get(typ_wort, "normal"),
            "titel_pfad": [t.strip() for t in re.split(r"\s+[/>»]\s+", titel) if t.strip()] if titel else pfad,
        })
    return {"positionen": positionen, "fehler": None}


# ---------- validation against the sheet ----------

def _zahlen(zeilen) -> list[float]:
    return [wert for _, zellen in zeilen for zelle in zellen if (wert := zahl(zelle)) is not None]


def _pruefe(block: Block, antwort, verwendet: set[tuple[str, int]]) -> tuple[list[tuple[int, Position]], str | None]:
    """Model entries that are backed by the sheet, as (row, Position); invented values never pass."""
    if not isinstance(antwort, dict) or not isinstance(antwort.get("positionen", []), list):
        raise ValueError(f'The model returned no readable item list for sheet "{block.blatt.name}" '
                         f"rows {block.zeilen[0][0]} to {block.zeilen[-1][0]}. Please try the import again.")
    zeilen = dict(block.zeilen)
    reihenfolge = [nummer for nummer, _ in block.zeilen]
    belegt: list[tuple[int, dict]] = []
    for eintrag in antwort.get("positionen") or []:
        if not isinstance(eintrag, dict) or not isinstance(eintrag.get("oz"), (str, int, float)):
            continue
        oz = str(eintrag["oz"]).strip()
        zeile = eintrag.get("zeile")
        if not (isinstance(zeile, int) and oz and oz in zeilen.get(zeile, []) and (block.blatt.name, zeile) not in verwendet):
            zeile = next((n for n in reihenfolge if oz and oz in zeilen[n] and (block.blatt.name, n) not in verwendet), None)
        if zeile is None:
            logger.warning("Excel import: dropped item %r, its OZ is not in sheet %r.", oz, block.blatt.name)
            continue
        verwendet.add((block.blatt.name, zeile))
        belegt.append((zeile, eintrag | {"oz": oz}))
    belegt.sort(key=lambda paar: paar[0])
    ergebnis = []
    for index, (zeile, eintrag) in enumerate(belegt):
        ende = belegt[index + 1][0] if index + 1 < len(belegt) else reihenfolge[-1] + 1
        vorhanden = _zahlen((n, z) for n, z in block.zeilen if zeile <= n < ende)
        werte = {}
        for feld in ("menge", "ep", "gp"):
            wert = zahl(eintrag.get(feld))
            if wert is not None and not any(_gleich(wert, z) for z in vorhanden):
                logger.warning("Excel import: %s %r of OZ %s is not in the sheet; set to null.", feld, eintrag.get(feld), eintrag["oz"])
                wert = None
            werte[feld] = wert
        typ = eintrag.get("typ") if eintrag.get("typ") in TYPEN else "normal"
        pfad = eintrag.get("titel_pfad")
        pfad = [str(t).strip() for t in pfad if isinstance(t, (str, int, float)) and str(t).strip()] if isinstance(pfad, list) else []
        einheit = eintrag.get("einheit")
        einheit = str(einheit).strip()[:40] or None if isinstance(einheit, (str, int, float)) else None
        ergebnis.append((zeile, Position(
            oz=eintrag["oz"], kurztext=_kurz(eintrag.get("kurztext")), langtext=_kurz(eintrag.get("langtext"), 20_000),
            menge=werte["menge"], einheit=einheit, ep=werte["ep"], gp=werte["gp"], typ=typ, titel_pfad=pfad)))
    fehler = antwort.get("fehler")
    return ergebnis, (str(fehler)[:300] if fehler else None)


def _kurz(wert, laenge=2000) -> str:
    return str(wert).strip()[:laenge] if isinstance(wert, (str, int, float)) else ""


# ---------- entry point ----------

def _modell(client: Client | None) -> Client | None:
    """The call to use; None means mock/offline mode (deterministic reader, no call)."""
    if client is not None:
        return client
    try:
        offline = llm.config()["mock"]
    except llm.LLMError as exc:
        raise ValueError(f"Excel import needs the model, but it is misconfigured: {exc}") from None
    return None if offline else llm.complete


def _frage(aufruf: Client, block: Block):
    try:
        with llm.sprache.ohne_hinweis():  # #196: copy the sheet texts, never translate them
            antwort = aufruf(prompt(block), system=SYSTEM, max_tokens=MAX_TOKENS)
    except llm.LLMError as exc:
        raise ValueError(f"Excel import via the model failed: {exc}") from None
    text = antwort.text if isinstance(antwort, llm.Answer) else antwort
    return _json(text) if isinstance(text, str) else None


def importiere(dateiname: str, inhalt: bytes, client: Client | None = None) -> LV:
    """Excel BoQ as `LV`. `client` replaces the model call (tests); None = configured model or mock."""
    blaetter = lese_blaetter(inhalt)
    aufruf = _modell(client)
    positionen: list[tuple[int, int, Position]] = []
    fehler: list[str] = []
    verwendet: set[tuple[str, int]] = set()
    for index, blatt in enumerate(blaetter):
        pfad: list[str] = []
        for block in _bloecke(blatt):
            block.titel_pfad = pfad
            antwort = mock_antwort(block) if aufruf is None else _frage(aufruf, block)
            gefunden, grund = _pruefe(block, antwort, verwendet)
            if grund and not gefunden:
                fehler.append(grund)
            # #170: sheet and row of the item, so a finding can name its place in the workbook.
            positionen.extend((index, zeile, position.model_copy(update={"quelle": PositionQuelle(blatt=blatt.name, zeile=zeile)}))
                              for zeile, position in gefunden)
            if gefunden:
                pfad = gefunden[-1][1].titel_pfad
    if not positionen:
        grund = fehler[0] if fehler else "no rows with an item number (OZ) were recognised"
        raise ValueError(f"Excel import found no BoQ items: {grund}.")
    positionen.sort(key=lambda eintrag: eintrag[:2])
    name = Path(dateiname).stem or "Excel BoQ"
    return LV(name=name, quelle=dateiname or "upload.xlsx", positionen=[p for _, _, p in positionen])

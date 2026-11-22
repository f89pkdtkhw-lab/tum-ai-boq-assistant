"""t256: AI reading of a competitor/offer PDF for the margin page.

The PDF goes directly to the configured model (Claude or Grok Bot, same path as the BoQ
Excel/PDF AI import and the AI evaluation). Page images plus the text layer are sent;
the model returns priced items (OZ, text, quantity, unit, EP, GP, bidder). Those rows
are written as an .xlsx in the format ``leseGebote`` / the margin page reads, stored in
the vault (type ``wettbewerb``, versioned, no hash-dedupe) and returned to the UI for
download. The mock provider is rejected: the main UI never falls back to a fake parse.
"""
from __future__ import annotations

import base64
import io
import logging
import os
import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from xml.sax.saxutils import escape

from fastapi import APIRouter, File, Header, HTTPException, UploadFile

from .ai import llm
from .ai.sprache import ohne_hinweis
from . import vault

log = logging.getLogger(__name__)
router = APIRouter(tags=["marge"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
AUFLOESUNG = 110
JPEG_QUALITAET = 80
MAX_TOKENS = 8000
MAX_SEITEN = 20
SEITEN_PRO_AUFRUF = 4
ERLAUBT = ("anthropic", "grokbot")
EIGEN = re.compile(r"^(our|own|us|we|wir|eigen)", re.I)
KOPF = [
    "Anbieter", "Position", "Einheit", "Menge", "Einheitspreis",
    "Angebotsbetrag", "Einzelkosten", "Gemeinkosten %", "Gewinnmarge %",
]
SYSTEM = (
    "You read pages of a German construction offer, price comparison (Preisspiegel) or "
    "competitor bid (Angebot / Submissionsergebnis) from images, helped by the text layer. "
    "Copy item numbers, texts, quantities, units and prices exactly as printed; never invent "
    "a number, a bidder or an item, and never translate. Answer with JSON only."
)

Client = Callable[..., object]


def _zahl_env(name: str, standard: float) -> float:
    try:
        wert = float(os.environ.get(name, ""))
    except ValueError:
        return standard
    return wert if wert > 0 else standard


def pruefe_anbieter() -> dict:
    """A real Claude or Grok Bot call would be made. Mock or a missing key is not accepted."""
    zustand = llm.status()
    if zustand.get("mock") or zustand.get("provider") not in ERLAUBT:
        raise ValueError(
            "Reading a competitor PDF needs Claude or Grok Bot. "
            "Set up the AI provider in the developer options (code 2211)."
        )
    return zustand


def _jpeg(page) -> bytes:
    bild = page.to_image(resolution=AUFLOESUNG).original.convert("RGB")
    puffer = io.BytesIO()
    bild.save(puffer, format="JPEG", quality=JPEG_QUALITAET)
    return puffer.getvalue()


def _seiten(inhalt: bytes) -> list[dict]:
    import pdfplumber
    maximal = int(_zahl_env("MARGE_PDF_MAX_SEITEN", MAX_SEITEN))
    with pdfplumber.open(io.BytesIO(inhalt)) as pdf:
        seiten = []
        for nummer, page in enumerate(pdf.pages[:maximal], start=1):
            try:
                bild = _jpeg(page)
            except Exception as exc:  # noqa: BLE001 - a single page must not abort the rest
                log.warning("Margin PDF: could not render page %s (%s)", nummer, type(exc).__name__)
                bild = b""
            seiten.append({"nummer": nummer, "text": page.extract_text() or "", "bild": bild})
        return seiten


def _bloecke(seiten: list[dict]) -> list[list[dict]]:
    groesse = int(_zahl_env("MARGE_PDF_SEITEN_PRO_AUFRUF", SEITEN_PRO_AUFRUF))
    groesse = max(1, groesse)
    return [seiten[i:i + groesse] for i in range(0, len(seiten), groesse)]


def _prompt(block: list[dict]) -> str:
    nummern = ", ".join(str(s["nummer"]) for s in block)
    texte = "\n\n".join(f"--- page {s['nummer']} text layer ---\n{s['text']}" for s in block)
    return (
        f"The images are pages {nummern} of a priced bill, offer or competitor comparison. "
        "List every priced BoQ item (Position) printed on these pages, in reading order. "
        "Record the bidder (Konkurrent / Bieter / Anbieter) for each row; if the document is "
        "one company's offer, use that company name for every competitor row. Rows that are our "
        "own costs (Selbstkosten, Einzelkosten, Our company, Wir) use bidder \"Our company\". "
        "Skip headers, footers, section titles and sums (Summe, Übertrag, Gesamt). "
        "Copy OZ, short text, quantity, unit, unit price (EP) and line total (GP) exactly as printed. "
        "Use null when a value is not printed; never calculate a missing GP or EP. "
        "If a direct-cost / operating-cost % / profit-margin % split is printed, include it. "
        'Answer with JSON only: {"bieter_dokument": "company name or null", "zeilen": [{'
        '"bieter": "company or Our company", "oz": "item number or null", "text": "short text", '
        '"menge": number or null, "einheit": "unit or null", "ep": number or null, '
        '"gp": number or null, "direkt": number or null, "bgk": number or null, '
        '"marge": number or null}]}.\n\n' + texte
    )


def _als_zahl(wert: Any) -> float | None:
    if wert is None or wert == "":
        return None
    if isinstance(wert, bool):
        return None
    if isinstance(wert, (int, float)):
        return float(wert) if wert == wert else None  # NaN out
    text = str(wert).strip()
    text = re.sub(r"[€\s]|eur", "", text, flags=re.I)
    if not text:
        return None
    deutsch = bool(re.search(r",\d{1,2}$", text)) or (
        bool(re.search(r"\.\d{3}(\D|$)", text)) and not re.search(r",\d{3}", text)
    )
    text = text.replace(".", "").replace(",", ".") if deutsch else text.replace(",", "")
    try:
        return float(text)
    except ValueError:
        return None


def _als_text(wert: Any) -> str:
    return "" if wert is None else str(wert).strip()


def _norm_zahl_text(wert: float) -> list[str]:
    """Forms that may appear in the page text for this number (DE/EN, with/without thousands)."""
    if wert != wert:
        return []
    ganz = abs(wert - round(wert)) < 1e-9
    n = int(round(wert)) if ganz else wert
    formen = {str(n), f"{wert:.2f}", f"{wert:.1f}", f"{wert:.0f}"}
    if ganz:
        formen.add(f"{n:,}".replace(",", "."))
        formen.add(f"{n:,}")
    else:
        formen.add(f"{wert:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        formen.add(f"{wert:,.2f}")
        formen.add(f"{wert:.2f}".replace(".", ","))
    return [f for f in formen if f]


def _steht_im_text(wert: float, text: str) -> bool:
    kompakt = re.sub(r"[\s.']", "", text).replace(",", ".")
    for form in _norm_zahl_text(wert):
        if form and form in text:
            return True
        if re.sub(r"[\s.']", "", form).replace(",", ".") in kompakt:
            return True
    return False


def _zeile_aus_modell(roh: dict, fallback_bieter: str) -> dict | None:
    bieter = _als_text(roh.get("bieter")) or fallback_bieter
    oz = _als_text(roh.get("oz"))
    text = _als_text(roh.get("text") or roh.get("kurztext") or roh.get("item"))
    if oz and text and not text.lower().startswith(oz.lower()):
        item = f"{oz} {text}".strip()
    else:
        item = text or oz
    if not bieter or not item:
        return None
    return {
        "bieter": "Our company" if EIGEN.match(bieter) else bieter,
        "oz": oz or None,
        "item": item,
        "einheit": _als_text(roh.get("einheit") or roh.get("unit")),
        "menge": _als_zahl(roh.get("menge") or roh.get("quantity")),
        "preis": _als_zahl(roh.get("ep") or roh.get("preis") or roh.get("unit_price")),
        "summe": _als_zahl(roh.get("gp") or roh.get("summe") or roh.get("angebot")),
        "direkt": _als_zahl(roh.get("direkt") or roh.get("einzelkosten") or roh.get("direct")),
        "bgk": _als_zahl(roh.get("bgk") or roh.get("gemeinkosten")),
        "marge": _als_zahl(roh.get("marge") or roh.get("gewinn")),
    }


def _frage(block: list[dict], client: Client | None, timeout: float) -> tuple[str, list[dict]]:
    bilder = [s["bild"] for s in block if s.get("bild")]
    aufruf = client or llm.complete
    with ohne_hinweis():
        antwort = aufruf(_prompt(block), system=SYSTEM, max_tokens=MAX_TOKENS, timeout=timeout,
                         json_mode=True, bilder=bilder or None)
    text = antwort.text if hasattr(antwort, "text") else str(antwort)
    daten = llm.parse_json(text)
    if not isinstance(daten, dict):
        return "", []
    fallback = _als_text(daten.get("bieter_dokument"))
    roh = daten.get("zeilen") or daten.get("positionen") or []
    zeilen = []
    if isinstance(roh, list):
        for eintrag in roh:
            if isinstance(eintrag, dict):
                z = _zeile_aus_modell(eintrag, fallback)
                if z:
                    zeilen.append(z)
    return fallback, zeilen


def _pruefe(zeilen: list[dict], seiten_text: str) -> list[dict]:
    """Drop invented amounts when a text layer exists; scanned pages keep the model values."""
    if not seiten_text.strip():
        return zeilen
    sauber = []
    for z in zeilen:
        neu = dict(z)
        for feld in ("menge", "preis", "summe", "direkt", "bgk", "marge"):
            wert = neu[feld]
            if wert is not None and not _steht_im_text(wert, seiten_text):
                neu[feld] = None
        if neu["item"] and (neu["preis"] is not None or neu["summe"] is not None
                            or neu["direkt"] is not None or EIGEN.match(neu["bieter"])):
            sauber.append(neu)
    return sauber


def _schluessel(z: dict) -> str:
    return f"{z['bieter'].casefold()}|{ (z.get('oz') or '').casefold() }|{z['item'].casefold()}"


def _item_schluessel(z: dict) -> str:
    return f"{(z.get('oz') or '').casefold()}|{re.sub(r'^' + re.escape(z.get('oz') or '') + r'\s+', '', z['item'], flags=re.I).casefold()}"


def _tabelle(zeilen: list[dict], fallback_bieter: str) -> list[list]:
    """Header + Our company rows first, then competitor rows. One Our company row per item."""
    gesehen: set[str] = set()
    unique: list[dict] = []
    for z in zeilen:
        if z["bieter"] == "" and fallback_bieter:
            z = {**z, "bieter": fallback_bieter}
        k = _schluessel(z)
        if k in gesehen:
            continue
        gesehen.add(k)
        unique.append(z)

    uns: dict[str, dict] = {}
    konk: list[dict] = []
    for z in unique:
        if EIGEN.match(z["bieter"]):
            uns[_item_schluessel(z)] = z
        else:
            konk.append(z)
    for z in unique:
        k = _item_schluessel(z)
        if k in uns:
            if uns[k]["menge"] is None:
                uns[k]["menge"] = z["menge"]
            if uns[k]["einheit"] == "" and z["einheit"]:
                uns[k]["einheit"] = z["einheit"]
            if uns[k]["direkt"] is None and z["direkt"] is not None and EIGEN.match(z["bieter"]):
                uns[k]["direkt"] = z["direkt"]
            continue
        # Synthesize our row from quantity (and a disclosed direct cost only if this is already ours).
        uns[k] = {
            "bieter": "Our company", "oz": z.get("oz"), "item": z["item"], "einheit": z["einheit"],
            "menge": z["menge"], "preis": None, "summe": None, "direkt": None, "bgk": None, "marge": 2,
        }

    def zellen(z: dict, uns_zeile: bool) -> list:
        return [
            "Our company" if uns_zeile else z["bieter"],
            z["item"],
            z["einheit"] or "",
            z["menge"],
            None if uns_zeile else z["preis"],
            None if uns_zeile else (z["summe"] if z["summe"] is not None else None),
            z["direkt"] if uns_zeile else z["direkt"],
            z["bgk"] if uns_zeile else z["bgk"],
            (z["marge"] if z["marge"] is not None else 2) if uns_zeile else z["marge"],
        ]

    # Stable item order: first occurrence in the document.
    ordnung: list[str] = []
    for z in unique:
        k = _item_schluessel(z)
        if k not in ordnung:
            ordnung.append(k)
    zeilen_out: list[list] = [KOPF]
    for k in ordnung:
        zeilen_out.append(zellen(uns[k], True))
    for z in konk:
        zeilen_out.append(zellen(z, False))
    return zeilen_out


def _spalte(index: int) -> str:
    n = index + 1
    buchstaben = []
    while n:
        n, r = divmod(n - 1, 26)
        buchstaben.append(chr(65 + r))
    return "".join(reversed(buchstaben))


def schreibe_xlsx(zeilen: list[list]) -> bytes:
    """Minimal .xlsx the in-browser ``leseXlsx`` reader accepts (inline strings + numeric cells)."""
    daten = ["<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>",
             "<worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\"><sheetData>"]
    for r, zeile in enumerate(zeilen, start=1):
        daten.append(f"<row r=\"{r}\">")
        for c, wert in enumerate(zeile):
            ref = f"{_spalte(c)}{r}"
            if wert is None or wert == "":
                continue
            if isinstance(wert, (int, float)) and not isinstance(wert, bool):
                zahl = int(wert) if isinstance(wert, float) and wert.is_integer() else wert
                daten.append(f"<c r=\"{ref}\"><v>{zahl}</v></c>")
            else:
                text = escape(str(wert), {"'": "&apos;", '"': "&quot;"})
                daten.append(f"<c r=\"{ref}\" t=\"inlineStr\"><is><t>{text}</t></is></c>")
        daten.append("</row>")
    daten.append("</sheetData></worksheet>")
    blatt = "".join(daten)
    workbook = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<workbook xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\" "
        "xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\">"
        "<sheets><sheet name=\"Angebote\" sheetId=\"1\" r:id=\"rId1\"/></sheets></workbook>"
    )
    rels_root = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">"
        "<Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" "
        "Target=\"xl/workbook.xml\"/></Relationships>"
    )
    rels_wb = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">"
        "<Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet\" "
        "Target=\"worksheets/sheet1.xml\"/></Relationships>"
    )
    typen = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">"
        "<Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/>"
        "<Default Extension=\"xml\" ContentType=\"application/xml\"/>"
        "<Override PartName=\"/xl/workbook.xml\" "
        "ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml\"/>"
        "<Override PartName=\"/xl/worksheets/sheet1.xml\" "
        "ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml\"/>"
        "</Types>"
    )
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", typen)
        z.writestr("_rels/.rels", rels_root)
        z.writestr("xl/workbook.xml", workbook)
        z.writestr("xl/_rels/workbook.xml.rels", rels_wb)
        z.writestr("xl/worksheets/sheet1.xml", blatt)
    return puffer.getvalue()


def _dateiname(quelle: str) -> str:
    stem = Path(quelle or "angebot").stem or "angebot"
    stem = re.sub(r"[^\w\- äöüÄÖÜß.]+", "", stem, flags=re.I).strip() or "angebot"
    stempel = datetime.now().strftime("%Y-%m-%d %H-%M-%S")
    return f"{stem} – {stempel}.xlsx"


def _hinweis(tabelle: list[list]) -> str | None:
    uns = [z for z in tabelle[1:] if z and EIGEN.match(str(z[0] or ""))]
    if uns and all(z[6] is None for z in uns):
        return ("No direct costs were found in the PDF. Add an Our company row with direct costs "
                "so the margin slider can work.")
    if len(tabelle) <= 1:
        return "The model found no priced items in this PDF."
    return None


def extrahiere(dateiname: str, inhalt: bytes, *, client: Client | None = None,
               besitzer: str | None = None, anbieter_pruefen: bool = True) -> dict:
    """Read a PDF via the model, build the margin Excel, store a new vault version."""
    if anbieter_pruefen:
        pruefe_anbieter()
    if not inhalt:
        raise ValueError("The uploaded file is empty.")
    seiten = _seiten(inhalt)
    if not seiten:
        raise ValueError("The PDF has no readable pages.")
    timeout = _zahl_env("MARGE_PDF_TIMEOUT", 120)
    alle: list[dict] = []
    fallback = ""
    for block in _bloecke(seiten):
        name, zeilen = _frage(block, client, timeout)
        if name and not fallback:
            fallback = name
        alle.extend(zeilen)
    seiten_text = "\n".join(s["text"] for s in seiten)
    alle = _pruefe(alle, seiten_text)
    if not alle:
        raise ValueError("No priced items were recognized in the PDF.")
    tabelle = _tabelle(alle, fallback)
    xlsx = schreibe_xlsx(tabelle)
    name = _dateiname(dateiname)
    eintrag = vault.lege_ab(xlsx, name, "wettbewerb", besitzer=besitzer, quelle="ki",
                            tags=["ki"], projekt=Path(dateiname or "angebot").name)
    return {
        "dateiname": name,
        "hinweis": _hinweis(tabelle),
        "gebote": max(0, len(tabelle) - 1),
        "xlsx_base64": base64.b64encode(xlsx).decode("ascii"),
        "vault": eintrag.model_dump() if eintrag is not None else None,
    }


@router.post("/api/marge/pdf")
async def pdf_einlesen(datei: UploadFile = File(...), x_lv_scout_user: str | None = Header(None)):
    if not (datei.filename or "").lower().endswith(".pdf"):
        raise HTTPException(422, "Please upload a PDF file.")
    try:
        inhalt = await datei.read(MAX_UPLOAD_BYTES + 1)
    finally:
        await datei.close()
    if len(inhalt) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File is too large (maximum 10 MiB).")
    try:
        return extrahiere(datei.filename or "angebot.pdf", inhalt, besitzer=x_lv_scout_user)
    except ValueError as exc:
        raise HTTPException(409 if "2211" in str(exc) else 422, str(exc)) from None
    except llm.LLMError as exc:
        # Never include secrets; the provider error text is shown as-is (llm.LLMError already avoids keys).
        raise HTTPException(502, str(exc)) from None

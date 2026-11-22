"""Read a tender opening record (Submissionsergebnis / Niederschrift über die Angebotseröffnung) into bidders and totals.

Order: text from the file (PDF via pdfplumber, Excel via its XML, CSV/TXT as text) → fixed rules (a bidder column
and an amount, or "1. Company … 1.234.567,89 €" lines) → the language model only when the rules find fewer than
two bidders and a real provider is configured. Every model answer is checked against the text: an amount that does
not occur in the document is dropped, so nothing is invented. Offline (mock) the rules result is returned as is.
"""
import io
import json
import re
import zipfile
from xml.etree import ElementTree as ET

from fastapi import APIRouter, HTTPException, UploadFile

from . import llm

router = APIRouter()
MAX_BYTES = 10 * 1024 * 1024
BETRAG = re.compile(r"(\d{1,3}(?:[.,  ]\d{3})+(?:[.,]\d{1,2})?|\d{4,}(?:[.,]\d{1,2})?)\s*(?:€|eur|euro)?\s*$", re.I)
NAME_SPALTE = re.compile(r"bieter|firma|company|bidder|name|unternehmen", re.I)
BETRAG_SPALTE = re.compile(r"summe|betrag|angebot|total|bid|preis|price|brutto|netto", re.I)


def zahl(text: str) -> float | None:
    s = re.sub(r"[€\s ]|eur", "", text, flags=re.I)
    deutsch = bool(re.search(r",\d{1,2}$", s)) or (bool(re.search(r"\.\d{3}(\D|$)", s)) and not re.search(r",\d{3}", s))
    s = s.replace(".", "").replace(",", ".") if deutsch else s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def text_aus_datei(name: str, inhalt: bytes) -> str:
    endung = name.lower().rsplit(".", 1)[-1] if "." in name else ""
    if endung == "pdf":
        import pdfplumber
        with pdfplumber.open(io.BytesIO(inhalt)) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages[:30])
    if endung == "xlsx":
        return _xlsx_text(inhalt)
    for kodierung in ("utf-8-sig", "cp1252"):
        try:
            return inhalt.decode(kodierung)
        except UnicodeDecodeError:
            continue
    raise ValueError("The file is not readable text.")


def _xlsx_text(inhalt: bytes) -> str:
    """First worksheet as ';'-separated lines, stdlib only."""
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(io.BytesIO(inhalt)) as z:
        geteilt = []
        if "xl/sharedStrings.xml" in z.namelist():
            geteilt = ["".join(t.text or "" for t in si.iter(f"{{{ns['m']}}}t")) for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", ns)]
        blatt = sorted(n for n in z.namelist() if n.startswith("xl/worksheets/sheet"))[0]
        zeilen = []
        for row in ET.fromstring(z.read(blatt)).iter(f"{{{ns['m']}}}row"):
            werte = []
            for c in row.findall("m:c", ns):
                v = c.find("m:v", ns)
                inline = c.find("m:is", ns)
                wert = "".join(t.text or "" for t in inline.iter(f"{{{ns['m']}}}t")) if inline is not None else (v.text if v is not None else "")
                werte.append(geteilt[int(wert)] if c.get("t") == "s" and wert else wert)
            zeilen.append(";".join(werte))
        return "\n".join(zeilen)


def regeln(text: str) -> list[dict]:
    zeilen = [z.strip() for z in text.splitlines() if z.strip()]
    kopf = next((i for i, z in enumerate(zeilen[:15]) if NAME_SPALTE.search(z) and re.search(r"[;\t]", z)), None)
    if kopf is not None:
        trenner = ";" if ";" in zeilen[kopf] else "\t"
        spalten = [k.strip() for k in zeilen[kopf].split(trenner)]
        i_name = next((i for i, k in enumerate(spalten) if NAME_SPALTE.search(k)), -1)
        i_betrag = next((i for i, k in enumerate(spalten) if BETRAG_SPALTE.search(k) and not re.search(r"rang|rank|nr", k, re.I)), -1)
        if i_name >= 0 and i_betrag >= 0:
            out = []
            for z in zeilen[kopf + 1:]:
                f = [x.strip().strip('"') for x in z.split(trenner)]
                summe = zahl(f[i_betrag]) if len(f) > i_betrag else None
                if len(f) > i_name and f[i_name] and summe and summe > 0:
                    out.append({"firma": f[i_name], "summe": summe})
            if out:
                return out
    out = []
    for z in zeilen:
        if re.match(r"^(summe|gesamt|total|rang|nr\.?\s)", z, re.I):
            continue
        m = BETRAG.search(z)
        if not m:
            continue
        firma = re.sub(r"[;:,\t|–-]+\s*$", "", re.sub(r"^\s*\d+\s*[.)]?\s+", "", z[:m.start()])).strip()
        summe = zahl(re.sub(r"[  ]", ".", m.group(1)))
        if firma and re.search(r"[^\W\d_]", firma) and summe and summe > 0:
            out.append({"firma": firma, "summe": summe})
    return out


def _im_text(summe: float, text: str) -> bool:
    """The model's amount must occur in the document (any thousands format)."""
    ziffern = re.sub(r"\D", "", text)
    ganz = str(int(round(summe)))
    return ganz in ziffern or f"{summe:.2f}".replace(".", "") in ziffern


def mit_modell(text: str) -> list[dict]:
    antwort = llm.complete(
        "From this tender opening record, list every bidder with its total bid amount. Answer only JSON: "
        '{"bidders": [{"company": "...", "total": 1234567.89}]}. Use amounts exactly as printed, no estimates.\n\n' + text[:12000],
        system="You extract data from German construction tender documents. Never invent companies or amounts.", max_tokens=1500)
    roh = antwort.text[antwort.text.find("{"): antwort.text.rfind("}") + 1]
    daten = json.loads(roh) if roh else {}
    out = []
    for b in daten.get("bidders", []):
        firma, summe = str(b.get("company", "")).strip(), b.get("total")
        if firma and isinstance(summe, (int, float)) and summe > 0 and _im_text(float(summe), text):
            out.append({"firma": firma, "summe": float(summe)})
    return out


def lesen(name: str, inhalt: bytes) -> dict:
    text = text_aus_datei(name, inhalt)
    bieter, methode = regeln(text), "regeln"
    hinweis = None
    if len(bieter) < 2:
        if llm.provider() != "mock":
            try:
                ki = mit_modell(text)
                if len(ki) > len(bieter):
                    bieter, methode = ki, "ki"
            except (llm.LLMError, ValueError, json.JSONDecodeError) as exc:
                hinweis = f"AI reading failed: {exc}"
        else:
            hinweis = "Rules found fewer than two bidders; AI reading needs a model key."
    return {"bieter": bieter, "methode": methode, "hinweis": hinweis, "zeichen": len(text)}


@router.post("/api/submission/lesen")
def submission_lesen(datei: UploadFile):
    inhalt = datei.file.read(MAX_BYTES + 1)
    if len(inhalt) > MAX_BYTES:
        raise HTTPException(413, "The file is larger than 10 MB.")
    try:
        return lesen(datei.filename or "", inhalt)
    except (ValueError, zipfile.BadZipFile, IndexError) as exc:
        raise HTTPException(422, f"The document could not be read: {exc}") from None

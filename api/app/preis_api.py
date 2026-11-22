"""Price list upload and price database routes (issue #153, epic #93 D4/D5/B9).

- ``POST /api/preisliste/import`` (multipart ``datei``, optional ``lv`` = tender bill for D84 texts): CSV, XLSX, GAEB X8x/D8x or JSON → ``Preisliste``;
  the entries are also stored in the price database (same item + unit = update).
- ``GET``/``POST /api/db/preise``: the UI contract (field ``item``) on top of @Anatomik5's price table in
  ``db/client.py`` (field ``name``). The adapter only uses that module's connection helper, so its own
  routes (``/api/db/prices…``, also mounted here) and tests stay unchanged.
- ``als_preisliste()`` is registered as ``pruefung.preise.preis_service`` at start-up, so
  ``/api/lv/analyse`` prices from the database when no list is uploaded (B9 #133).

``db`` is imported lazily: without it (or without duckdb) the API still starts, the routes answer 503 and the
analysis gets the B9 "price database unreachable" warning instead of an exception.
"""
from __future__ import annotations

import csv
import hashlib
import io
import logging
import re
import sys
import time
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from fastapi import APIRouter, FastAPI, Header, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field, ValidationError, field_validator

from .modelle import LV, Preisliste, PreislistenEintrag
from .pruefung import preise
from .pruefung.regeln import _kanonische_einheit

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
log = logging.getLogger(__name__)
router = APIRouter(tags=["prices"])


class NeuerPreis(BaseModel):
    """Body row of POST /api/db/preise (epic #93 D5)."""
    item: str
    unit: str
    price_per_unit: float = Field(gt=0, allow_inf_nan=False)

    @field_validator("item", "unit")
    @classmethod
    def validate_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        if value.casefold() == "string":
            raise ValueError("'string' is a placeholder")
        return value


class PreisEintrag(BaseModel):
    id: int
    item: str
    unit: str
    price_per_unit: float


# --- Price database adapter (db/client.py: table prices(id, name, unit, price_per_unit)) ---

def _verbinde(read_only: bool = False):
    try:
        from db import client  # noqa: PLC0415 - optional, lives in the repository root
    except Exception as exc:  # noqa: BLE001 - missing db/ or duckdb must not stop the API
        raise HTTPException(503, f"Price database is not available: {exc}") from None
    return client._connect_price(read_only=read_only)


def _einheit(roh: str) -> str:
    """Canonical unit spelling (m2 → m², Stk → St, …) as used by the rest of the API."""
    roh = roh.strip()
    return preise.WEITERE_EINHEITEN.get(roh.lower(), _kanonische_einheit(roh))


def _schluessel(item: str, unit: str) -> tuple[str, str | None]:
    return item.strip().casefold(), preise.kanonische_einheit(unit)


def _als_eintrag(zeile) -> PreisEintrag:
    return PreisEintrag(id=int(zeile[0]), item=zeile[1] or "", unit=zeile[2] or "", price_per_unit=float(zeile[3]))


def speichere_preise(neue: list[NeuerPreis]) -> list[PreisEintrag]:
    """Upsert: an existing row with the same item (case-insensitive) and canonical unit gets the new price."""
    if not neue:
        return []
    with _verbinde() as conn:
        zeilen = conn.execute("SELECT id, name, unit, price_per_unit FROM prices").fetchall()
        vorhanden = {_schluessel(z[1] or "", z[2] or ""): int(z[0]) for z in zeilen}
        naechste = max(int(time.time() * 1000), max((int(z[0]) for z in zeilen), default=0) + 1)
        ergebnis: dict[tuple, PreisEintrag] = {}
        for neu in neue:
            item, unit = neu.item.strip(), _einheit(neu.unit)
            schluessel = _schluessel(item, unit)
            if schluessel in vorhanden:
                conn.execute("UPDATE prices SET name = ?, unit = ?, price_per_unit = ? WHERE id = ?",
                             [item, unit, neu.price_per_unit, vorhanden[schluessel]])
            else:
                vorhanden[schluessel] = naechste
                naechste += 1
                conn.execute("INSERT INTO prices (id, name, unit, price_per_unit) VALUES (?, ?, ?, ?)",
                             [vorhanden[schluessel], item, unit, neu.price_per_unit])
            ergebnis[schluessel] = PreisEintrag(id=vorhanden[schluessel], item=item, unit=unit,
                                                price_per_unit=neu.price_per_unit)
    return list(ergebnis.values())


def lade_preise(item: str = "", unit: str = "", limit: int | None = None) -> list[PreisEintrag]:
    with _verbinde(read_only=True) as conn:
        zeilen = conn.execute("SELECT id, name, unit, price_per_unit FROM prices ORDER BY id DESC").fetchall()
    suche, einheit = item.strip().casefold(), preise.kanonische_einheit(unit)
    treffer = [_als_eintrag(z) for z in zeilen
               if (not suche or suche in (z[1] or "").casefold())
               and (einheit is None or preise.kanonische_einheit(z[2] or "") == einheit)]
    return treffer if limit is None else treffer[:limit]


def als_preisliste() -> Preisliste | None:
    """B9 seam: the whole price table as a `Preisliste` with id "preis-db"; None when it is empty."""
    eintraege = [PreislistenEintrag(id=str(e.id), kurztext=e.item, einheit=e.unit, ep=e.price_per_unit,
                                    quelle=f"{preise.PREIS_DB_ID}:{e.id}")
                 for e in lade_preise() if e.unit.strip()]
    return Preisliste(id=preise.PREIS_DB_ID, dateiname="price database", eintraege=eintraege) if eintraege else None


@router.get("/api/db/preise", response_model=list[PreisEintrag])
def get_preise(item: str = Query(default=""), unit: str = Query(default=""),
               limit: int = Query(default=200, ge=1, le=10000)):
    try:
        return lade_preise(item, unit, limit)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - e.g. a DB file written by a newer duckdb: say so, no bare 500
        raise HTTPException(503, f"Price database cannot be read: {exc}") from None


@router.post("/api/db/preise", response_model=list[PreisEintrag])
def post_preise(neue: list[NeuerPreis]):
    try:
        return speichere_preise(neue)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - shown to the user instead of a bare 500
        raise HTTPException(500, f"Price database write failed: {exc}") from None


# --- Price list import (D4): CSV / XLSX / GAEB / JSON → Preisliste ---

SPALTEN = {
    "oz": ("oz", "pos", "position", "ordnungszahl"),
    "kurztext": ("kurztext", "text", "item", "name", "bezeichnung", "beschreibung", "description", "leistung"),
    "einheit": ("einheit", "unit", "me", "mengeneinheit"),
    "ep": ("ep", "preis", "price", "price_per_unit", "einheitspreis", "unit_price", "ep_eur"),
    "waehrung": ("waehrung", "währung", "currency"),
}
PFLICHT = ("kurztext", "einheit", "ep")


def _zahl(roh) -> float | None:
    if isinstance(roh, (int, float)):
        return float(roh)
    text = re.sub(r"[\s€]|EUR", "", str(roh or ""), flags=re.IGNORECASE)
    if not text:
        return None
    if "," in text and "." in text:
        tausender = "." if text.rfind(",") > text.rfind(".") else ","
        text = text.replace(tausender, "")
    text = text.replace(",", ".")
    try:
        wert = float(text)
    except ValueError:
        return None
    return wert if wert == wert and abs(wert) != float("inf") else None


def _aus_tabelle(dateiname: str, zeilen: list[list[str]]) -> tuple[list[PreislistenEintrag], list[str], str]:
    kopf_index = next((i for i, z in enumerate(zeilen) if any(str(c).strip() for c in z)), None)
    if kopf_index is None:
        raise ValueError("The price list contains no rows.")
    kopf = [str(c).strip().casefold() for c in zeilen[kopf_index]]
    spalte = {feld: next((i for i, k in enumerate(kopf) if k in namen), None) for feld, namen in SPALTEN.items()}
    fehlend = [f for f in PFLICHT if spalte[f] is None]
    if fehlend:
        raise ValueError(f"Missing column(s): {', '.join(fehlend)}. Expected columns: oz (optional), kurztext, "
                         "einheit, ep, waehrung (optional).")

    def zelle(z: list, feld: str) -> str:
        i = spalte[feld]
        return str(z[i]).strip() if i is not None and i < len(z) and z[i] is not None else ""

    eintraege, warnungen, waehrungen = [], [], set()
    for nummer, z in enumerate(zeilen[kopf_index + 1:], start=kopf_index + 2):
        if not any(str(c).strip() for c in z if c is not None):
            continue
        oz, text, einheit, roh_ep = zelle(z, "oz"), zelle(z, "kurztext"), zelle(z, "einheit"), zelle(z, "ep")
        ep = _zahl(roh_ep)
        if not (text or oz):
            warnungen.append(f"Row {nummer}: no short text or OZ, skipped.")
        elif not einheit:
            warnungen.append(f"Row {nummer}: no unit, skipped.")
        elif ep is None or ep < 0:
            warnungen.append(f"Row {nummer}: no valid unit price ({roh_ep or 'empty'}), skipped.")
        else:
            if zelle(z, "waehrung"):
                waehrungen.add(zelle(z, "waehrung").upper())
            eintraege.append(PreislistenEintrag(id=f"z{nummer}", oz=oz or None, kurztext=text,
                                                einheit=_einheit(einheit), ep=ep, quelle=f"{dateiname}:{nummer}"))
    if len(waehrungen) > 1:
        warnungen.append(f"Mixed currencies ({', '.join(sorted(waehrungen))}); prices are not converted.")
    return eintraege, warnungen, (waehrungen.pop() if len(waehrungen) == 1 else "EUR")


def _csv_zeilen(inhalt: bytes) -> list[list[str]]:
    for kodierung in ("utf-8-sig", "cp1252", "latin-1"):  # latin-1 never fails
        try:
            text = inhalt.decode(kodierung)
            break
        except UnicodeDecodeError:
            continue
    try:
        dialekt = csv.Sniffer().sniff(text[:4096], delimiters=";,\t")
    except csv.Error:
        dialekt = csv.excel
    return list(csv.reader(io.StringIO(text), dialekt))


_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _xlsx_zeilen(inhalt: bytes) -> list[list[str]]:
    """First worksheet of an XLSX file with the standard library only (no new dependency)."""
    try:
        mappe = zipfile.ZipFile(io.BytesIO(inhalt))
    except zipfile.BadZipFile:
        raise ValueError("Invalid XLSX file.") from None
    namen = mappe.namelist()
    texte = []
    if "xl/sharedStrings.xml" in namen:
        for si in ElementTree.fromstring(mappe.read("xl/sharedStrings.xml")).iter(f"{_NS}si"):
            texte.append("".join(t.text or "" for t in si.iter(f"{_NS}t")))
    blaetter = sorted((n for n in namen if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n)),
                      key=lambda n: int(re.search(r"\d+", n.rsplit("/", 1)[1]).group()))
    if not blaetter:
        raise ValueError("The XLSX file contains no worksheet.")
    zeilen = []
    for row in ElementTree.fromstring(mappe.read(blaetter[0])).iter(f"{_NS}row"):
        zeile: dict[int, str] = {}
        for c in row.iter(f"{_NS}c"):
            treffer = re.match(r"[A-Z]+", c.get("r") or "")
            buchstaben = treffer.group() if treffer else None
            spalte = sum((ord(b) - 64) * 26 ** i for i, b in enumerate(reversed(buchstaben))) - 1 if buchstaben \
                else len(zeile)
            typ, v = c.get("t"), c.find(f"{_NS}v")
            if typ == "s" and v is not None:
                wert = texte[int(v.text)]
            elif typ == "inlineStr":
                wert = "".join(t.text or "" for t in c.iter(f"{_NS}t"))
            else:
                wert = v.text if v is not None and v.text is not None else ""
            zeile[spalte] = wert
        zeilen.append([zeile.get(i, "") for i in range(max(zeile, default=-1) + 1)])
    return zeilen


LV_BEGLEIT_ENDUNGEN = (".x83", ".d83", ".x84", ".d84", ".x86", ".d86")


def _gaeb_lv(dateiname: str, inhalt: bytes) -> LV:
    from .lv import gaeb  # noqa: PLC0415
    if Path(dateiname).suffix.lower().startswith(".d"):
        from .lv import gaeb90  # noqa: PLC0415
        return gaeb.to_lv(gaeb90.parse_legacy(dateiname, inhalt))
    return gaeb.importiere(dateiname, inhalt)


def _oz_schluessel(oz: str | None) -> str:
    """OZ without padding, so "01.01.0010" (X83) and "1.1.10" (D84) are the same item."""
    teile = [t.strip().lstrip("0") or "0" for t in re.split(r"[.\s]+", (oz or "").strip()) if t.strip()]
    return ".".join(t.casefold() for t in teile)


def _aus_gaeb(dateiname: str, inhalt: bytes, lv_name: str | None = None,
              lv_inhalt: bytes | None = None) -> tuple[list[PreislistenEintrag], list[str]]:
    """Priced GAEB bill (same rule as @Anatomik5's /prices/import-gaeb in db/client.py: items with EP + unit).

    A DA84 offer usually carries only OZ, quantity, unit and unit price; the item texts are in the tender's
    D83/X83. With that bill as second file, short text and missing units are taken from it by OZ."""
    lv = _gaeb_lv(dateiname, inhalt)
    warnungen: list[str] = []
    texte: dict[str, tuple[str, str | None]] = {}
    if lv_inhalt is not None:
        name = lv_name or "bill"
        if Path(name).suffix.lower() not in LV_BEGLEIT_ENDUNGEN:
            raise ValueError("The matching bill must be a GAEB file (X83, D83, X84, D84, X86, D86).")
        try:
            begleit = _gaeb_lv(name, lv_inhalt)
        except ValueError as exc:
            raise ValueError(f"Could not read the matching bill {name}: {exc}") from None
        texte = {_oz_schluessel(p.oz): (p.kurztext.strip(), p.einheit) for p in begleit.positionen}
    eintraege, ohne_text, zugeordnet = [], 0, 0
    for p in lv.positionen:
        kurztext, einheit = p.kurztext.strip(), (p.einheit or "").strip()
        if texte:
            text, lv_einheit = texte.get(_oz_schluessel(p.oz), ("", None))
            if text or (lv_einheit or "").strip():
                zugeordnet += 1
            kurztext = kurztext or text
            einheit = einheit or (lv_einheit or "").strip()
        if p.ep is None or not einheit:
            continue
        if not kurztext:
            ohne_text += 1
        eintraege.append(PreislistenEintrag(id=f"oz-{p.oz}", oz=p.oz, kurztext=kurztext, einheit=_einheit(einheit),
                                            ep=p.ep, quelle=f"{dateiname}:{p.oz}"))
    ohne = len(lv.positionen) - len(eintraege)
    if ohne:
        warnungen.append(f"{ohne} item(s) without unit price or unit were skipped.")
    if texte and not zugeordnet:
        warnungen.append(f"No item of {lv_name} matches the OZ of {dateiname}; is it the right bill?")
    if ohne_text:
        warnungen.append(f"{ohne_text} item(s) have no item text (a D84 offer usually carries prices only). "
                         "Add the matching bill (D83/X83) to keep their prices in the price database; "
                         "until then they are only matched by OZ.")
    if not eintraege:
        if any(p.ep is not None for p in lv.positionen) and not texte:
            raise ValueError("The GAEB file has unit prices but no units or item texts (price-only D84). "
                             "Add the matching bill (D83/X83/D86) as second file.")
        raise ValueError("The GAEB file contains no items with unit price and unit.")
    return eintraege, warnungen


def lies_preisliste(dateiname: str, inhalt: bytes, lv_name: str | None = None,
                    lv_inhalt: bytes | None = None) -> Preisliste:
    endung = Path(dateiname).suffix.lower()
    pid = f"preisliste-{hashlib.sha256(inhalt + (lv_inhalt or b'')).hexdigest()[:12]}"
    if lv_inhalt is not None and not re.fullmatch(r"\.[xd]8\d", endung):
        raise ValueError("A matching bill only applies to GAEB price files (X84/D84/X86/D86).")
    if endung == ".json":
        try:
            liste = Preisliste.model_validate_json(inhalt)
        except ValidationError as exc:
            raise ValueError(f"Invalid price list JSON: {exc.errors()[0]['msg']}") from None
        return liste.model_copy(update={"dateiname": liste.dateiname or dateiname})
    if endung in (".csv", ".txt", ".xlsx"):
        zeilen = _xlsx_zeilen(inhalt) if endung == ".xlsx" else _csv_zeilen(inhalt)
        eintraege, warnungen, waehrung = _aus_tabelle(dateiname, zeilen)
    elif re.fullmatch(r"\.[xd]8\d", endung):
        eintraege, warnungen = _aus_gaeb(dateiname, inhalt, lv_name, lv_inhalt)
        waehrung = "EUR"
    elif endung == ".pdf":
        raise ValueError("PDF price lists are not read (prices are never inferred from prose). "
                         "Please upload CSV, XLSX, GAEB X84/D84/X86/D86 or JSON.")
    else:
        raise ValueError("Unsupported price list format. Allowed: CSV, XLSX, GAEB X84/D84/X86/D86, JSON.")
    if not eintraege:
        warnungen.append("The price list contains no usable entries.")
    return Preisliste(id=pid, dateiname=dateiname, waehrung=waehrung, eintraege=eintraege, warnungen=warnungen)


def _als_neue_preise(liste: Preisliste, nur_mit_text: bool = False) -> list[NeuerPreis]:
    """Same mapping as the UI preview (web/lib/preis-db.ts): item falls back to the OZ.

    ``nur_mit_text``: GAEB items without a short text are not stored by OZ alone (an OZ only means something
    inside its own bill); they stay in the returned list for this analysis."""
    neue = []
    for nummer, e in enumerate(liste.eintraege, start=1):
        if nur_mit_text and not e.kurztext.strip():
            continue
        try:
            neue.append(NeuerPreis(item=e.kurztext.strip() or e.oz or "", unit=e.einheit, price_per_unit=e.ep))
        except ValidationError as exc:
            fehler = exc.errors()[0]
            quelle = e.quelle or f"{liste.dateiname} entry {nummer}"
            liste.warnungen.append(f"{quelle}: {fehler['loc'][0]} {fehler['msg']}, skipped for database import.")
    return neue


@router.post("/api/preisliste/import", response_model=Preisliste)
async def import_preisliste(datei: UploadFile, lv: UploadFile | None = None, x_lv_scout_user: str | None = Header(None)):
    """``lv`` (optional): the tender bill (D83/X83/…) that gives a D84 offer its item texts."""
    try:
        inhalt = await datei.read(MAX_UPLOAD_BYTES + 1)
        if len(inhalt) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "File is too large (maximum 10 MiB).")
        if not inhalt:
            raise HTTPException(422, "The uploaded file is empty.")
        lv_inhalt = None
        if lv is not None:
            lv_inhalt = await lv.read(MAX_UPLOAD_BYTES + 1)
            if len(lv_inhalt) > MAX_UPLOAD_BYTES:
                raise HTTPException(413, "The matching bill is too large (maximum 10 MiB).")
            if not lv_inhalt:
                raise HTTPException(422, "The matching bill is empty.")
        liste = lies_preisliste(datei.filename or "", inhalt, lv.filename if lv else None, lv_inhalt)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    finally:
        await datei.close()
        if lv is not None:
            await lv.close()
    from . import vault  # noqa: PLC0415  t243: price lists are filed in the vault (deduplicated)
    vault.lege_ab(inhalt, datei.filename or "preisliste", "preisliste", besitzer=x_lv_scout_user)
    if lv is not None and lv_inhalt:
        vault.lege_ab(lv_inhalt, lv.filename or "lv", "lv", besitzer=x_lv_scout_user)
    gaeb_datei = bool(re.fullmatch(r"\.[xd]8\d", Path(datei.filename or "").suffix.lower()))
    neue = _als_neue_preise(liste, nur_mit_text=gaeb_datei)
    try:
        speichere_preise(neue)
    except Exception as exc:  # noqa: BLE001 - the parsed list is still usable for this analysis
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        liste.warnungen.append(f"Prices were read but not stored in the price database: {detail}")
    return liste


def einbinden(app: FastAPI) -> None:
    """Single seam for main.py: routes, @Anatomik5's own price routes under /api/db, and the B9 price seam."""
    app.include_router(router)
    try:
        from db.client import price_router  # noqa: PLC0415
        app.include_router(price_router, prefix="/api/db")
    except Exception as exc:  # noqa: BLE001 - optional, like the history router in main.py
        log.warning("Price router not mounted: %s", exc)
    if "pytest" not in sys.modules:  # tests register the seam themselves against a temporary database
        preise.preis_service = als_preisliste

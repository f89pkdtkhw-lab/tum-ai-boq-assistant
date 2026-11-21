"""Project close (epic #93 D3, issues #101/#154): our report/estimate + the real final bill → one history record.

`POST /api/db/abschluss` (multipart `bericht`, `abrechnung`, optional `description`, `tags`, `note`) parses both
files with the same parsers as the bill upload, builds `expected_json` (our estimate) and `actual_json` (the real
final bill) per OZ, and stores the 7-column record in the history DB of `db/client.py` (@Anatomik5). The JSON shapes
are the ones Reports 2/3 (`pruefung/berichte.py`: `positionen`) and `db/history_adapter.py` (`measurements`) read.
No prices are invented: every value comes from one of the two files.
"""
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, ValidationError

from .lv import gaeb
from .lv.importer import importiere
from .modelle import LV

router = APIRouter(tags=["history-db"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
GAEB_ENDUNGEN = {".x83", ".x84", ".x86", ".d83", ".d84", ".d86"}
BERICHT_ENDUNGEN = {".json", ".xlsx", ".x83", ".x84", ".pdf"}  # web/lib/abschluss.ts BERICHT_FORMATE
ABRECHNUNG_ENDUNGEN = {".x84", ".x86", ".xlsx", ".pdf", ".json"}  # web/lib/abschluss.ts ABRECHNUNG_FORMATE
METRIK = "menge"  # same metric as Report 2 (pruefung/berichte.py METRIK)


class AbschlussRecord(BaseModel):
    """`RecordResponse` of db/client.py plus the optional `warnungen` the UI shows (web/lib/abschluss.ts DbRecord)."""
    id: int
    date: str
    description: str
    tags: list[str]
    expected_json: dict[str, Any]
    actual_json: dict[str, Any]
    note: str
    warnungen: list[str] = Field(default_factory=list)


class _DateiFehler(ValueError):
    pass


def _db():
    """The history DB module; optional like the DB router in main.py, so a missing duckdb gives a readable 503."""
    try:
        from db import client
    except Exception as exc:  # noqa: BLE001 – any import failure means the DB is not available here
        raise HTTPException(503, f"History database is not available: {exc}") from None
    return client


def _zeile(oz: str, kurztext: str, menge, einheit, ep, gp, **extra) -> dict[str, Any]:
    return {"oz": oz, "kurztext": kurztext, "menge": menge, "einheit": einheit, "ep": ep, "gp": gp, **extra}


def _zeilen_aus_lv(lv: LV) -> list[dict[str, Any]]:
    return [_zeile(p.oz, p.kurztext, p.menge, p.einheit, p.ep, p.gp) for p in lv.positionen]


def _aus_bericht_json(daten: dict[str, Any]) -> tuple[LV, list[dict[str, Any]]]:
    """Exported report (`Pruefbericht`): the estimated bill (B8) when present, else the reviewed bill."""
    lv = LV.model_validate(daten["lv"])
    geschaetzt = daten.get("geschaetztes_lv") or {}
    positionen = geschaetzt.get("positionen") if isinstance(geschaetzt, dict) else None
    if not isinstance(positionen, list) or not positionen:
        return lv, _zeilen_aus_lv(lv)
    zeilen = []
    for p in positionen:
        if isinstance(p, dict) and str(p.get("oz") or "").strip():
            zeilen.append(_zeile(str(p["oz"]).strip(), str(p.get("kurztext") or ""), p.get("menge_neu"),
                                 p.get("einheit"), p.get("ep"), p.get("gp_neu"), status=p.get("status")))
    return lv, zeilen


def _parse(art: str, dateiname: str, inhalt: bytes, erlaubt: set[str]) -> tuple[LV, list[dict[str, Any]]]:
    """LV + rows {oz, kurztext, menge, einheit, ep, gp} of one file; errors name the file."""
    endung = Path(dateiname).suffix.lower()
    if endung not in erlaubt:
        raise _DateiFehler(f"{art} “{dateiname}” has an unsupported format. Allowed: "
                           f"{', '.join(sorted(e.lstrip('.').upper() for e in erlaubt))}.")
    try:
        if endung == ".json":
            daten = json.loads(inhalt)
            if isinstance(daten, dict) and isinstance(daten.get("lv"), dict):
                return _aus_bericht_json(daten)
            lv = LV.model_validate(daten)
        elif endung in GAEB_ENDUNGEN:
            lv = gaeb.importiere(dateiname, inhalt)
        else:
            lv = importiere(dateiname, inhalt)
    except (ValidationError, json.JSONDecodeError, UnicodeDecodeError):
        raise _DateiFehler(f"{art} “{dateiname}” could not be read: invalid BoQ or report JSON.") from None
    except (ValueError, NotImplementedError) as exc:
        raise _DateiFehler(f"{art} “{dateiname}” could not be read: {exc}") from None
    return lv, _zeilen_aus_lv(lv)


def _eindeutig(art: str, dateiname: str, zeilen: list[dict[str, Any]], warnungen: list[str]) -> dict[str, dict]:
    nach_oz: dict[str, dict] = {}
    for z in zeilen:
        if z["oz"] in nach_oz:
            warnungen.append(f"{art} “{dateiname}”: OZ {z['oz']} appears more than once; the first one is used.")
            continue
        nach_oz[z["oz"]] = z
    return nach_oz


def _seite(quelle: str, name: str, zeilen: list[dict[str, Any]]) -> dict[str, Any]:
    summe = round(sum(z["gp"] for z in zeilen if isinstance(z.get("gp"), (int, float))), 2)
    messungen = [{"oz": z["oz"], "title_path": [], "metric": METRIK, "value": z["menge"], "unit": z["einheit"]}
                 for z in zeilen if isinstance(z.get("menge"), (int, float)) and (z.get("einheit") or "").strip()]
    return {"quelle": quelle, "name": name, "positionen": zeilen, "measurements": messungen, "summe_gp": summe}


def _differenz(a, b):
    return round(b - a, 4) if isinstance(a, (int, float)) and isinstance(b, (int, float)) else None


def vergleiche(bericht_name: str, bericht: list[dict], abrechnung_name: str, abrechnung: list[dict]
               ) -> tuple[list[dict], list[dict], list[str]]:
    """Expected/actual rows over the union of OZs; one-sided OZs get `null` values on the other side + a warning."""
    warnungen: list[str] = []
    soll = _eindeutig("Report file", bericht_name, bericht, warnungen)
    ist = _eindeutig("Final bill", abrechnung_name, abrechnung, warnungen)
    erwartet, tatsaechlich = [], []
    for oz in [*soll, *(oz for oz in ist if oz not in soll)]:
        s, i = soll.get(oz), ist.get(oz)
        if s is None:
            warnungen.append(f"OZ {oz} is only in the final bill “{abrechnung_name}”, not in our estimate.")
            s = _zeile(oz, i["kurztext"], None, i["einheit"], None, None, fehlt=True)
        if i is None:
            warnungen.append(f"OZ {oz} is only in our estimate “{bericht_name}”, not in the final bill.")
            i = _zeile(oz, s["kurztext"], None, s["einheit"], None, None, fehlt=True)
        erwartet.append(s)
        tatsaechlich.append({**i, "menge_delta": _differenz(s["menge"], i["menge"]),
                             "gp_delta": _differenz(s["gp"], i["gp"])})
    return erwartet, tatsaechlich, warnungen


def _tags(db, text: str | None) -> list[str]:
    tags: list[str] = []
    for teil in (text or "").split(","):
        if teil.strip():
            try:
                tag = db.normalize_tag(teil)
            except ValueError:
                raise HTTPException(422, f"Invalid tag “{teil.strip()}”: each tag must be a single word "
                                         "without spaces (separate tags with commas).") from None
            if tag not in tags:
                tags.append(tag)
    return tags


def _metadaten(lv: LV, bericht_name: str, db) -> tuple[str, list[str]]:
    """Description/tags from the existing `/api/history/metadata` logic; deterministic fallback, never invented."""
    beschreibung, tags = f"Project close: {lv.name} ({len(lv.positionen)} items).", []
    try:
        from .ai.history_metadata import MetadataRequest, history_metadata
        antwort = history_metadata(MetadataRequest(lv=lv))
        beschreibung, tags = antwort.description or beschreibung, list(antwort.tags)
    except (ValidationError, HTTPException, ValueError):
        pass
    try:
        tags += db._extract_tags_from_filename(bericht_name)
    except ValueError:
        pass
    sauber: list[str] = []
    for t in tags:
        try:
            tag = db.normalize_tag(str(t))
        except ValueError:
            continue
        if tag not in sauber:
            sauber.append(tag)
    return beschreibung, sauber


async def _lesen(art: str, datei: UploadFile | None, feld: str) -> tuple[str, bytes]:
    if datei is None:
        raise HTTPException(422, f"{art} is missing: send it as multipart field “{feld}”.")
    try:
        inhalt = await datei.read(MAX_UPLOAD_BYTES + 1)
    finally:
        await datei.close()
    name = datei.filename or feld
    if len(inhalt) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"{art} “{name}” is too large (maximum 10 MiB).")
    if not inhalt:
        raise HTTPException(422, f"{art} “{name}” is empty.")
    return name, inhalt


def _speichern(db, beschreibung: str, tags: list[str], erwartet: dict, tatsaechlich: dict, notiz: str
               ) -> tuple[int, str]:
    """Insert into the 7-column `database` table (db/client.py schema); id = ms timestamp, always increasing."""
    datum = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with db._connect_history(read_only=False) as conn:
        hoechste = conn.execute("SELECT COALESCE(MAX(id), 0) FROM database").fetchone()[0]
        record_id = max(int(time.time() * 1000), int(hoechste) + 1)
        conn.execute(
            "INSERT INTO database (id, date, description, tags, expected_json, actual_json, note) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [record_id, datum, beschreibung, tags, json.dumps(erwartet, ensure_ascii=False),
             json.dumps(tatsaechlich, ensure_ascii=False), notiz],
        )
    return record_id, datum


@router.post("/api/db/abschluss", response_model=AbschlussRecord,
             responses={413: {"description": "A file is larger than 10 MiB."},
                        422: {"description": "A file is missing, empty, unsupported or unreadable; the "
                                             "message names the file."},
                        503: {"description": "The history database is not available."}})
async def abschluss(
    bericht: UploadFile | None = File(default=None, description="Our report (JSON export) or estimate bill"),
    abrechnung: UploadFile | None = File(default=None, description="The real final bill"),
    description: str | None = Form(default=None),
    tags: str | None = Form(default=None, description="Comma-separated, e.g. roof,timber"),
    note: str | None = Form(default=None, description="Notes/marks, e.g. problems that happened"),
) -> AbschlussRecord:
    bericht_name, bericht_inhalt = await _lesen("Report file", bericht, "bericht")
    abrechnung_name, abrechnung_inhalt = await _lesen("Final bill", abrechnung, "abrechnung")
    db = _db()
    gegebene_tags = _tags(db, tags)

    def verarbeiten() -> AbschlussRecord:
        try:
            lv_soll, soll = _parse("Report file", bericht_name, bericht_inhalt, BERICHT_ENDUNGEN)
            lv_ist, ist = _parse("Final bill", abrechnung_name, abrechnung_inhalt, ABRECHNUNG_ENDUNGEN)
        except _DateiFehler as exc:
            raise HTTPException(422, str(exc)) from None
        erwartet, tatsaechlich, warnungen = vergleiche(bericht_name, soll, abrechnung_name, ist)
        if not any(z.get("menge") is not None and not z.get("fehlt") for z in erwartet) \
                and not any(z.get("menge") is not None and not z.get("fehlt") for z in tatsaechlich):
            raise HTTPException(422, f"Neither “{bericht_name}” nor “{abrechnung_name}” contains items "
                                     "with quantities; no record was stored.")
        beschreibung, erzeugte_tags = _metadaten(lv_soll, bericht_name, db)
        beschreibung = (description or "").strip() or beschreibung
        record_tags = gegebene_tags or erzeugte_tags
        if not record_tags:
            warnungen.append("No tags given or generated: the record is only found through “recent”, "
                             "not through Report 2's tag search.")
        notiz = (note or "").strip()
        expected_json = _seite(bericht_name, lv_soll.name, erwartet)
        actual_json = _seite(abrechnung_name, lv_ist.name, tatsaechlich)
        try:
            record_id, datum = _speichern(db, beschreibung, record_tags, expected_json, actual_json, notiz)
        except Exception as exc:  # noqa: BLE001 – show the storage error instead of a bare 500
            raise HTTPException(503, f"The record could not be stored in the history database: {exc}") from None
        return AbschlussRecord(id=record_id, date=datum, description=beschreibung, tags=record_tags,
                               expected_json=expected_json, actual_json=actual_json, note=notiz,
                               warnungen=warnungen)

    return await run_in_threadpool(verarbeiten)

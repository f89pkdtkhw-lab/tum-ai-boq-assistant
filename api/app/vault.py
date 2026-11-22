"""Local document vault (t243/t247/t248): every document and result in one place, stored on this machine.

- Files: ``$LV_SCOUT_VAULT_DIR`` (default ``data/vault/`` in the repository, git-ignored) under ``dateien/``.
- Metadata: one JSON file ``index.json`` next to them (id, typ, dateiname, groesse, hash, hochgeladen_am,
  tags, projekt, besitzer, quelle, lv_schluessel, lv_name).
- Uploaded files (LV, regulation, price list, competitor-bid Excel) are de-duplicated by SHA-256 per type. Results (reports,
  research, price research, AI evaluation) are never de-duplicated: every run is a new version with a
  timestamp and a reference to its bill (``lv_schluessel``), older versions stay.

Routes: ``GET /api/vault`` (``?typ=``, ``?lv=``), ``POST /api/vault`` (multipart ``datei`` + ``typ``),
``GET /api/vault/{id}``, ``GET /api/vault/{id}/datei``, ``PATCH /api/vault/{id}``, ``DELETE /api/vault/{id}``.
All storage is local and shared by every account (demo); ``besitzer`` records the signed-in e-mail if the UI sends it.
Storing never breaks an import or an analysis: ``lege_ab``/``archiviere`` swallow and log errors (no content logged).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)
router = APIRouter(tags=["vault"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
DOKUMENT_TYPEN = ("lv", "regelwerk", "preisliste", "wettbewerb")
ERGEBNIS_TYPEN = ("bericht", "recherche", "preisrecherche", "auswertung")
Typ = Literal["lv", "regelwerk", "preisliste", "wettbewerb", "bericht", "recherche", "preisrecherche", "auswertung"]
_LOCK = threading.RLock()


class VaultEintrag(BaseModel):
    id: str
    typ: Typ
    dateiname: str
    groesse: int
    hash: str
    hochgeladen_am: str
    tags: list[str] = Field(default_factory=list)
    projekt: str | None = None
    besitzer: str | None = None
    quelle: str = "upload"
    lv_schluessel: str | None = None
    lv_name: str | None = None
    version: int | None = None


class VaultAenderung(BaseModel):
    dateiname: str | None = Field(default=None, min_length=1, max_length=200)
    tags: list[str] | None = None
    projekt: str | None = None


def vault_dir() -> Path:
    eigen = os.environ.get("LV_SCOUT_VAULT_DIR")
    return Path(eigen) if eigen else Path(__file__).resolve().parents[2] / "data" / "vault"


def _index_pfad() -> Path:
    return vault_dir() / "index.json"


def _lade() -> list[dict]:
    try:
        roh = json.loads(_index_pfad().read_text("utf-8"))
        return roh if isinstance(roh, list) else []
    except (OSError, ValueError):
        return []


def _speichere(eintraege: list[dict]) -> None:
    pfad = _index_pfad()
    pfad.parent.mkdir(parents=True, exist_ok=True)
    tmp = pfad.with_suffix(".tmp")
    tmp.write_text(json.dumps(eintraege, ensure_ascii=False, indent=1), "utf-8")
    tmp.replace(pfad)


def _datei_pfad(eintrag: dict) -> Path:
    endung = Path(eintrag["dateiname"]).suffix.lower()
    endung = endung if re.fullmatch(r"\.[a-z0-9]{1,6}", endung) else ""
    return vault_dir() / "dateien" / f"{eintrag['id']}{eintrag.get('endung', endung)}"


def _sauberer_name(name: str) -> str:
    name = Path(name or "").name.strip() or "dokument"
    return re.sub(r"[\x00-\x1f]", "", name)[:200]


def _besitzer(wert: str | None) -> str | None:
    wert = (wert or "").strip().lower()
    return wert if re.fullmatch(r"[^@\s]{1,64}@[^@\s]{1,190}", wert) else None


def lv_schluessel(lv: Any) -> str:
    """Stable reference to a bill: hash over name and items, the same at import and in the analysis."""
    try:
        daten = lv.model_dump(mode="json") if hasattr(lv, "model_dump") else dict(lv)
        kern = [daten.get("name"), [[p.get("oz"), p.get("kurztext"), p.get("menge"), p.get("einheit")]
                                    for p in daten.get("positionen") or []]]
        return hashlib.sha256(json.dumps(kern, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    except Exception:  # noqa: BLE001 - a reference must never break the caller
        return ""


def speichere(inhalt: bytes, dateiname: str, typ: str, *, besitzer: str | None = None, quelle: str = "upload",
              lv_key: str | None = None, lv_name: str | None = None, tags: list[str] | None = None,
              projekt: str | None = None) -> tuple[VaultEintrag, bool]:
    """Stores bytes; returns (entry, neu). Documents with the same hash and type return the existing entry."""
    if typ not in DOKUMENT_TYPEN + ERGEBNIS_TYPEN:
        raise ValueError(f"Unknown vault type: {typ}")
    digest = hashlib.sha256(inhalt).hexdigest()
    with _LOCK:
        eintraege = _lade()
        # t256: AI-read competitor workbooks are a new version each time (no hash-dedupe).
        if typ in DOKUMENT_TYPEN and quelle != "ki":
            for e in eintraege:
                if e["typ"] == typ and e["hash"] == digest and _datei_pfad(e).exists():
                    geaendert = False
                    if lv_key and not e.get("lv_schluessel"):
                        e["lv_schluessel"], e["lv_name"], geaendert = lv_key, lv_name, True
                    if geaendert:
                        _speichere(eintraege)
                    return VaultEintrag.model_validate(e), False
        version = None
        if typ in ERGEBNIS_TYPEN and lv_key:
            version = 1 + sum(1 for e in eintraege if e["typ"] == typ and e.get("lv_schluessel") == lv_key)
        elif typ == "wettbewerb" and quelle == "ki":
            version = 1 + sum(1 for e in eintraege if e["typ"] == typ and e.get("quelle") == "ki"
                              and (e.get("projekt") or "") == ((projekt or "").strip()))
        eintrag = {
            "id": secrets.token_hex(8), "typ": typ, "dateiname": _sauberer_name(dateiname), "groesse": len(inhalt),
            "hash": digest, "hochgeladen_am": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "tags": [t.strip() for t in tags or [] if t.strip()][:20], "projekt": (projekt or "").strip() or None,
            "besitzer": _besitzer(besitzer), "quelle": quelle, "lv_schluessel": lv_key or None,
            "lv_name": lv_name or None, "version": version,
        }
        pfad = _datei_pfad(eintrag)
        pfad.parent.mkdir(parents=True, exist_ok=True)
        pfad.write_bytes(inhalt)
        eintraege.append(eintrag)
        _speichere(eintraege)
    return VaultEintrag.model_validate(eintrag), True


def lege_ab(inhalt: bytes, dateiname: str, typ: str, **optionen) -> VaultEintrag | None:
    """Auto-filing from imports/analyses: never raises."""
    try:
        return speichere(inhalt, dateiname, typ, **optionen)[0]
    except Exception as exc:  # noqa: BLE001
        log.warning("Vault: could not store a %s document (%s)", typ, type(exc).__name__)
        return None


def archiviere(typ: str, daten: Any, titel: str, *, lv: Any = None, besitzer: str | None = None,
               quelle: str = "analyse", lv_name: str | None = None) -> VaultEintrag | None:
    """Stores one result as a new JSON version (no de-duplication)."""
    try:
        roh = daten.model_dump(mode="json") if hasattr(daten, "model_dump") else daten
        inhalt = json.dumps(roh, ensure_ascii=False, indent=1).encode()
        name = getattr(lv, "name", None) or lv_name
        stempel = datetime.now().strftime("%Y-%m-%d %H-%M-%S")
        dateiname = f"{titel} – {name} – {stempel}.json" if name else f"{titel} – {stempel}.json"
        return speichere(inhalt, dateiname, typ, besitzer=besitzer, quelle=quelle,
                         lv_key=lv_schluessel(lv) if lv is not None else None, lv_name=name)[0]
    except Exception as exc:  # noqa: BLE001
        log.warning("Vault: could not archive a %s result (%s)", typ, type(exc).__name__)
        return None


def archiviere_bericht(bericht: Any, lv: Any, besitzer: str | None = None) -> None:
    """Analysis report plus its research parts, each as its own version (t248)."""
    archiviere("bericht", bericht, "Analysebericht", lv=lv, besitzer=besitzer)
    if getattr(bericht, "recherche", None) is not None:
        archiviere("recherche", bericht.recherche, "Webrecherche", lv=lv, besitzer=besitzer)
    kalkulation = getattr(bericht, "kalkulation", None)
    if kalkulation is not None and any(p.treffer in ("index", "recherche") for p in kalkulation.positionen):
        archiviere("preisrecherche", kalkulation, "Preisrecherche", lv=lv, besitzer=besitzer)


def eintraege(typ: str | None = None, lv: str | None = None) -> list[VaultEintrag]:
    with _LOCK:
        liste = [VaultEintrag.model_validate(e) for e in _lade()]
    if typ:
        erlaubt = set(typ.split(","))
        liste = [e for e in liste if e.typ in erlaubt]
    if lv:
        liste = [e for e in liste if e.lv_schluessel == lv]
    return sorted(liste, key=lambda e: e.hochgeladen_am, reverse=True)


def _finde(eintrag_id: str) -> dict:
    for e in _lade():
        if e["id"] == eintrag_id:
            return e
    raise HTTPException(404, "Document not found in the vault.")


@router.get("/api/vault", response_model=list[VaultEintrag])
def liste(typ: str | None = Query(None), lv: str | None = Query(None)):
    return eintraege(typ, lv)


@router.post("/api/vault", response_model=VaultEintrag, status_code=201)
async def hochladen(datei: UploadFile, typ: Typ = Form(...), tags: str = Form(""), projekt: str = Form(""),
                    x_lv_scout_user: str | None = Header(None)):
    try:
        inhalt = await datei.read(MAX_UPLOAD_BYTES + 1)
    finally:
        await datei.close()
    if len(inhalt) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File is too large (maximum 10 MiB).")
    if not inhalt:
        raise HTTPException(422, "The uploaded file is empty.")
    eintrag, _ = speichere(inhalt, datei.filename or "dokument", typ, besitzer=x_lv_scout_user,
                           tags=[t for t in tags.split(",")], projekt=projekt)
    return eintrag


@router.get("/api/vault/{eintrag_id}", response_model=VaultEintrag)
def details(eintrag_id: str):
    with _LOCK:
        return VaultEintrag.model_validate(_finde(eintrag_id))


@router.get("/api/vault/{eintrag_id}/datei")
def herunterladen(eintrag_id: str):
    with _LOCK:
        eintrag = _finde(eintrag_id)
    pfad = _datei_pfad(eintrag)
    if not pfad.exists():
        raise HTTPException(404, "The stored file is missing.")
    art = "application/json" if pfad.suffix == ".json" else "application/octet-stream"
    return FileResponse(pfad, media_type=art, filename=eintrag["dateiname"])


@router.patch("/api/vault/{eintrag_id}", response_model=VaultEintrag)
def aendern(eintrag_id: str, aenderung: VaultAenderung):
    with _LOCK:
        alle = _lade()
        e = next((x for x in alle if x["id"] == eintrag_id), None)
        if e is None:
            raise HTTPException(404, "Document not found in the vault.")
        alt = _datei_pfad(e)
        if aenderung.dateiname is not None:
            e.setdefault("endung", alt.suffix)  # keep the stored file where it is
            e["dateiname"] = _sauberer_name(aenderung.dateiname)
        if aenderung.tags is not None:
            e["tags"] = [t.strip() for t in aenderung.tags if t.strip()][:20]
        if aenderung.projekt is not None:
            e["projekt"] = aenderung.projekt.strip() or None
        _speichere(alle)
        return VaultEintrag.model_validate(e)


@router.delete("/api/vault/{eintrag_id}", status_code=204)
def loeschen(eintrag_id: str):
    with _LOCK:
        alle = _lade()
        e = next((x for x in alle if x["id"] == eintrag_id), None)
        if e is None:
            raise HTTPException(404, "Document not found in the vault.")
        _datei_pfad(e).unlink(missing_ok=True)
        _speichere([x for x in alle if x["id"] != eintrag_id])

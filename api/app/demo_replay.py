"""Offline replay of one stored analysis (demo video without API key or AI costs).

Off unless ``DEMO_REPLAY`` names a directory (``python tools/dev.py --demo`` sets it to ``.demo-replay/``,
git-ignored). The directory holds an earlier real run, exported with ``tools/demo_fixture.py``:

    bericht.json     the Pruefbericht of that run (contains the bill under ``lv``)
    evaluation.json  the AI evaluation of that run (optional)

While it is on, a middleware answers the routes that would call a model or parse a document:
``/api/lv/import`` returns the stored bill, ``/api/lv/analyse/start`` starts a job that walks through the
pipeline's progress steps with short pauses and ends with the stored report, ``/api/lv/analyse`` and
``/api/lv/pruefen`` return it directly and ``/api/lv/ai-evaluation`` returns the stored evaluation.
``llm.status()`` reports the model of the stored run, and ``llm.complete`` refuses every call, so no
external AI request can leave the backend. Nothing in the UI changes. Without ``DEMO_REPLAY`` nothing changes.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from functools import lru_cache
from pathlib import Path

from fastapi import Request
from fastapi.responses import JSONResponse

log = logging.getLogger(__name__)


def verzeichnis() -> Path | None:
    roh = os.environ.get("DEMO_REPLAY", "").strip()
    if not roh or roh.lower() in ("0", "off", "false", "no"):
        return None
    return Path(roh).expanduser().resolve()


def aktiv() -> bool:
    return verzeichnis() is not None


@lru_cache(maxsize=4)
def _lade(pfad: str, name: str, mtime: float):
    return json.loads((Path(pfad) / name).read_text("utf-8"))


def lade(name: str):
    pfad = verzeichnis()
    if pfad is None or not (pfad / name).exists():
        return None
    return _lade(str(pfad), name, (pfad / name).stat().st_mtime)


def bericht() -> dict:
    daten = lade("bericht.json")
    if not isinstance(daten, dict) or "lv" not in daten:
        raise RuntimeError(f"DEMO_REPLAY: {verzeichnis()}/bericht.json is missing or has no 'lv'.")
    return daten


def sekunden() -> float:
    try:
        return max(1.0, float(os.environ.get("DEMO_REPLAY_SEKUNDEN", "45")))
    except ValueError:
        return 45.0


def _modell() -> tuple[str, str]:
    """Provider and model of the stored run, e.g. ("anthropic", "claude-sonnet-…")."""
    try:
        kennung = bericht().get("kennzahlen", {}).get("modell") or ""
    except Exception:
        kennung = ""
    provider, _, modell = str(kennung).partition("/")
    return (provider or "anthropic"), (modell or "claude-sonnet-4-5")


def status(keys: dict) -> dict:
    """What llm.status() reports in replay: the stored run's model, as if a key were configured."""
    provider, modell = _modell()
    return {"provider": provider, "model": modell, "mock": False, "keys": keys, "reason": None,
            "key_set": True, "key_source": "env"}


def _schritte(b: dict) -> list[tuple[int, str, str, float]]:
    """(step, start message, done message, share of the total time) along the real pipeline."""
    n = len(b["lv"].get("positionen") or [])
    findings = b.get("findings") or []
    llm_n = sum(1 for f in findings if str(f.get("id", "")).startswith("llm-"))
    risiko_n = sum(1 for f in findings if str(f.get("id", "")).startswith("RISK_"))
    norm_n = sum(1 for f in findings if str(f.get("id", "")).startswith("NORM"))
    provider, modell = _modell()
    rech = (b.get("recherche") or {}).get("meldung") or "done."
    return [
        (1, f"Running fixed rules on {n} items …", "Fixed rules checked.", 0.04),
        (2, "Checking quantities and units …", "Quantity checks done.", 0.04),
        (3, f"AI item review of {n} items with {provider}/{modell} …", f"AI item review: {llm_n} findings.", 0.22),
        (4, "Scoring risks and Nachtrag potential …", f"Risk scoring: {risiko_n} findings scored.", 0.06),
        (5, "Checking standards and regulations …", f"Standards check: {norm_n} findings.", 0.12),
        (6, "Building reports 1–3 (rules, comparison, what-if) …", f"Reports: {len(b.get('berichte') or [])} built.", 0.12),
        (7, "Adding assumptions and the final report …", "Assumptions and final report added.", 0.04),
        (8, "Pricing the bill (price list, price database) …", "Price calculation and estimated bill done.", 0.12),
        (9, "Web research: 2 group(s) (findings, prices, reports) …", f"Web research: {rech}", 0.24),
    ]


def _abspielen(fortschritt, mit_preis: bool):
    from .modelle import Pruefbericht  # noqa: PLC0415
    b = bericht()
    schritte = [s for s in _schritte(b) if mit_preis or s[0] != 8]
    gesamt = len(schritte)
    dauer = sekunden()
    for nummer, (_, start, fertig, anteil) in enumerate(schritte, 1):
        zeit = dauer * anteil
        fortschritt(nummer, gesamt, start, 0.0)
        teile = 4
        for k in range(1, teile):
            time.sleep(zeit / teile)
            fortschritt(nummer, gesamt, start, k / teile)
        time.sleep(zeit / teile)
        fortschritt(nummer, gesamt, fertig, 1.0)
    daten = dict(b)
    if not mit_preis:
        daten.pop("kalkulation", None)
        daten.pop("geschaetztes_lv", None)
    return Pruefbericht.model_validate(daten)


async def middleware(request: Request, call_next):
    if not aktiv() or request.method != "POST":
        return await call_next(request)
    pfad = request.url.path.rstrip("/")
    try:
        if pfad == "/api/lv/import":
            await request.body()
            await asyncio.sleep(1.5)
            return JSONResponse(bericht()["lv"])
        if pfad == "/api/lv/analyse/start":
            from . import analyse_job  # noqa: PLC0415
            try:
                body = json.loads(await request.body() or b"{}")
            except ValueError:
                body = {}
            mit_preis = not bool(body.get("nur_pruefen"))
            anzahl = 9 if mit_preis else 8
            job = analyse_job.starte(lambda f: _abspielen(f, mit_preis), anzahl)
            return JSONResponse({"job_id": job}, status_code=202)
        if pfad in ("/api/lv/analyse", "/api/lv/pruefen"):
            await request.body()
            await asyncio.sleep(2.0)
            return JSONResponse(_sofort(pfad == "/api/lv/analyse"))
        if pfad == "/api/lv/ai-evaluation":
            await request.body()
            daten = lade("evaluation.json")
            if isinstance(daten, dict):
                await asyncio.sleep(min(6.0, sekunden() / 8))
                return JSONResponse(daten)
    except Exception as exc:  # a broken fixture must show up as a normal error, not a crash
        log.exception("DEMO_REPLAY failed for %s", pfad)
        return JSONResponse({"detail": f"{type(exc).__name__}: {exc}"}, status_code=500)
    return await call_next(request)


def _sofort(mit_preis: bool) -> dict:
    daten = dict(bericht())
    if not mit_preis:
        daten.pop("kalkulation", None)
        daten.pop("geschaetztes_lv", None)
    return daten

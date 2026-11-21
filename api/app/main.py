"""BoQ review API: import → fixed rules → model review (configured provider, else offline mock) → report."""
import json
import os
from pathlib import Path
from starlette.concurrency import run_in_threadpool
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ValidationError
from .ai import llm
from .ai.step_api import router as comparison_router
from .ai.history_metadata import router as metadata_router
from .lv.importer import importiere
from .modelle import Beispiel, Beispiele, Kennzahlen, LV, Pruefbericht
from .modelle import Preisliste  # B6 #112
from .pruefung.preise import kalkuliere_mit_preis_db  # B6 #112, B9 #133
from .pruefung.regeln import pruefe_regeln
from .pruefung.mengen import pruefe_mengen
from .pruefung.llm_pruefung import pruefe_mit_llm, pruefe_mit_llm_status  # noqa: F401 (pruefe_mit_llm: golden tests)
from .pruefung.normen import ergaenze_annahmen, pruefe_normen_sicher  # B4 #97: ergaenze_annahmen
from .pruefung.bewertung import zusammenfassen
from .pruefung.berichte import ergaenze_berichte  # B5 (#98)
from .pruefung.geschaetztes_lv import ergaenze_geschaetztes_lv  # B8 #114
from .modelle import Regelwerk  # B3 (#96)
from .pruefung.regelwerk import importiere_regelwerk  # B3 (#96)
from .pruefung.normen import vorgaben_aus_regelwerk  # B3 (#96)
from .risiko.scoring import bewerte

from .ai import step_api
import logging
import sys

# db/ lives in the repository root; uvicorn runs from api/, so make it importable.
_REPO_ROOT = str(Path(__file__).resolve().parents[2])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

if "pytest" not in sys.modules:  # #147: keys come from .env.local (never in tests; environment variables win)
    llm.load_env_file(Path(_REPO_ROOT) / ".env.local")

try:
    from db.client import DB_PATH
    from db.history_adapter import get_history_records

    if "pytest" not in sys.modules and Path(DB_PATH).exists():
        step_api.history_service = get_history_records
except Exception:
    pass



ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
app = FastAPI(title="BoQ Review Assistant", version="0.2.0")
app.include_router(comparison_router)
app.include_router(metadata_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[s.strip() for s in os.environ.get("WEB_ORIGINS", "http://localhost:3000").split(",") if s.strip()],
    allow_methods=["GET", "POST"], allow_headers=["Content-Type"],
)
try:
    from db.client import router as db_router
    app.include_router(db_router)
except Exception as exc:  # the optional DB service must not stop the API from starting
    logging.getLogger(__name__).warning("DB router not mounted: %s", exc)

# Project close → history record (D3, #154): POST /api/db/abschluss; the DB itself is imported lazily.
from .abschluss_api import router as abschluss_router  # noqa: E402
app.include_router(abschluss_router)

# Price list upload, price DB page and the B9 price seam (#153): routes live in preis_api.py.
from .preis_api import einbinden as preis_api_einbinden  # noqa: E402
preis_api_einbinden(app)

class Question(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    use_data: bool = True


def load_examples():
    return [Beispiel(id="synthetisch-rohbau", titel="Synthetic structural works BoQ",
                     beschreibung="30 items, 3 sections, 5 seeded errors; domain rules follow. "
                                 "The model review uses the configured provider, otherwise the offline mock.",
                     lv=LV.model_validate_json((DATA / "beispiel_lv.json").read_bytes()))]


@app.get("/health")
def health():
    """Provider and model the BoQ pipeline uses; `mock: true` without a usable key (`reason` says why)."""
    return {"ok": True, **llm.status()}


@app.get("/api/beispiele", response_model=Beispiele)
def examples():
    return Beispiele(items=load_examples())


@app.post("/api/lv/import", response_model=LV)
async def import_lv(datei: UploadFile):
    try:
        inhalt = await datei.read(MAX_UPLOAD_BYTES + 1)
        if len(inhalt) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "File is too large (maximum 10 MiB).")
        if not inhalt:
            raise HTTPException(422, "The uploaded file is empty.")
        # Synchronous parsers (PDF especially) must not block the event loop.
        return await run_in_threadpool(importiere, datei.filename or "", inhalt)
    except ValidationError:
        raise HTTPException(422, "Invalid BoQ JSON. Please use the documented BoQ contract.") from None
    except NotImplementedError as exc:
        raise HTTPException(501, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    finally:
        await datei.close()


@app.post("/api/lv/pruefen", response_model=Pruefbericht)
def pruefen(lv: LV):
    return _pruefbericht(lv)


def _pruefbericht(lv: LV, vorgaben=None):
    """`vorgaben`: requirements of the uploaded regulation document (B3 #96) for check 1; None = as before."""
    modell = pruefe_mit_llm_status(lv)  # #147: never raises; falls back to the mock with a reason
    findings = (bewerte(lv, pruefe_regeln(lv) + pruefe_mengen(lv) + modell.findings)
                + (pruefe_normen_sicher(lv) if vorgaben is None else pruefe_normen_sicher(lv, vorgaben=vorgaben)))
    return ergaenze_annahmen(ergaenze_berichte(Pruefbericht(lv=lv, findings=findings, kennzahlen=Kennzahlen(
        positionen=len(lv.positionen), findings=len(findings),
        kritisch=sum(f.schwere == "kritisch" for f in findings), modell_mock=modell.mock,
        modell_reason=modell.reason, modell=None if modell.mock else f"{modell.provider}/{modell.model}",
    ), zusammenfassung=zusammenfassen(findings))))


class AnalyseAnfrage(BaseModel):
    """Body of POST /api/lv/analyse (epic #93): `regelwerk` from B3 (#96), `preisliste` from B6 (#112)."""
    lv: LV
    regelwerk: Regelwerk | None = None  # B3 #96
    preisliste: Preisliste | None = None  # B6 #112


# --- Regulation document (B3, issue #96): upload + analysis with the uploaded key values. ---
@app.post("/api/regelwerk/import", response_model=Regelwerk)
async def import_regelwerk(datei: UploadFile):
    try:
        inhalt = await datei.read(MAX_UPLOAD_BYTES + 1)
        if len(inhalt) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "File is too large (maximum 10 MiB).")
        if not inhalt:
            raise HTTPException(422, "The uploaded file is empty.")
        return importiere_regelwerk(datei.filename or "", inhalt)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    finally:
        await datei.close()


@app.post("/api/lv/analyse", response_model=Pruefbericht)
def analyse(anfrage: AnalyseAnfrage):
    """`/api/lv/pruefen` plus check 1 with the uploaded regulation document (B3, via B2's `vorgaben`) and
    the price list (B6); `regelwerk: null` and no `preisliste` = identical result."""
    vorgaben = vorgaben_aus_regelwerk(anfrage.regelwerk)  # B3 #96 -> B2 check 1 (lower/bigger/missing/extra)
    bericht = _pruefbericht(anfrage.lv, vorgaben)
    # B6 #112 / B9 #133: upload first, price database fills the gaps; no price source → no `kalkulation` field
    bericht.kalkulation = kalkuliere_mit_preis_db(anfrage.lv, anfrage.preisliste)
    if bericht.kalkulation is not None:  # B8 #114: adjustments + estimated bill, only with a price source
        bericht = ergaenze_geschaetztes_lv(bericht, anfrage.preisliste)
    return bericht


@app.post("/api/ask")
def ask(body: Question):
    """Starter route: the configured model answers; on a missing key, error or timeout the mock (with `reason`)."""
    context = json.dumps([e.model_dump() for e in load_examples()], ensure_ascii=False)[:6000] if body.use_data else ""
    prompt = body.question if not context else f"Data:\n{context}\n\nQuestion: {body.question}"
    answer = llm.complete_with_fallback(prompt, timeout=llm.seconds("LLM_REVIEW_TIMEOUT", 60))
    return {"answer": answer.text, "provider": answer.provider, "model": answer.model, "ms": answer.ms,
            "mock": answer.provider == "mock", "reason": answer.reason}

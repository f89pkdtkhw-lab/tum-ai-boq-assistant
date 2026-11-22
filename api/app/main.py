"""BoQ review API: import → fixed rules → model review (configured provider, else offline mock) → report."""
import json
import os
from pathlib import Path
from starlette.concurrency import run_in_threadpool
from fastapi import FastAPI, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ValidationError
from .ai import llm
from .ai.step_api import router as comparison_router
from .ai.history_metadata import router as metadata_router
from .ai.evaluation import router as evaluation_router
from .ai.submission import router as submission_router
from .ai.uebersetzen import router as uebersetzen_router
from .ai.sprache import Antwortsprache  # #196
from .lv.importer import importiere
from .modelle import Beispiel, Beispiele, Kennzahlen, LV, Pruefbericht
from .modelle import Preisliste  # B6 #112
from .pruefung.preise import kalkuliere_mit_preis_db  # B6 #112, B9 #133
from .pruefung.preis_fallback import ergaenze_recherchepreise  # t237
from .pruefung.regeln import pruefe_regeln
from .pruefung.mengen import pruefe_mengen
from .pruefung.llm_pruefung import pruefe_mit_llm, pruefe_mit_llm_status  # noqa: F401 (pruefe_mit_llm: golden tests)
from .pruefung.normen import ergaenze_annahmen, pruefe_normen_sicher  # B4 #97: ergaenze_annahmen
from .pruefung.normen_ki import starte_recherche as starte_normrecherche  # #166
from .pruefung.normen import ergaenze_note2  # #167: Note 2 (register_als_quellen) in the analysis path
from .pruefung.bewertung import Bewertungsmodell, DEFAULT_MODELL, zusammenfassen
from .pruefung.berichte import ergaenze_berichte  # B5 (#98)
from .pruefung.geschaetztes_lv import ergaenze_geschaetztes_lv  # B8 #114
from .modelle import Regelwerk  # B3 (#96)
from .pruefung.regelwerk import importiere_regelwerk  # B3 (#96)
from .pruefung.normen import vorgaben_aus_regelwerk  # B3 (#96)
from .risiko.scoring import bewerte
from . import analyse_job  # #165: background analysis jobs
from .fortschritt import OHNE_FORTSCHRITT, Fortschritt  # #165: progress API
from .fortschritt import teilschritt  # #166: N5 research rounds report under step 5
from .pruefung.recherche import aktiv as recherche_aktiv, vertiefe_recherche  # E #169: deep web research

from .ai import step_api
from .ai import ki_status  # D #168
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
app.include_router(evaluation_router)
app.include_router(submission_router)
app.include_router(uebersetzen_router)
app.add_middleware(Antwortsprache)  # #196: answer language from the UI cookie
app.add_middleware(
    CORSMiddleware,
    allow_origins=[s.strip() for s in os.environ.get("WEB_ORIGINS", "http://localhost:3000").split(",") if s.strip()],
    allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["Content-Type", "X-LV-Scout-User"],
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

from .db_seams import verbinde_history_db  # #155: Reports 2/3 ← history DB
verbinde_history_db()

from .ai.schluessel import router as key_router  # #156: enter the Claude API key in the UI
app.include_router(key_router)
from .ai.dev_options import router as dev_options_router  # developer options + Grok Bot mode
app.include_router(dev_options_router)
from . import vault  # noqa: E402  t243: local document vault (data/vault/, git-ignored)
app.include_router(vault.router)
from .marge_pdf import router as marge_pdf_router  # noqa: E402  t256: AI competitor PDF → margin Excel
app.include_router(marge_pdf_router)

class Question(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    use_data: bool = True


def load_examples():
    return [Beispiel(id="synthetisch-rohbau", titel="Synthetic structural works BoQ",
                     beschreibung="30 items, 3 sections, 5 seeded errors; domain rules follow. "
                                 "The model review uses the configured provider, otherwise the offline mock.",
                     lv=LV.model_validate_json((DATA / "beispiel_lv.json").read_bytes())),
            Beispiel(id="synthetisch-sauber", titel="Clean BoQ (office building)",
                     beschreibung="About 300 items, almost no errors: shows what a good BoQ looks like. Generated by tools/beispiel_gross.py.",
                     lv=LV.model_validate_json((DATA / "beispiel_lv_sauber.json").read_bytes())),
            Beispiel(id="synthetisch-mittel", titel="Medium BoQ (apartment building)",
                     beschreibung="About 770 items, some errors, price outliers and outdated standards. Generated by tools/beispiel_gross.py.",
                     lv=LV.model_validate_json((DATA / "beispiel_lv_mittel.json").read_bytes())),
            Beispiel(id="synthetisch-gross", titel="Large synthetic BoQ (housing estate)",
                     beschreibung="About 2,500 items, 3 buildings × 12 trades, ~4 % seeded errors; generated by tools/beispiel_gross.py.",
                     lv=LV.model_validate_json((DATA / "beispiel_lv_gross.json").read_bytes()))]


@app.get("/health")
def health():
    """Provider and model the BoQ pipeline uses; `mock: true` without a usable key (`reason` says why)."""
    return {"ok": True, **llm.status()}


@app.get("/api/beispiele", response_model=Beispiele)
def examples():
    return Beispiele(items=load_examples())


@app.post("/api/lv/import", response_model=LV)
async def import_lv(datei: UploadFile, x_lv_scout_user: str | None = Header(None)):
    try:
        inhalt = await datei.read(MAX_UPLOAD_BYTES + 1)
        if len(inhalt) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "File is too large (maximum 10 MiB).")
        if not inhalt:
            raise HTTPException(422, "The uploaded file is empty.")
        # Synchronous parsers (PDF especially) must not block the event loop.
        lv = await run_in_threadpool(importiere, datei.filename or "", inhalt)
        # t247: a bill used in an analysis is filed in the vault (same file = same entry).
        vault.lege_ab(inhalt, datei.filename or "lv", "lv", besitzer=x_lv_scout_user, quelle="analyse",
                      lv_key=vault.lv_schluessel(lv), lv_name=lv.name)
        return lv
    except ValidationError:
        raise HTTPException(422, "Invalid BoQ JSON. Please use the documented BoQ contract.") from None
    except NotImplementedError as exc:
        raise HTTPException(501, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    finally:
        await datei.close()


@app.post("/api/lv/pruefen", response_model=Pruefbericht)
def pruefen(lv: LV, bewertungsmodell: Bewertungsmodell = Query(DEFAULT_MODELL), x_lv_scout_user: str | None = Header(None)):
    bericht = _pruefen(lv, bewertungsmodell=bewertungsmodell)
    vault.archiviere_bericht(bericht, lv, x_lv_scout_user)  # t248: every run is a new version
    return bericht


def _recherche_schritte() -> int:
    """E #169: deep research is one more progress step, counted only when it runs (Claude with a key)."""
    return 1 if recherche_aktiv()[0] else 0


def _pruefen(lv: LV, fortschritt: Fortschritt | None = None, bewertungsmodell: Bewertungsmodell = DEFAULT_MODELL):
    """The /api/lv/pruefen pipeline plus deep research (E #169; unchanged without a Claude key)."""
    gesamt = PRUEF_SCHRITTE + _recherche_schritte()
    bericht = _pruefbericht(lv, fortschritt=fortschritt, gesamt=gesamt, bewertungsmodell=bewertungsmodell)
    return vertiefe_recherche(bericht, fortschritt=fortschritt, schritt=gesamt, gesamt=gesamt)


PRUEF_SCHRITTE = 7  # #165: steps of `_pruefbericht`; `_analyse` adds the price calculation as step 8


def _pruefbericht(lv: LV, vorgaben=None, fortschritt: Fortschritt | None = None, gesamt: int = PRUEF_SCHRITTE,
                   bewertungsmodell: Bewertungsmodell = DEFAULT_MODELL):
    """`vorgaben`: requirements of the uploaded regulation document (B3 #96) for check 1; None = as before.
    `fortschritt` (#165): progress callback of a background job (see fortschritt.py); None = no reports."""
    melde = fortschritt or OHNE_FORTSCHRITT
    n = len(lv.positionen)
    starte_normrecherche(lv)  # #166: N5 web research runs in the background, parallel to the item review
    with ki_status.erfasse() as ki_schritte:  # D #168: every AI step reports how it ran (failures stay visible)
        melde(1, gesamt, f"Running fixed rules on {n} items …")
        regeln = pruefe_regeln(lv)
        melde(1, gesamt, f"Fixed rules: {len(regeln)} findings.", 1.0)
        melde(2, gesamt, "Checking quantities and units …")
        mengen = pruefe_mengen(lv)
        melde(2, gesamt, f"Quantity checks: {len(mengen)} findings.", 1.0)
        ki = llm.status()
        melde(3, gesamt, f"AI item review of {n} items with {ki['provider']}/{ki['model']} …" if not ki["mock"]
              else f"AI item review of {n} items (without AI model) …")
        if fortschritt is None:  # #147/#167: never raises; failed batches are named, partial results kept
            modell = pruefe_mit_llm_status(lv)
        else:  # #167: progress per model batch inside step 3
            modell = pruefe_mit_llm_status(lv, fortschritt=lambda fertig, alle: melde(
                3, gesamt, f"AI item review: batch {fertig} of {alle} done …", fertig / alle))
        _melde_positionspruefung(modell)
        if modell.fehlgeschlagen:
            melde.fehler(f"AI item review: {modell.reason}")
        melde(3, gesamt, f"AI item review: {len(modell.findings)} findings{' (without AI model)' if modell.mock else ''}.", 1.0)
        melde(4, gesamt, "Scoring risks and Nachtrag potential …")
        bewertet = bewerte(lv, regeln + mengen + modell.findings)
        melde(4, gesamt, f"Risk scoring: {len(bewertet)} findings scored.", 1.0)
        melde(5, gesamt, "Checking standards and regulations …" if vorgaben is None
              else "Checking standards against the uploaded regulation document …")
        normen = pruefe_normen_sicher(lv, **_normen_optionen(vorgaben, fortschritt, gesamt))
        melde(5, gesamt, f"Standards check: {len(normen)} findings.", 1.0)
        findings = bewertet + normen
        melde(6, gesamt, "Building reports 1–3 (rules, comparison, what-if) …")
        bericht = ergaenze_berichte(Pruefbericht(lv=lv, findings=findings, kennzahlen=Kennzahlen(
            positionen=len(lv.positionen), findings=len(findings),
            kritisch=sum(f.schwere == "kritisch" for f in findings), modell_mock=modell.mock,
            modell_reason=modell.reason, modell=None if modell.mock else f"{modell.provider}/{modell.model}",
            modell_batches=None if modell.mock else modell.batches,  # #167
            modell_batches_fehlgeschlagen=None if modell.mock else modell.fehlgeschlagen,
        ), zusammenfassung=zusammenfassen(findings, n_positionen=len(lv.positionen), modell=bewertungsmodell)))
        melde(6, gesamt, f"Reports: {len(bericht.berichte or [])} built.", 1.0)
        melde(7, gesamt, "Adding assumptions and the final report …")
        bericht = ergaenze_note2(ergaenze_annahmen(bericht))  # #167: Note 2 from the norm register
        melde(7, gesamt, "Assumptions and final report added.", 1.0)
    bericht.ki_schritte = ki_status.ergebnis(ki_schritte)
    return bericht


def _normen_optionen(vorgaben, fortschritt, gesamt) -> dict:
    """Keyword arguments of `pruefe_normen_sicher`: the regulation document (B3) and, in a job, the progress of
    the N5 research rounds (#166) under step 5; none when absent, so a plain `pruefe_normen_sicher(lv)` stays."""
    optionen = {} if vorgaben is None else {"vorgaben": vorgaben}
    if fortschritt is not None:
        optionen["melde"] = teilschritt(fortschritt, 5, gesamt)
    return optionen


def _melde_positionspruefung(modell) -> None:
    """D #168: the position review's outcome as a step status; a mock chosen by configuration reports nothing.
    #167: failed batches (partial results kept) are reported as `fehler` with the batches named."""
    if not modell.mock and modell.fehlgeschlagen:
        ki_status.melde("positionspruefung", "fehler", modell.reason, modell=f"{modell.provider}/{modell.model}")
    elif not modell.mock:
        ki_status.melde("positionspruefung", "ok", f"{modell.batches} batch(es) reviewed by the model.",
                        modell=f"{modell.provider}/{modell.model}")
    elif modell.reason:
        ki_status.melde("positionspruefung", "mock", modell.reason)


class AnalyseAnfrage(BaseModel):
    """Body of POST /api/lv/analyse (epic #93): `regelwerk` from B3 (#96), `preisliste` from B6 (#112)."""
    lv: LV
    regelwerk: Regelwerk | None = None  # B3 #96
    preisliste: Preisliste | None = None  # B6 #112
    bewertungsmodell: Bewertungsmodell = DEFAULT_MODELL


# --- Regulation document (B3, issue #96): upload + analysis with the uploaded key values. ---
@app.post("/api/regelwerk/import", response_model=Regelwerk)
async def import_regelwerk(datei: UploadFile, x_lv_scout_user: str | None = Header(None)):
    try:
        inhalt = await datei.read(MAX_UPLOAD_BYTES + 1)
        if len(inhalt) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "File is too large (maximum 10 MiB).")
        if not inhalt:
            raise HTTPException(422, "The uploaded file is empty.")
        regelwerk = importiere_regelwerk(datei.filename or "", inhalt)
        vault.lege_ab(inhalt, datei.filename or "regelwerk", "regelwerk", besitzer=x_lv_scout_user, quelle="analyse")
        return regelwerk
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    finally:
        await datei.close()


@app.post("/api/lv/analyse", response_model=Pruefbericht)
def analyse(anfrage: AnalyseAnfrage, x_lv_scout_user: str | None = Header(None)):
    """`/api/lv/pruefen` plus check 1 with the uploaded regulation document (B3, via B2's `vorgaben`) and
    the price list (B6); `regelwerk: null` and no `preisliste` = identical findings, plus the price DB
    calculation and estimated bill whenever the price database has prices (#167: the UI always uses it)."""
    bericht = _analyse(anfrage)
    vault.archiviere_bericht(bericht, anfrage.lv, x_lv_scout_user)  # t248
    return bericht


def _analyse(anfrage: AnalyseAnfrage, fortschritt: Fortschritt | None = None):
    melde = fortschritt or OHNE_FORTSCHRITT
    preis_schritt = PRUEF_SCHRITTE + 1
    gesamt = preis_schritt + _recherche_schritte()  # E #169: + deep research when it runs
    vorgaben = vorgaben_aus_regelwerk(anfrage.regelwerk)  # B3 #96 -> B2 check 1 (lower/bigger/missing/extra)
    bericht = _pruefbericht(anfrage.lv, vorgaben, fortschritt, gesamt, bewertungsmodell=anfrage.bewertungsmodell)
    # B6 #112 / B9 #133: upload first, price database fills the gaps; no price source → no `kalkulation` field
    melde(preis_schritt, gesamt, "Pricing the bill (price list, price database) …")
    bericht.kalkulation = kalkuliere_mit_preis_db(anfrage.lv, anfrage.preisliste)  # + index price fallback
    if bericht.kalkulation is not None and any(k.treffer == "kein_treffer" for k in bericht.kalkulation.positionen):
        melde(preis_schritt, gesamt, "Researching prices for items without a price …", 0.5)
        bericht.kalkulation = ergaenze_recherchepreise(bericht.kalkulation, anfrage.lv)  # t237: web research
    if bericht.kalkulation is not None:  # B8 #114: adjustments + estimated bill, only with a price source
        bericht = ergaenze_geschaetztes_lv(bericht, anfrage.preisliste)
    melde(preis_schritt, gesamt, "Price calculation: no price source." if bericht.kalkulation is None
          else "Price calculation and estimated bill done.", 1.0)
    return vertiefe_recherche(bericht, fortschritt=fortschritt, schritt=gesamt, gesamt=gesamt)  # E #169


# --- Background analysis job with progress (#165, package F) ---------------------------------------
class AnalyseJobAnfrage(AnalyseAnfrage):
    """Body of POST /api/lv/analyse/start: like /api/lv/analyse; `nur_pruefen: true` runs the
    /api/lv/pruefen pipeline instead (bill only, no price calculation), exactly as the sync route."""
    nur_pruefen: bool = False


@app.post("/api/lv/analyse/start", response_model=analyse_job.AnalyseStart, status_code=202)
def analyse_start(anfrage: AnalyseJobAnfrage, x_lv_scout_user: str | None = Header(None)):
    """Starts the analysis in a background thread and answers at once; poll …/status/{job_id}."""
    if anfrage.nur_pruefen:
        lauf, gesamt = (lambda f: _pruefen(anfrage.lv, f, bewertungsmodell=anfrage.bewertungsmodell)), PRUEF_SCHRITTE + _recherche_schritte()  # E #169
    else:
        lauf, gesamt = (lambda f: _analyse(anfrage, f)), PRUEF_SCHRITTE + 1 + _recherche_schritte()

    def arbeit(f):
        bericht = lauf(f)
        vault.archiviere_bericht(bericht, anfrage.lv, x_lv_scout_user)  # t248: new version per run, no cache
        return bericht
    try:
        return analyse_job.AnalyseStart(job_id=analyse_job.starte(arbeit, gesamt))
    except analyse_job.ZuVieleJobs as exc:
        raise HTTPException(429, str(exc)) from None


@app.get("/api/lv/analyse/status/{job_id}", response_model=analyse_job.AnalyseStatus)
def analyse_status(job_id: str):
    """`{status, schritt, schritte_gesamt, prozent, meldung, fertige_schritte[], fehler[], ergebnis?}`."""
    stand = analyse_job.status(job_id)
    if stand is None:
        raise HTTPException(404, "Unknown or expired analysis job. Please start the analysis again.")
    return stand


@app.post("/api/ask")
def ask(body: Question):
    """Starter route: the configured model answers; on a missing key, error or timeout the mock (with `reason`)."""
    context = json.dumps([e.model_dump() for e in load_examples()], ensure_ascii=False)[:6000] if body.use_data else ""
    prompt = body.question if not context else f"Data:\n{context}\n\nQuestion: {body.question}"
    answer = llm.complete_with_fallback(prompt, timeout=llm.seconds("LLM_REVIEW_TIMEOUT", 60))
    return {"answer": answer.text, "provider": answer.provider, "model": answer.model, "ms": answer.ms,
            "mock": answer.provider == "mock", "reason": answer.reason}

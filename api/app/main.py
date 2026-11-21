"""Offline kickoff API: import → fixed rules → model mock → report."""
import json
import os
from pathlib import Path
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ValidationError
from .ai import llm
from .ai.step_api import router as comparison_router
from .ai.history_metadata import router as metadata_router
from .lv.importer import importiere
from .modelle import Beispiel, Beispiele, Kennzahlen, LV, Pruefbericht
from .modelle import Preisliste  # B6 #112
from .pruefung.preise import kalkuliere  # B6 #112
from .pruefung.regeln import pruefe_regeln
from .pruefung.mengen import pruefe_mengen
from .pruefung.llm_pruefung import pruefe_mit_llm
from .pruefung.normen import pruefe_normen_sicher
from .pruefung.bewertung import zusammenfassen
from .risiko.scoring import bewerte

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


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    use_data: bool = True


def load_examples():
    return [Beispiel(id="synthetisch-rohbau", titel="Synthetic structural works BoQ",
                     beschreibung="30 items, 3 sections, 5 seeded errors; domain rules follow. The model is a mock.",
                     lv=LV.model_validate_json((DATA / "beispiel_lv.json").read_bytes()))]


@app.get("/health")
def health():
    # The BoQ pipeline always uses a mock, regardless of any available API keys.
    return {"ok": True, "provider": "mock", "model": "offline-lv-mock", "mock": True,
            "keys": {name: False for name in ("anthropic", "openai", "azure", "gemini")}}


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
        return importiere(datei.filename or "", inhalt)
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
    findings = bewerte(lv, pruefe_regeln(lv) + pruefe_mengen(lv) + pruefe_mit_llm(lv)) + pruefe_normen_sicher(lv)
    return Pruefbericht(lv=lv, findings=findings, kennzahlen=Kennzahlen(
        positionen=len(lv.positionen), findings=len(findings),
        kritisch=sum(f.schwere == "kritisch" for f in findings), modell_mock=True,
    ), zusammenfassung=zusammenfassen(findings))


class AnalyseAnfrage(BaseModel):
    """Body of POST /api/lv/analyse (epic #93). B3 (#96) types and evaluates `regelwerk`."""
    lv: LV
    regelwerk: dict | None = None
    preisliste: Preisliste | None = None  # B6 #112


@app.post("/api/lv/analyse", response_model=Pruefbericht)
def analyse(anfrage: AnalyseAnfrage):
    bericht = pruefen(anfrage.lv)
    if anfrage.preisliste is not None:  # B6 #112: no price list → no `kalkulation` field
        bericht.kalkulation = kalkuliere(anfrage.lv, anfrage.preisliste)
    return bericht


@app.post("/api/ask")
def ask(body: Question):
    """The existing starter route remains compatible and also uses only the mock."""
    context = json.dumps([e.model_dump() for e in load_examples()], ensure_ascii=False)[:6000] if body.use_data else ""
    prompt = body.question if not context else f"Data:\n{context}\n\nQuestion: {body.question}"
    answer = llm.mock(prompt)
    return {"answer": answer.text, "provider": answer.provider, "model": answer.model, "ms": answer.ms}

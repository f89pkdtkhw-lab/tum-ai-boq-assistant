"""Offline-Kickoff-API: Import → feste Regeln → Modell-Mock → Bericht."""
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
from .pruefung.regeln import pruefe_regeln
from .pruefung.mengen import pruefe_mengen
from .pruefung.llm_pruefung import pruefe_mit_llm
from .risiko.scoring import bewerte

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
app = FastAPI(title="LV-Prüfassistent", version="0.2.0")
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
    return [Beispiel(id="synthetisch-rohbau", titel="Synthetisches Rohbau-LV",
                     beschreibung="30 Positionen, 3 Titel, 5 eingebaute Fehler; Fachregeln folgen. Modell ist Mock.",
                     lv=LV.model_validate_json((DATA / "beispiel_lv.json").read_bytes()))]


@app.get("/health")
def health():
    # Die LV-Pipeline ist unabhängig von eventuell vorhandenen API-Schlüsseln immer Mock.
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
            raise HTTPException(413, "Datei ist zu groß (maximal 10 MiB).")
        if not inhalt:
            raise HTTPException(422, "Die hochgeladene Datei ist leer.")
        return importiere(datei.filename or "", inhalt)
    except ValidationError:
        raise HTTPException(422, "Ungültiges LV-JSON. Bitte den dokumentierten LV-Vertrag verwenden.") from None
    except NotImplementedError as exc:
        raise HTTPException(501, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    finally:
        await datei.close()


@app.post("/api/lv/pruefen", response_model=Pruefbericht)
def pruefen(lv: LV):
    findings = bewerte(lv, pruefe_regeln(lv) + pruefe_mengen(lv) + pruefe_mit_llm(lv))
    return Pruefbericht(lv=lv, findings=findings, kennzahlen=Kennzahlen(
        positionen=len(lv.positionen), findings=len(findings),
        kritisch=sum(f.schwere == "kritisch" for f in findings), modell_mock=True,
    ))


@app.post("/api/ask")
def ask(body: Question):
    """Bestehende Starterroute bleibt kompatibel, aber verwendet ebenfalls nur den Mock."""
    context = json.dumps([e.model_dump() for e in load_examples()], ensure_ascii=False)[:6000] if body.use_data else ""
    prompt = body.question if not context else f"Daten:\n{context}\n\nFrage: {body.question}"
    answer = llm.mock(prompt)
    return {"answer": answer.text, "provider": answer.provider, "model": answer.model, "ms": answer.ms}

"""Backend des Wettbewerbsprodukts. Start: python tools/dev.py (oder uvicorn app.main:app --reload in api/).

Die Beispiel-Route /api/ask zeigt den ganzen Weg: Eingabe prüfen, Daten laden, Modell fragen, Antwort mit
Herkunft zurückgeben. Nach dem Kickoff ersetzen die Agenten sie durch die Routen des Cases.
"""
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .ai import llm

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env.local")
load_dotenv(ROOT / ".env")
DATA = ROOT / "data"

app = FastAPI(title="TUM.ai Hackathon Produkt-API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.environ.get("WEB_ORIGINS", "http://localhost:3000").split(",") if origin.strip()],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    use_data: bool = True


def load_examples():
    path = DATA / "beispiele.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []


@app.get("/health")
def health():
    return {"ok": True, **llm.config()}


@app.get("/api/beispiele")
def examples():
    return {"items": load_examples()}


@app.post("/api/ask")
def ask(body: Question):
    context = json.dumps(load_examples(), ensure_ascii=False)[:6000] if body.use_data else ""
    system = "Du bist der Assistent unseres Hackathon-Produkts. Antworte knapp, konkret und auf Deutsch."
    prompt = body.question if not context else f"Daten:\n{context}\n\nFrage: {body.question}"
    try:
        answer = llm.complete(prompt, system=system)
    except llm.LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None
    return {"answer": answer.text, "provider": answer.provider, "model": answer.model, "ms": answer.ms}

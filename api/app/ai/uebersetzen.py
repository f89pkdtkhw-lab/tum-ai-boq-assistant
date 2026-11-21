"""Translate document texts (item short/long texts, titles) between German and English for the language switch.

The browser shows a built-in glossary translation at once and asks here for a better one. With a model key the
configured provider translates the batch; offline (mock) every entry is null and the glossary stays. Numbers,
units, item numbers and standards must stay unchanged – an answer that changes the digits of a text is dropped.
"""
import json
import re
from typing import Literal

from fastapi import APIRouter
from pydantic import Field

from ..modelle import Vertrag
from . import llm
from .sprache import ohne_hinweis  # #196

router = APIRouter()


class Anfrage(Vertrag):
    texte: list[str] = Field(max_length=60)
    ziel: Literal["de", "en"]


def _ziffern(text: str) -> str:
    return "".join(re.findall(r"\d", text))


def uebersetze(texte: list[str], ziel: str) -> list[str | None]:
    if not texte or llm.provider() == "mock":
        return [None] * len(texte)
    sprache = "English" if ziel == "en" else "German"
    with ohne_hinweis():  # #196: the target language is given explicitly
        antwort = llm.complete(
            f"Translate each construction bill-of-quantities text to {sprache}. Keep numbers, units, item numbers, "
            "standards (DIN, EN, VOB) and product names unchanged. Use standard construction terminology. Answer only a "
            f"JSON array of strings in the same order and length.\n\n{json.dumps(texte, ensure_ascii=False)}",
            system="You are a precise technical translator for German construction documents.", max_tokens=4000)
    roh = antwort.text[antwort.text.find("["): antwort.text.rfind("]") + 1]
    daten = json.loads(roh) if roh else []
    if not isinstance(daten, list) or len(daten) != len(texte):
        return [None] * len(texte)
    return [d if isinstance(d, str) and d.strip() and _ziffern(d) == _ziffern(t) else None for t, d in zip(texte, daten)]


@router.post("/api/uebersetzen")
def uebersetzen(anfrage: Anfrage):
    texte = [t[:2000] for t in anfrage.texte]
    try:
        ergebnis = uebersetze(texte, anfrage.ziel)
        methode = "mock" if llm.provider() == "mock" else "ki"
    except (llm.LLMError, ValueError, json.JSONDecodeError):
        ergebnis, methode = [None] * len(texte), "fehler"
    return {"uebersetzungen": ergebnis, "methode": methode}

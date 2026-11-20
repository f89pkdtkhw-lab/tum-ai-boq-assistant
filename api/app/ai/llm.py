"""Eine Schnittstelle für alle Modell-Anbieter, die uns am Wettbewerb gestellt werden könnten.

Auswahl über Umgebungsvariablen (siehe .env.example):
    LLM_PROVIDER   anthropic | openai | azure | gemini | mock   (leer = erster Anbieter mit Schlüssel, sonst mock)
    LLM_MODEL      Modellname; ohne Angabe ein Standard pro Anbieter

`mock` läuft ohne Netz und ohne Schlüssel, damit Demo und Tests immer starten.
Schlüssel verlassen nie den Server und tauchen in keiner Fehlermeldung auf.
"""
from dataclasses import dataclass
import os
import time

import httpx

DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-5-5",
    "openai": "",
    "azure": "",
    "gemini": "gemini-2.5-flash",
    "mock": "mock",
}
KEY_FOR = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "azure": "AZURE_OPENAI_API_KEY",
           "gemini": "GEMINI_API_KEY"}
TIMEOUT = float(os.environ.get("LLM_TIMEOUT", "60"))


class LLMError(Exception):
    """A message that is safe to show in the UI."""


@dataclass
class Answer:
    text: str
    provider: str
    model: str
    ms: int


def env(name):
    return os.environ.get(name, "").strip()


def provider():
    chosen = env("LLM_PROVIDER").lower()
    if chosen:
        if chosen not in DEFAULT_MODELS:
            raise LLMError(f"LLM_PROVIDER '{chosen}' ist unbekannt. Erlaubt: {', '.join(DEFAULT_MODELS)}")
        return chosen
    return next((name for name, key in KEY_FOR.items() if env(key)), "mock")


def model(name=None):
    name = name or provider()
    return env("LLM_MODEL") or (env("AZURE_OPENAI_DEPLOYMENT") if name == "azure" else "") or DEFAULT_MODELS[name]


def config():
    """What the app runs on, without any secret."""
    name = provider()
    return {"provider": name, "model": model(name), "mock": name == "mock",
            "keys": {provider_name: bool(env(key)) for provider_name, key in KEY_FOR.items()}}


def complete(prompt, system="", max_tokens=1024):
    name = provider()
    chosen = model(name)
    started = time.perf_counter()
    if name != "mock" and not env(KEY_FOR[name]):
        raise LLMError(f"Für {name} fehlt {KEY_FOR[name]}. Ohne Schlüssel LLM_PROVIDER=mock setzen.")
    if not chosen:
        raise LLMError(f"Für {name} LLM_MODEL setzen (Modellname aus der Doku des Anbieters).")
    try:
        text = {"anthropic": _anthropic, "openai": _openai, "azure": _azure, "gemini": _gemini, "mock": _mock}[name](
            prompt, system, chosen, max_tokens)
    except httpx.HTTPStatusError as exc:
        raise LLMError(f"{name} antwortete mit HTTP {exc.response.status_code}. Schlüssel, Modell und Guthaben prüfen.") from None
    except httpx.HTTPError:
        raise LLMError(f"{name} ist nicht erreichbar. Netz prüfen oder LLM_PROVIDER=mock.") from None
    except (KeyError, IndexError, TypeError, ValueError):
        raise LLMError(f"{name} lieferte eine unerwartete Antwort.") from None
    return Answer(text.strip(), name, chosen, round((time.perf_counter() - started) * 1000))


def _post(url, headers, payload):
    response = httpx.post(url, headers=headers, json=payload, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()


def _anthropic(prompt, system, chosen, max_tokens):
    payload = {"model": chosen, "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]}
    if system:
        payload["system"] = system
    data = _post(env("ANTHROPIC_BASE_URL") or "https://api.anthropic.com/v1/messages",
                 {"x-api-key": env("ANTHROPIC_API_KEY"), "anthropic-version": "2023-06-01"}, payload)
    return "".join(block.get("text", "") for block in data["content"] if block.get("type") == "text")


def _chat_messages(prompt, system):
    return ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]


def _openai(prompt, system, chosen, max_tokens):
    base = (env("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    data = _post(f"{base}/chat/completions", {"Authorization": f"Bearer {env('OPENAI_API_KEY')}"},
                 {"model": chosen, "messages": _chat_messages(prompt, system), "max_completion_tokens": max_tokens})
    return data["choices"][0]["message"]["content"]


def _azure(prompt, system, chosen, max_tokens):
    endpoint = env("AZURE_OPENAI_ENDPOINT").rstrip("/")
    if not endpoint or not chosen:
        raise LLMError("Für azure AZURE_OPENAI_ENDPOINT und AZURE_OPENAI_DEPLOYMENT setzen.")
    version = env("AZURE_OPENAI_API_VERSION") or "2024-10-21"
    data = _post(f"{endpoint}/openai/deployments/{chosen}/chat/completions?api-version={version}",
                 {"api-key": env("AZURE_OPENAI_API_KEY")},
                 {"messages": _chat_messages(prompt, system), "max_completion_tokens": max_tokens})
    return data["choices"][0]["message"]["content"]


def _gemini(prompt, system, chosen, max_tokens):
    payload = {"contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": {"maxOutputTokens": max_tokens}}
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}
    data = _post(f"https://generativelanguage.googleapis.com/v1beta/models/{chosen}:generateContent",
                 {"x-goog-api-key": env("GEMINI_API_KEY")}, payload)
    return "".join(part.get("text", "") for part in data["candidates"][0]["content"]["parts"])


def _mock(prompt, system, chosen, max_tokens):
    lines = [line.strip() for line in prompt.strip().splitlines() if line.strip()]
    question = (lines[-1] if lines else "").removeprefix("Frage:").strip()[:160]
    return f"[Mock-Antwort] Ohne Modell-Schlüssel beantwortet: „{question}“. Mit einem Schlüssel in .env.local antwortet ein echtes Modell."


def mock(prompt, system="", max_tokens=1024):
    """Expliziter Offline-Aufruf, unabhängig von Schlüsseln und Provider-Konfiguration."""
    return Answer(_mock(prompt, system, DEFAULT_MODELS["mock"], max_tokens), "mock", DEFAULT_MODELS["mock"], 0)

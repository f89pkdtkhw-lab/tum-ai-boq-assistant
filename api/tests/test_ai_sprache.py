"""#196: AI texts in German when the UI is German; English (or no setting) keeps every prompt unchanged."""
import time

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import analyse_job
from app.ai import llm, sprache, uebersetzen
from app.lv import excel
from app.main import app
from app.modelle import LV, Position
from app.pruefung import llm_pruefung, normen_ki

SYNTHETIC_KEY = "sk-synthetic-test-key"


class Protokoll(list):
    """Recorded system prompts plus the canned answer of the fake provider."""


@pytest.fixture
def claude(monkeypatch):
    """Claude configured with a fake key; the HTTP layer is replaced, every system prompt is recorded."""
    monkeypatch.setattr(llm, "RUNTIME", {})
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", SYNTHETIC_KEY)
    monkeypatch.setattr(httpx, "post", lambda *_, **__: (_ for _ in ()).throw(AssertionError("no real HTTP call")))
    systeme = Protokoll()
    antworten = {"text": '{"ok": true}'}

    def fake(prompt, system, chosen, max_tokens, **_):
        systeme.append(system)
        return antworten["text"]
    monkeypatch.setattr(llm, "_anthropic", fake)
    systeme.antworten = antworten
    return systeme


@pytest.fixture
def mini(claude):
    """A tiny app with the middleware and a sync route (runs in the thread pool like the real routes)."""
    neu = FastAPI()

    @neu.get("/frage")
    def frage():
        return {"text": llm.complete("Prompt", system="SYS").text}

    neu.add_middleware(sprache.Antwortsprache)
    return TestClient(neu)


def test_german_cookie_adds_the_instruction_to_the_system_prompt(mini, claude):
    mini.get("/frage", cookies={"sprache": "de"})
    assert claude[-1] == "SYS\n\n" + sprache.HINWEIS_DE


@pytest.mark.parametrize("cookies", [{"sprache": "en"}, {}, {"sprache": "fr"}])
def test_english_missing_or_unknown_language_keeps_the_prompt_byte_identical(mini, claude, cookies):
    mini.get("/frage", cookies=cookies)
    assert claude[-1] == "SYS"


def test_header_wins_over_cookie_and_language_does_not_leak_between_requests(mini, claude):
    mini.get("/frage", cookies={"sprache": "en"}, headers={"X-Sprache": "de-DE"})
    assert claude[-1].endswith(sprache.HINWEIS_DE)
    mini.cookies.clear()
    mini.get("/frage")
    assert claude[-1] == "SYS"
    assert sprache.aktuell() is None


def test_main_app_installs_the_middleware():
    assert any(m.cls is sprache.Antwortsprache for m in app.user_middleware)


def test_research_gets_the_instruction_once_on_the_claude_path(claude, monkeypatch):
    gesehen = []
    monkeypatch.setattr(llm, "_anthropic_research", lambda prompt, system, *a, **k: gesehen.append(system) or
                        llm.ResearchAnswer("ok", "anthropic", "m", 1))
    token = sprache.setze("de")
    try:
        llm.research("Prompt", system="SYS")
    finally:
        sprache.zuruecksetzen(token)
    assert gesehen == ["SYS\n\n" + sprache.HINWEIS_DE]


def test_fallback_pool_thread_keeps_the_language(claude):
    token = sprache.setze("de")
    try:
        llm.complete_with_fallback("Prompt", system="SYS", timeout=5)
    finally:
        sprache.zuruecksetzen(token)
    assert claude[-1].endswith(sprache.HINWEIS_DE)


def test_background_analysis_job_keeps_the_language():
    gesehen = []

    def arbeit(_fortschritt):
        gesehen.append(sprache.aktuell())
        raise RuntimeError("stop after recording")
    token = sprache.setze("de")
    try:
        job_id = analyse_job.starte(arbeit, 1)
    finally:
        sprache.zuruecksetzen(token)
    for _ in range(200):
        if gesehen and analyse_job.status(job_id).status != "laeuft":
            break
        time.sleep(0.01)
    assert gesehen == ["de"]


def test_item_review_batches_keep_the_language(claude):
    gesehen = []
    lv = LV(name="Synthetic", quelle="t.json", positionen=[Position(oz="01.0010", kurztext="Wand", menge=1, einheit="m")])
    token = sprache.setze("de")
    try:
        llm_pruefung.pruefe_mit_llm_status(lv, modell=lambda batch: gesehen.append(sprache.aktuell()) or "{}",
                                           timeout=5, parallel=2)
    finally:
        sprache.zuruecksetzen(token)
    assert gesehen == ["de"]


def test_translation_and_excel_extraction_get_no_language_instruction(claude, monkeypatch):
    claude.antworten["text"] = '["Wall 24 cm"]'
    token = sprache.setze("de")
    try:
        assert uebersetzen.uebersetze(["Wand 24 cm"], "en") == ["Wall 24 cm"]
        assert sprache.HINWEIS_DE not in claude[-1]
        claude.antworten["text"] = '{"positionen": []}'
        monkeypatch.setattr(excel, "prompt", lambda block: "Prompt")
        excel._frage(llm.complete, None)
        assert claude[-1] == excel.SYSTEM
        assert sprache.aktuell() == "de"  # the exemption ends with its block
    finally:
        sprache.zuruecksetzen(token)


def test_norm_research_cache_separates_german_and_english():
    lv = LV(name="Synthetic", quelle="t.json", positionen=[Position(oz="01.0010", kurztext="Beton C25/30")])
    englisch = normen_ki._schluessel(lv)
    token = sprache.setze("de")
    try:
        deutsch = normen_ki._schluessel(lv)
    finally:
        sprache.zuruecksetzen(token)
    assert deutsch != englisch
    assert normen_ki._schluessel(lv) == englisch


@pytest.mark.parametrize("wert, erwartet", [("de", "de"), ("DE-de", "de"), ("en-GB", "en"), ("fr", None), ("", None),
                                            (None, None)])
def test_language_values_are_normalised(wert, erwartet):
    assert sprache.normalisiere(wert) == erwartet

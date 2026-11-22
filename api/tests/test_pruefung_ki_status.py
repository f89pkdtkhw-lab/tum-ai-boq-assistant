"""#168 (package D): AI failures and mock fallbacks are visible per step in the report.

Offline only: the model boundaries `llm.complete` and `llm.research` (N5 web research, #166) are replaced by fakes, `httpx.post` and sockets are blocked,
keys are synthetic values. Synthetic LV only, no dataset text.
"""
import json
import socket
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main
from app.ai import ki_status, llm
from app.modelle import LV, Position
from app.pruefung import normen_ki

client = TestClient(main.app)
FAKE_KEY = "synthetic-not-a-key"

LV_D = LV(name="Synthetic D LV", quelle="test", positionen=[
    Position(oz="01.01", kurztext="Innenwand Mauerwerk", langtext="Wohnungstrennwand, schalltechnisch hochwertig.",
             menge=40, einheit="m²", titel_pfad=["Rohbau"]),
    Position(oz="01.02", kurztext="Stahlbeton Decke", langtext="Beton nach DIN 1045-2, C25/30, XC1.",
             menge=20, einheit="m³", titel_pfad=["Rohbau"]),
])


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("network access in offline test")
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(httpx, "post", blocked)
    for name in ("NORM_KI_RECHERCHE", "NORM_KI_TIMEOUT", "NORM_KI_MAX_SEARCHES", "NORM_KI_RUNDEN", "NORMPRUEFUNG"):
        monkeypatch.delenv(name, raising=False)
    normen_ki.cache_leeren()  # #166: N5 results are cached per LV hash


def use_model(monkeypatch, fake):
    """The same fake answers the item review (`llm.complete`) and the N5 web research (`llm.research`, #166)."""
    monkeypatch.setattr(llm, "complete", fake)
    monkeypatch.setattr(llm, "research", fake)


@pytest.fixture
def claude(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)


def report() -> dict:
    response = client.post("/api/lv/pruefen", content=LV_D.model_dump_json(),
                           headers={"Content-Type": "application/json"})
    assert response.status_code == 200
    return response.json()


def steps(body: dict) -> dict:
    return {s["schritt"]: s for s in body.get("ki_schritte") or []}


def fake_complete(review: str, norms: str):
    def complete(prompt, system="", max_tokens=1024, **kwargs):
        text = norms if system == normen_ki.SYSTEM else review
        return llm.Answer(text, "anthropic", "claude-test", 1)
    return complete


def test_mock_by_configuration_reports_no_step_and_the_report_is_unchanged():
    body = report()
    assert "ki_schritte" not in body
    assert body["kennzahlen"]["modell_mock"] is True and "modell_reason" not in body["kennzahlen"]


def test_failing_model_marks_position_review_and_norm_research(claude, monkeypatch):
    def failing(*args, **kwargs):
        raise llm.LLMError("anthropic: HTTP 529 (overloaded).")
    use_model(monkeypatch, failing)
    body = report()
    schritte = steps(body)
    review = schritte["positionspruefung"]
    assert review["status"] == "mock" and review["titel"] == "AI position review"
    assert "HTTP 529" in review["grund"] and "No AI findings in this run" in review["grund"]
    assert review["grund"] == body["kennzahlen"]["modell_reason"]
    norms = schritte["normrecherche"]
    assert norms["status"] == "fehler" and "HTTP 529" in norms["grund"] and "no AI norm hints" in norms["grund"]
    assert FAKE_KEY not in json.dumps(body)


def test_review_timeout_is_visible_with_its_reason(claude, monkeypatch):
    monkeypatch.setenv("LLM_REVIEW_TIMEOUT", "0.2")
    monkeypatch.setenv("NORM_KI_RECHERCHE", "off")

    def slow(*args, **kwargs):
        time.sleep(2)
        return llm.Answer('{"findings": []}', "anthropic", "claude-test", 1)
    use_model(monkeypatch, slow)
    schritte = steps(report())
    assert schritte["positionspruefung"]["status"] == "mock"
    assert "did not finish the review within 0.2 s" in schritte["positionspruefung"]["grund"]
    assert "normrecherche" not in schritte  # switched off on purpose: no status, no notice


def test_norm_research_timeout_is_visible(claude, monkeypatch):
    monkeypatch.setenv("NORM_KI_TIMEOUT", "0.1")

    def complete(prompt, system="", max_tokens=1024, **kwargs):
        if system == normen_ki.SYSTEM:
            time.sleep(1)
        return llm.Answer('{"findings": []}', "anthropic", "claude-test", 1)
    use_model(monkeypatch, complete)
    schritte = steps(report())
    assert schritte["positionspruefung"]["status"] == "ok"
    assert schritte["normrecherche"]["status"] == "fehler"
    assert "No answer within 0.1 s" in schritte["normrecherche"]["grund"]


def test_successful_steps_report_ok_with_model(claude, monkeypatch):
    use_model(monkeypatch, fake_complete('{"findings": []}', '{"vorschlaege": []}'))
    body = report()
    schritte = steps(body)
    assert [s["schritt"] for s in body["ki_schritte"]] == ["positionspruefung", "normrecherche"]
    assert schritte["positionspruefung"]["status"] == "ok"
    assert schritte["positionspruefung"]["modell"].startswith("anthropic/")
    assert schritte["normrecherche"] == {"schritt": "normrecherche", "titel": "AI norm research", "status": "ok",
                                         "grund": "0 additional standard(s) suggested.",
                                         "modell": schritte["positionspruefung"]["modell"]}


def test_analyse_route_carries_the_step_status(claude, monkeypatch):
    def failing(*args, **kwargs):
        raise llm.LLMError("anthropic: request timed out.")
    use_model(monkeypatch, failing)
    response = client.post("/api/lv/analyse", json={"lv": LV_D.model_dump(), "regelwerk": None})
    assert response.status_code == 200
    assert steps(response.json())["positionspruefung"]["status"] == "mock"


def test_melde_outside_a_report_is_a_no_op_and_never_raises():
    ki_status.melde("positionspruefung", "fehler", "x")  # no collector: dropped
    with ki_status.erfasse() as schritte:
        ki_status.melde("normrecherche", "kaputt", "invalid status is ignored")
        ki_status.melde("normrecherche", "fehler", "first")
        ki_status.melde("normrecherche", "ok", "  second\n  report  ")
        ki_status.melde("eigener_schritt", "mock", "z" * 400, titel="Custom step")
    assert [(s.schritt, s.status, s.titel) for s in schritte] == [
        ("normrecherche", "ok", "AI norm research"), ("eigener_schritt", "mock", "Custom step")]
    assert schritte[0].grund == "second report"
    assert len(schritte[1].grund) == ki_status.MAX_GRUND and schritte[1].grund.endswith("…")
    assert ki_status.ergebnis([]) is None


EVIDENCE = {"name": "Synthetic", "items": 10, "score": 95, "traffic_light": "gruen", "serious_items": 0}


def test_evaluation_names_why_the_mock_answered_only_when_a_model_is_configured(monkeypatch):
    assert "reason" not in client.post("/api/lv/ai-evaluation", json=EVIDENCE).json()
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    # #167: with a key the evaluation calls the model; a failing call (stubbed, never the network) names the mock
    monkeypatch.setattr(httpx, "post", lambda url, headers, json, timeout: httpx.Response(
        529, json={}, request=httpx.Request("POST", url)))
    body = client.post("/api/lv/ai-evaluation", json=EVIDENCE).json()
    assert body["source"] == "model_mock"
    assert "evidence-based evaluation" in body["reason"] and FAKE_KEY not in body["reason"]

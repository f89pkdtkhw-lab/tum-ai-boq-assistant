"""AI evaluation endpoint: offline mock, evidence-only numbers, decision follows the traffic light."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

EVIDENCE = {
    "name": "Synthetic LV", "items": 100, "score": 45, "traffic_light": "gelb",
    "stated_total": 105000, "recalculated_total": 100000, "with_optional_total": 112000, "history_expected_total": 110000,
    "serious_items": 6, "findings_by_rule": {"RECHENFEHLER": 2, "MENGE_FEHLT": 3}, "change_order_findings": 4,
    "price_outliers": [{"oz": "01.001", "work": "Betonarbeiten Wand", "deviation_pct": 150}], "unusual_prices": 1,
    "trades": [{"trade": "Abdichtung", "avg_overrun_pct": 25, "projects": 8}, {"trade": "Malerarbeiten", "avg_overrun_pct": -2, "projects": 9}],
    "past_overrun_share": .7,
}


def test_mock_evaluation_is_built_from_evidence():
    r = client.post("/api/lv/ai-evaluation", json=EVIDENCE)
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "model_mock"
    assert body["decision"] == "go_with_conditions"
    cost = next(p for p in body["predictions"] if p["title"] == "Expected final cost")
    assert (cost["low"], cost["high"]) == (100000, 122000)  # history expectation + optional exposure
    assert any(p["title"] == "Likely overrun in Abdichtung" for p in body["predictions"])
    assert not any("Malerarbeiten" in p["title"] for p in body["predictions"])
    titles = [r["title"] for r in body["recommendations"]]
    assert titles[0] == "Fix 2 price errors first"
    assert "Add a 25 % buffer to Abdichtung" in titles


def test_red_light_is_no_go_and_clean_boq_is_go():
    assert client.post("/api/lv/ai-evaluation", json={**EVIDENCE, "traffic_light": "rot"}).json()["decision"] == "no_go"
    clean = {"name": "Clean", "items": 10, "score": 95, "traffic_light": "gruen", "serious_items": 0}
    body = client.post("/api/lv/ai-evaluation", json=clean).json()
    assert body["decision"] == "go"
    assert body["recommendations"][0]["title"] == "Do a final manual check and submit"


def test_invalid_evidence_is_rejected():
    assert client.post("/api/lv/ai-evaluation", json={**EVIDENCE, "score": 140}).status_code == 422


def test_german_answer_on_request():
    body = client.post("/api/lv/ai-evaluation", json={**EVIDENCE, "language": "de"}).json()
    assert body["headline"] == "Nur mit Vorbehalten und Klärungen anbieten"
    assert body["recommendations"][0]["title"] == "Zuerst 2 Preisfehler korrigieren"


# --- #167: with a key, Claude answers (HTTP stubbed, never the network) ---------------------------
FAKE_KEY = "sk-ant-test-evaluation"


@pytest.fixture
def claude(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)


def stub_reply(monkeypatch, text, calls):
    def fake_post(url, headers, json, timeout):
        calls.append({"url": url, "json": json, "timeout": timeout})
        return httpx.Response(200, json={"content": [{"type": "text", "text": text}], "stop_reason": "end_turn"},
                              request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "post", fake_post)


LIVE = {
    "decision": "no_go", "headline": "Clarify first", "summary": "Six serious items.",
    "predictions": [
        {"title": "Expected final cost", "low": 100000, "high": 125000, "unit": "EUR", "confidence": "medium", "basis": "recalculated_total"},
        {"title": "Invented", "low": 9e9, "high": 9e9, "unit": "EUR", "confidence": "high", "basis": "none"},
    ],
    "recommendations": [{"priority": "now", "title": "Fix 2 price errors", "why": "RECHENFEHLER: 2"}],
    "source": "model_mock",
}


def test_with_a_key_claude_answers_and_source_is_model(claude, monkeypatch):
    calls = []
    stub_reply(monkeypatch, "```json\n" + json.dumps(LIVE) + "\n```", calls)
    r = client.post("/api/lv/ai-evaluation", json=EVIDENCE)
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "model" and body["model"] == "anthropic/claude-sonnet-5-5"
    assert body["decision"] == "no_go" and "reason" not in body
    assert [p["title"] for p in body["predictions"]] == ["Expected final cost"]  # out-of-range number dropped
    assert len(calls) == 1 and calls[0]["url"].endswith("/v1/messages")
    sent = calls[0]["json"]
    assert not {"temperature", "top_p", "top_k", "thinking"} & set(sent)
    assert '"recalculated_total": 100000' in sent["messages"][0]["content"]
    assert FAKE_KEY not in r.text


@pytest.mark.parametrize("text", ["no json at all", json.dumps({"decision": "maybe"})])
def test_invalid_model_answer_falls_back_to_the_mock_with_reason(claude, monkeypatch, text):
    stub_reply(monkeypatch, text, [])
    body = client.post("/api/lv/ai-evaluation", json=EVIDENCE).json()
    assert body["source"] == "model_mock" and "evidence-based evaluation" in body["reason"]
    assert body["recommendations"][0]["title"] == "Fix 2 price errors first"


def test_model_http_error_falls_back_to_the_mock_with_reason(claude, monkeypatch):
    def fake_post(url, headers, json, timeout):
        return httpx.Response(429, json={}, request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "post", fake_post)
    body = client.post("/api/lv/ai-evaluation", json=EVIDENCE).json()
    assert body["source"] == "model_mock" and "HTTP 429" in body["reason"]


def test_without_a_key_no_reason_and_no_model_field():
    body = client.post("/api/lv/ai-evaluation", json=EVIDENCE).json()
    assert body["source"] == "model_mock" and "reason" not in body and "model" not in body

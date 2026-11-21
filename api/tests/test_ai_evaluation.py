"""AI evaluation endpoint: offline mock, evidence-only numbers, decision follows the traffic light."""
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

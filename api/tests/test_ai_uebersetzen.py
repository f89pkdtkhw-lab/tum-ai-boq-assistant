from fastapi.testclient import TestClient

from app.ai import uebersetzen
from app.main import app

client = TestClient(app)


def test_offline_returns_nulls(monkeypatch):
    monkeypatch.setattr(uebersetzen.llm, "provider", lambda: "mock")
    r = client.post("/api/uebersetzen", json={"texte": ["Stahlbetonwand 24 cm"], "ziel": "en"})
    assert r.status_code == 200 and r.json() == {"uebersetzungen": [None], "methode": "mock"}


def test_model_answer_must_keep_the_numbers(monkeypatch):
    class A:
        text = '["Reinforced concrete wall 24 cm", "Excavation 99 m"]'
    monkeypatch.setattr(uebersetzen.llm, "provider", lambda: "anthropic")
    monkeypatch.setattr(uebersetzen.llm, "complete", lambda *a, **k: A())
    assert uebersetzen.uebersetze(["Stahlbetonwand 24 cm", "Aushub 12 m"], "en") == ["Reinforced concrete wall 24 cm", None]

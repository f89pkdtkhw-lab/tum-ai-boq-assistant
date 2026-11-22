"""Offline replay (DEMO_REPLAY): stored run in, same run out, no model call."""
import json
import time

import pytest
from fastapi.testclient import TestClient

from app.ai import llm
from app.main import app, DATA


@pytest.fixture()
def replay(tmp_path, monkeypatch):
    client = TestClient(app)
    lv = json.loads((DATA / "beispiel_lv.json").read_text("utf-8"))
    bericht = client.post("/api/lv/pruefen", json=lv).json()
    bericht["kennzahlen"]["modell"] = "anthropic/claude-test"
    (tmp_path / "bericht.json").write_text(json.dumps(bericht), "utf-8")
    (tmp_path / "evaluation.json").write_text(json.dumps({"decision": "go", "headline": "h"}), "utf-8")
    monkeypatch.setenv("DEMO_REPLAY", str(tmp_path))
    monkeypatch.setenv("DEMO_REPLAY_SEKUNDEN", "1")
    return client, bericht


def test_ohne_flag_unveraendert(monkeypatch):
    monkeypatch.delenv("DEMO_REPLAY", raising=False)
    assert TestClient(app).get("/health").json()["provider"] == llm.status()["provider"]


def test_replay(replay):
    client, bericht = replay
    gesund = client.get("/health").json()
    assert (gesund["provider"], gesund["model"], gesund["mock"], gesund["key_set"]) == ("anthropic", "claude-test", False, True)
    lv = client.post("/api/lv/import", files={"datei": ("egal.pdf", b"%PDF-1.4", "application/pdf")}).json()
    assert lv == bericht["lv"]
    job = client.post("/api/lv/analyse/start", json={"lv": lv}).json()["job_id"]
    for _ in range(100):
        stand = client.get(f"/api/lv/analyse/status/{job}").json()
        if stand["status"] != "laeuft":
            break
        time.sleep(0.1)
    assert stand["status"] == "fertig" and len(stand["fertige_schritte"]) == 9
    assert stand["ergebnis"]["findings"] == bericht["findings"]
    assert client.post("/api/lv/ai-evaluation", json={}).json()["headline"] == "h"
    with pytest.raises(llm.LLMError):
        llm.complete("hi")
    with pytest.raises(llm.LLMError):
        llm.research("hi")

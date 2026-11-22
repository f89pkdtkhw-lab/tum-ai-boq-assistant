"""Developer-options code gate, provider switch and Grok Bot file-queue bridge."""
import json
import logging
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.ai import grokbot, llm
from app.fortschritt import Aufzeichnung, setze, zuruecksetzen, warte
from app.main import app

client = TestClient(app)
FAKE_KEY = "sk-ant-test-0123456789abcdefFAKEKEY"
DEFAULT_CODE = "2211"


@pytest.fixture(autouse=True)
def clean(monkeypatch, tmp_path):
    llm.RUNTIME.clear()
    monkeypatch.delenv("DEV_OPTIONS_CODE", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setenv("GROKBOT_QUEUE_DIR", str(tmp_path / "queue"))
    monkeypatch.setenv("GROKBOT_TIMEOUT", "2")
    monkeypatch.setenv("GROKBOT_POLL", "0.05")
    yield
    llm.RUNTIME.clear()


def test_unlock_accepts_the_default_code_and_never_returns_it():
    reply = client.post("/api/ai/dev-options/unlock", json={"code": DEFAULT_CODE})
    assert reply.status_code == 200 and reply.json() == {"ok": True}
    assert DEFAULT_CODE not in reply.text
    assert "2211" not in json.dumps(client.get("/api/ai/dev-options").json())


def test_unlock_rejects_a_wrong_code_without_echoing_it():
    typo = "9999-this-is-not-the-code"
    reply = client.post("/api/ai/dev-options/unlock", json={"code": typo})
    assert reply.status_code == 403 and typo not in reply.text
    assert reply.json()["detail"] == "Wrong unlock code."


def test_unlock_uses_the_environment_code(monkeypatch):
    monkeypatch.setenv("DEV_OPTIONS_CODE", "hackathon")
    assert client.post("/api/ai/dev-options/unlock", json={"code": DEFAULT_CODE}).status_code == 403
    assert client.post("/api/ai/dev-options/unlock", json={"code": "hackathon"}).json() == {"ok": True}


def test_unlock_rejects_non_json_without_echoing_a_code():
    reply = client.post("/api/ai/dev-options/unlock", content=f"code={DEFAULT_CODE}",
                        headers={"Content-Type": "text/plain"})
    assert reply.status_code == 400 and DEFAULT_CODE not in reply.text


def test_default_provider_stays_mock():
    health = client.get("/health").json()
    state = client.get("/api/ai/dev-options").json()
    assert health["provider"] == "mock" and health["mock"] is True
    assert state["provider"] == "mock" and "grokbot" in state["providers"]
    assert llm.complete("Question: hi").provider == "mock"


def test_set_provider_to_grokbot_and_back_to_mock():
    body = client.post("/api/ai/dev-options", json={"provider": "grokbot"}).json()
    assert body["provider"] == "grokbot" and body["mock"] is False and body["model"] == "grok-bot"
    assert client.get("/health").json()["provider"] == "grokbot"
    assert client.post("/api/ai/dev-options", json={"provider": "mock"}).json()["provider"] == "mock"
    assert llm.complete("Question: hi").provider == "mock"


def test_unknown_provider_is_rejected_and_leaves_mock():
    reply = client.post("/api/ai/dev-options", json={"provider": "openai"})
    assert reply.status_code == 400 and llm.provider() == "mock"


def test_wrong_code_on_set_provider_is_rejected(monkeypatch):
    monkeypatch.setenv("DEV_OPTIONS_CODE", "secret-code")
    reply = client.post("/api/ai/dev-options", json={"provider": "grokbot", "code": "nope"})
    assert reply.status_code == 403 and "nope" not in reply.text and "secret-code" not in reply.text
    assert llm.provider() == "mock"


def test_queue_roundtrip_returns_the_answer_text(tmp_path):
    client.post("/api/ai/dev-options", json={"provider": "grokbot"})

    def answer_when_ready():
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            jobs = grokbot.pending()
            if jobs:
                grokbot.write_answer(jobs[0]["job_id"], {"text": "Hello from Grok Bot"})
                return
            time.sleep(0.02)
        raise RuntimeError("job never appeared")

    worker = threading.Thread(target=answer_when_ready)
    worker.start()
    answer = llm.complete("Question: what is the price?")
    worker.join(timeout=3)
    assert (answer.provider, answer.model, answer.text) == ("grokbot", "grok-bot", "Hello from Grok Bot")
    assert grokbot.pending() == []
    done = list((tmp_path / "queue" / "inbox" / "done").glob("*.json"))
    assert len(done) == 1


def test_research_roundtrip_keeps_citations():
    client.post("/api/ai/dev-options", json={"provider": "grokbot"})

    def answer_when_ready():
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            jobs = grokbot.pending()
            if jobs:
                assert jobs[0]["kind"] == "research"
                grokbot.write_answer(jobs[0]["job_id"], {
                    "text": "DIN 18300 applies.",
                    "citations": [{"url": "https://example.org/din", "title": "DIN", "cited_text": "earthworks"}],
                    "sources": [{"url": "https://example.org/din", "title": "DIN"}],
                    "searches": 2,
                    "web_search": True,
                })
                return
            time.sleep(0.02)
        raise RuntimeError("job never appeared")

    worker = threading.Thread(target=answer_when_ready)
    worker.start()
    answer = llm.research("Please check the standard.")
    worker.join(timeout=3)
    assert answer.provider == "grokbot" and answer.text == "DIN 18300 applies."
    assert answer.web_search is True and answer.searches == 2
    assert answer.citations[0].url == "https://example.org/din"
    assert answer.citations[0].cited_text == "earthworks"


def test_timeout_raises_a_clear_error(monkeypatch):
    monkeypatch.setenv("GROKBOT_TIMEOUT", "0.2")
    client.post("/api/ai/dev-options", json={"provider": "grokbot"})
    started = time.monotonic()
    with pytest.raises(llm.LLMError, match="Grok Bot did not answer within 0.2 s"):
        llm.complete("Question: nobody is home")
    assert time.monotonic() - started < 2
    jobs = grokbot.pending()
    assert len(jobs) == 1 and "nobody is home" in jobs[0]["prompt"]


def test_progress_shows_waiting_for_grok_bot(monkeypatch):
    monkeypatch.setenv("GROKBOT_TIMEOUT", "0.2")
    client.post("/api/ai/dev-options", json={"provider": "grokbot"})
    aufzeichnung = Aufzeichnung()
    token = setze(aufzeichnung)
    try:
        with pytest.raises(llm.LLMError, match="did not answer"):
            llm.complete("Question: wait")
    finally:
        zuruecksetzen(token)
    assert any(meldung == grokbot.WARTET for _, _, meldung, _ in aufzeichnung.meldungen)


def test_wait_helper_forwards_the_message():
    aufzeichnung = Aufzeichnung()
    token = setze(aufzeichnung)
    try:
        warte(grokbot.WARTET)
    finally:
        zuruecksetzen(token)
    assert aufzeichnung.meldungen[0][2] == "Wartet auf Grok Bot …"


def test_code_and_keys_never_appear_in_logs(monkeypatch, caplog):
    monkeypatch.setenv("DEV_OPTIONS_CODE", "super-secret-code")
    client.post("/api/ai/dev-options", json={"provider": "anthropic"})
    llm.RUNTIME[llm.KEY_FOR["anthropic"]] = FAKE_KEY
    with caplog.at_level(logging.DEBUG):
        client.post("/api/ai/dev-options/unlock", json={"code": "super-secret-code"})
        client.get("/api/ai/dev-options")
        client.get("/health")
    assert "super-secret-code" not in caplog.text
    assert FAKE_KEY not in caplog.text


def test_cli_list_show_answer(tmp_path, monkeypatch):
    import sys
    import importlib.util

    monkeypatch.setenv("GROKBOT_QUEUE_DIR", str(tmp_path / "queue"))
    client.post("/api/ai/dev-options", json={"provider": "grokbot"})
    job = grokbot.enqueue("complete", "Question: cli test", "Be brief")
    spec = importlib.util.spec_from_file_location(
        "grokbot_queue_cli", Path(__file__).resolve().parents[2] / "tools" / "grokbot_queue.py")
    cli = importlib.util.module_from_spec(spec)
    # The tool inserts api/ onto sys.path; load it fresh.
    spec.loader.exec_module(cli)

    assert cli.main(["list"]) == 0
    assert cli.main(["show", job["job_id"]]) == 0
    answer = tmp_path / "antwort.json"
    answer.write_text('{"text": "CLI reply"}', encoding="utf-8")
    assert cli.main(["answer", job["job_id"], str(answer)]) == 0
    assert grokbot.read_answer(job["job_id"])["text"] == "CLI reply"
    assert grokbot.pending() == []
    assert (tmp_path / "queue" / "inbox" / "done" / f"{job['job_id']}.json").exists()
    del sys  # silence unused if the path insert is enough

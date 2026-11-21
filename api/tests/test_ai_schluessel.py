"""#156: the Claude API key entered in the UI. Offline only: fake keys, `httpx.post` is stubbed."""
import json
import logging
import stat
import subprocess
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.ai import llm, schluessel
from app.main import app

client = TestClient(app)
FAKE_KEY = "sk-ant-test-0123456789abcdefFAKEKEY"
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def clean_runtime(monkeypatch, tmp_path):
    llm.RUNTIME.clear()
    monkeypatch.setattr(schluessel, "ENV_FILE", tmp_path / ".env.local")
    monkeypatch.delenv("LLM_KEY_UI", raising=False)
    yield
    llm.RUNTIME.clear()


def claude_reply(text="OK"):
    return {"type": "message", "role": "assistant", "content": [{"type": "text", "text": text}],
            "stop_reason": "end_turn"}


def stub_post(monkeypatch, response=None, error=None):
    calls = []

    def fake_post(url, headers, json, timeout):
        calls.append({"url": url, "headers": headers, "json": json})
        if error:
            raise error
        code, body = response or (200, claude_reply())
        return httpx.Response(code, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    return calls


def test_without_key_health_and_ui_route_show_the_mock():
    health = client.get("/health").json()
    assert health["mock"] is True and health["key_set"] is False and health["key_source"] is None
    state = client.get("/api/ai/key").json()
    assert state["mock"] is True and state["key_set"] is False and state["ui_enabled"] is True


def test_post_fake_key_sets_key_and_model_but_never_returns_the_key():
    response = client.post("/api/ai/key", json={"key": FAKE_KEY})
    assert response.status_code == 200 and FAKE_KEY not in response.text
    body = response.json()
    assert body["provider"] == "anthropic" and body["mock"] is False and body["persisted"] is False
    assert body["key_set"] is True and body["key_source"] == "ui" and body["model"] == "claude-sonnet-5-5"
    for path in ("/health", "/api/ai/key"):
        reply = client.get(path)
        assert FAKE_KEY not in reply.text
        assert reply.json()["key_set"] is True and reply.json()["model"] == "claude-sonnet-5-5"


def test_switch_from_mock_to_anthropic_without_restart(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")  # even an explicit mock setting yields to the UI key
    assert llm.complete("Question: hi").provider == "mock"
    calls = stub_post(monkeypatch, response=(200, claude_reply("Hello from Claude")))
    assert client.post("/api/ai/key", json={"key": FAKE_KEY, "model": "claude-haiku-5-5"}).status_code == 200
    answer = llm.complete("Question: hi")
    assert (answer.provider, answer.model, answer.text) == ("anthropic", "claude-haiku-5-5", "Hello from Claude")
    assert calls[0]["headers"]["x-api-key"] == FAKE_KEY and calls[0]["url"].startswith("https://api.anthropic.com")
    assert client.delete("/api/ai/key").json()["mock"] is True
    assert llm.complete("Question: hi").provider == "mock"


def test_probe_ok_with_stubbed_http(monkeypatch):
    calls = stub_post(monkeypatch)
    client.post("/api/ai/key", json={"key": FAKE_KEY})
    body = client.post("/api/ai/key/test").json()
    assert body["ok"] is True and body["provider"] == "anthropic" and body["model"] == "claude-sonnet-5-5"
    assert len(calls) == 1 and calls[0]["json"]["max_tokens"] <= 64


@pytest.mark.parametrize("response,error,expected", [
    ((401, {"error": {"message": f"invalid x-api-key {FAKE_KEY}"}}), None, "HTTP 401"),
    ((429, {"error": {"message": "rate"}}), None, "Rate limit"),
    (None, httpx.ConnectError("down"), "unreachable"),
    (None, httpx.ReadTimeout("slow"), "did not answer within"),
])
def test_probe_failure_returns_a_readable_error_without_the_key(monkeypatch, response, error, expected):
    stub_post(monkeypatch, response=response, error=error)
    client.post("/api/ai/key", json={"key": FAKE_KEY})
    reply = client.post("/api/ai/key/test")
    assert reply.status_code == 200 and FAKE_KEY not in reply.text
    assert reply.json()["ok"] is False and expected in reply.json()["error"]


def test_probe_without_key_explains_the_mock(monkeypatch):
    calls = stub_post(monkeypatch)
    body = client.post("/api/ai/key/test").json()
    assert body["ok"] is False and "mock" in body["error"] and calls == []


@pytest.mark.parametrize("payload", [
    {"key": "short"}, {"key": "sk-ant has spaces inside the key value"}, {"key": 12345678901234567890123},
    {"nokey": FAKE_KEY}, [FAKE_KEY], {"key": FAKE_KEY, "model": "bad model; rm"},
])
def test_invalid_input_is_rejected_without_echoing_it(payload):
    reply = client.post("/api/ai/key", json=payload)
    assert reply.status_code == 400 and FAKE_KEY not in reply.text and "spaces inside" not in reply.text
    assert llm.RUNTIME == {} and client.get("/health").json()["key_set"] is False


def test_non_json_body_is_rejected_without_echoing_it():
    reply = client.post("/api/ai/key", content=f"key={FAKE_KEY}", headers={"Content-Type": "text/plain"})
    assert reply.status_code == 400 and FAKE_KEY not in reply.text


def test_key_never_appears_in_logs(monkeypatch, caplog):
    stub_post(monkeypatch, response=(401, {"error": {"message": f"bad {FAKE_KEY}"}}))
    with caplog.at_level(logging.DEBUG):
        client.post("/api/ai/key", json={"key": FAKE_KEY})
        client.post("/api/ai/key/test")
        client.get("/health")
    assert FAKE_KEY not in caplog.text


def test_persist_writes_env_local_with_mode_0600_and_keeps_other_lines(tmp_path):
    target = tmp_path / ".env.local"
    target.write_text("# comment\nGEMINI_API_KEY=other\nANTHROPIC_API_KEY=old\n", encoding="utf-8")
    body = client.post("/api/ai/key", json={"key": FAKE_KEY, "persist": True}).json()
    assert body["persisted"] is True and FAKE_KEY not in json.dumps(body)
    lines = target.read_text(encoding="utf-8").splitlines()
    assert lines[:3] == ["# comment", "GEMINI_API_KEY=other", f"ANTHROPIC_API_KEY={FAKE_KEY}"]
    assert "LLM_PROVIDER=anthropic" in lines and "LLM_MODEL=claude-sonnet-5-5" in lines
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert list(tmp_path.glob(".env.local.*")) == []


def test_without_persist_nothing_is_written(tmp_path):
    client.post("/api/ai/key", json={"key": FAKE_KEY})
    assert not (tmp_path / ".env.local").exists()


def test_env_local_is_gitignored():
    result = subprocess.run(["git", "check-ignore", "-q", ".env.local"], cwd=ROOT)
    assert result.returncode == 0


def test_ui_route_can_be_disabled_for_a_shared_backend(monkeypatch):
    monkeypatch.setenv("LLM_KEY_UI", "off")
    for method, path in (("post", "/api/ai/key"), ("delete", "/api/ai/key"), ("post", "/api/ai/key/test")):
        kwargs = {"json": {"key": FAKE_KEY}} if path == "/api/ai/key" and method == "post" else {}
        assert getattr(client, method)(path, **kwargs).status_code == 403
    assert llm.RUNTIME == {} and client.get("/api/ai/key").json()["ui_enabled"] is False


def test_environment_key_is_reported_as_env_source(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    health = client.get("/health")
    assert health.json()["key_set"] is True and health.json()["key_source"] == "env" and FAKE_KEY not in health.text


def test_config_and_complete_stay_compatible():
    client.post("/api/ai/key", json={"key": FAKE_KEY})
    assert set(llm.config()) == {"provider", "model", "mock", "keys"}
    assert llm.config()["provider"] == "anthropic" and llm.config()["keys"]["anthropic"] is True

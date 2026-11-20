"""Backend tests: run offline, no key required. Run: cd api && python -m pytest -q"""
import httpx
import pytest
from fastapi.testclient import TestClient

from app import main
from app.ai import llm

KEYS = ("LLM_PROVIDER", "LLM_MODEL", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "AZURE_OPENAI_API_KEY", "GEMINI_API_KEY",
        "OPENAI_BASE_URL", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in KEYS:
        monkeypatch.delenv(key, raising=False)


client = TestClient(main.app)


def test_health_runs_on_mock_without_keys():
    body = client.get("/health").json()
    assert body["ok"] and body["provider"] == "mock" and body["mock"]
    assert set(body["keys"]) == {"anthropic", "openai", "azure", "gemini"}


def test_ask_answers_with_mock_and_reports_its_origin():
    body = client.post("/api/ask", json={"question": "Was kann die App?"}).json()
    assert body["provider"] == "mock" and "Was kann die App?" in body["answer"] and body["ms"] >= 0


def test_ask_rejects_empty_question():
    assert client.post("/api/ask", json={"question": ""}).status_code == 422


def test_first_provider_with_a_key_is_chosen(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    assert llm.provider() == "gemini" and llm.model() == llm.DEFAULT_MODELS["gemini"]
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    assert llm.provider() == "mock"


@pytest.mark.parametrize("name, key, reply, expected", [
    ("anthropic", "ANTHROPIC_API_KEY", {"content": [{"type": "text", "text": "hallo"}]}, "hallo"),
    ("openai", "OPENAI_API_KEY", {"choices": [{"message": {"content": "hi"}}]}, "hi"),
    ("gemini", "GEMINI_API_KEY", {"candidates": [{"content": {"parts": [{"text": "servus"}]}}]}, "servus"),
])
def test_each_provider_is_called_with_its_own_format(monkeypatch, name, key, reply, expected):
    monkeypatch.setenv("LLM_PROVIDER", name)
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv(key, "geheim-123")
    seen = {}

    def fake_post(url, headers, json, timeout):
        seen.update(url=url, headers=headers, json=json)
        return httpx.Response(200, json=reply, request=httpx.Request("POST", url))

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    answer = llm.complete("Frage", system="Sei knapp")
    assert (answer.text, answer.provider, answer.model) == (expected, name, "test-model")
    assert "geheim-123" in str(seen["headers"]) and "geheim-123" not in seen["url"]


def test_errors_never_leak_the_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "geheim-123")

    def failing(url, headers, json, timeout):
        return httpx.Response(401, json={"error": "geheim-123 invalid"}, request=httpx.Request("POST", url))

    monkeypatch.setattr(llm.httpx, "post", failing)
    with pytest.raises(llm.LLMError) as error:
        llm.complete("x")
    assert "401" in str(error.value) and "geheim-123" not in str(error.value)


def test_missing_key_or_model_gives_clear_message(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    with pytest.raises(llm.LLMError, match="OPENAI_API_KEY"):
        llm.complete("x")
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    with pytest.raises(llm.LLMError, match="LLM_MODEL"):
        llm.complete("x")

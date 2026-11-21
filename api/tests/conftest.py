"""Shared test setup: every test starts offline in mock mode (#147).

Since the BoQ pipeline uses a configured provider, a key exported in the developer's shell would
otherwise turn tests into real model calls. Tests that need a provider set fake values themselves
and stub the HTTP layer.
"""
import pytest

MODEL_ENV = (
    "LLM_PROVIDER", "LLM_MODEL", "LLM_TIMEOUT", "LLM_REVIEW_TIMEOUT", "LLM_BATCH_TIMEOUT", "LLM_EVALUATION_TIMEOUT", "LLM_REVIEW_EFFORT", "LLM_BATCH_SIZE",
    "LLM_PARALLEL", "ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL", "ANTHROPIC_EFFORT", "OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL",
    "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT", "AZURE_OPENAI_API_VERSION",
    "GEMINI_API_KEY", "GEMINI_BASE_URL", "GEMINI_THINKING_BUDGET",
    "DEEP_RESEARCH_MAX_USES", "DEEP_RESEARCH_MAX_CALLS", "DEEP_RESEARCH_BUDGET",  # E #169
    "DEEP_RESEARCH_MAX_ITEMS", "DEEP_RESEARCH_TIMEOUT", "DEEP_RESEARCH_PARALLEL",
)


@pytest.fixture(autouse=True)
def offline_model_env(monkeypatch):
    for name in MODEL_ENV:
        monkeypatch.delenv(name, raising=False)
    # E #169: deep web research stays off in tests even with a fake key; its tests switch it on.
    monkeypatch.setenv("DEEP_RESEARCH", "off")

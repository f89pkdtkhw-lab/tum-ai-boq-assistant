"""`llm.research()` (#166): Claude web search with citations and pause_turn, against stubbed HTTP only.

Synthetic answers only; httpx.post is replaced, so no test reaches the network or needs a key.
"""
import copy

import httpx
import pytest

from app.ai import llm

KEYS = ("LLM_PROVIDER", "LLM_MODEL", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "AZURE_OPENAI_API_KEY", "GEMINI_API_KEY",
        "ANTHROPIC_BASE_URL", "ANTHROPIC_EFFORT", "LLM_TIMEOUT")
SYNTHETIC_KEY = "synthetic-test-key-not-real"


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    for key in KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(llm, "RUNTIME", {})

    def kein_netz(*_, **__):
        raise AssertionError("no real HTTP call in tests")
    monkeypatch.setattr(httpx, "post", kein_netz)


class Antwort:
    def __init__(self, data, status=200):
        self.data, self.status_code = data, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("synthetic", request=httpx.Request("POST", "https://x"),
                                        response=httpx.Response(self.status_code))

    def json(self):
        return self.data


def server(monkeypatch, *antworten):
    """Stub httpx.post with the given Messages API answers in order; returns the recorded requests."""
    anfragen, rest = [], list(antworten)

    def post(url, headers=None, json=None, timeout=None):
        anfragen.append({"url": url, "headers": headers, "json": copy.deepcopy(json),
                         "timeout": timeout})
        antwort = rest.pop(0)
        return antwort if isinstance(antwort, Antwort) else Antwort(antwort)
    monkeypatch.setattr(httpx, "post", post)
    return anfragen


def claude(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", SYNTHETIC_KEY)


SUCHE = {"type": "server_tool_use", "id": "srvtoolu_1", "name": "web_search", "input": {"query": "DIN 4109"}}
TREFFER = {"type": "web_search_tool_result", "tool_use_id": "srvtoolu_1", "content": [
    {"type": "web_search_result", "url": "https://example.org/a", "title": "Page A", "encrypted_content": "x"},
    {"type": "web_search_result", "url": "https://example.org/b", "title": "Page B", "encrypted_content": "y"},
]}
ZITIERT = {"type": "text", "text": "DIN 4109 applies.", "citations": [
    {"type": "web_search_result_location", "url": "https://example.org/a", "title": "Page A",
     "cited_text": "DIN 4109-1 sets minimum sound insulation.", "encrypted_index": "z"}]}


def nachricht(content, stop="end_turn", suchen=0):
    return {"content": content, "stop_reason": stop, "usage": {"server_tool_use": {"web_search_requests": suchen}}}


def test_request_declares_the_web_search_tool_and_no_sampling_parameters(monkeypatch):
    claude(monkeypatch)
    anfragen = server(monkeypatch, nachricht([{"type": "text", "text": "ok"}]))
    antwort = llm.research("Question", "System", 9000, max_searches=4, timeout=30)
    [anfrage] = anfragen
    body = anfrage["json"]
    assert body["tools"] == [{"type": "web_search_20250305", "name": "web_search", "max_uses": 4}]
    assert body["max_tokens"] == 9000 and body["system"] == "System" and body["model"] == "claude-sonnet-5-5"
    assert not {"temperature", "top_p", "top_k", "thinking"} & body.keys()
    assert anfrage["headers"]["x-api-key"] == SYNTHETIC_KEY and anfrage["headers"]["anthropic-version"]
    assert 0 < anfrage["timeout"] <= 30
    assert (antwort.text, antwort.provider, antwort.web_search, antwort.citations) == ("ok", "anthropic", True, [])


def test_citations_sources_and_searches_are_collected(monkeypatch):
    claude(monkeypatch)
    server(monkeypatch, nachricht([{"type": "text", "text": "Searching. "}, SUCHE, TREFFER, ZITIERT,
                                   {"type": "text", "text": ' {"vorschlaege": []}'}], suchen=1))
    antwort = llm.research("Question")
    assert antwort.text == 'Searching. DIN 4109 applies. {"vorschlaege": []}'
    assert antwort.citations == [llm.Citation("https://example.org/a", "Page A",
                                              "DIN 4109-1 sets minimum sound insulation.")]
    assert [s.url for s in antwort.sources] == ["https://example.org/a", "https://example.org/b"]
    assert antwort.searches == 1 and llm.parse_json(antwort.text) == {"vorschlaege": []}


def test_pause_turn_sends_the_paused_answer_back_and_continues(monkeypatch):
    claude(monkeypatch)
    erst = [{"type": "text", "text": "Let me search. "}, SUCHE, TREFFER]
    anfragen = server(monkeypatch, nachricht(erst, "pause_turn", 1), nachricht([ZITIERT], suchen=1))
    antwort = llm.research("Question", max_searches=3)
    assert len(anfragen) == 2
    zweite = anfragen[1]["json"]["messages"]
    assert zweite == [{"role": "user", "content": "Question"}, {"role": "assistant", "content": erst}]
    assert anfragen[1]["json"]["tools"] == anfragen[0]["json"]["tools"]
    assert antwort.text == "Let me search. DIN 4109 applies." and antwort.searches == 2
    assert len(antwort.citations) == 1 and len(antwort.sources) == 2


def test_endless_pause_turn_gives_up_with_a_readable_error(monkeypatch):
    claude(monkeypatch)
    server(monkeypatch, *[nachricht([SUCHE], "pause_turn")] * (llm.MAX_PAUSE_TURNS + 1))
    with pytest.raises(llm.LLMError, match="paused the research"):
        llm.research("Question")


def test_search_error_result_is_skipped(monkeypatch):
    claude(monkeypatch)
    fehler = {"type": "web_search_tool_result", "tool_use_id": "srvtoolu_1",
              "content": {"type": "web_search_tool_result_error", "error_code": "max_uses_exceeded"}}
    server(monkeypatch, nachricht([SUCHE, fehler, {"type": "text", "text": "No sources."}]))
    antwort = llm.research("Question")
    assert antwort.text == "No sources." and antwort.sources == []


def test_max_tokens_with_text_returns_a_truncated_answer(monkeypatch):
    claude(monkeypatch)
    server(monkeypatch, nachricht([{"type": "text", "text": '{"ergebnisse": [{"oz": "01.01"},'}], "max_tokens", 1))
    antwort = llm.research("Question")
    assert antwort.truncated and antwort.web_search and '{"ergebnisse"' in antwort.text
    assert antwort.searches == 1


@pytest.mark.parametrize("data, muster", [
    ({"content": [], "stop_reason": "refusal", "stop_details": {"category": "cyber"}}, "refusal: cyber"),
    (nachricht([], "max_tokens"), "max_tokens"),
    (nachricht([SUCHE, TREFFER]), "no text"),
    ({"unexpected": True}, "unexpected response"),
])
def test_bad_answers_raise_ui_safe_errors(monkeypatch, data, muster):
    claude(monkeypatch)
    server(monkeypatch, data)
    with pytest.raises(llm.LLMError, match=muster):
        llm.research("Question")


@pytest.mark.parametrize("status, muster", [(429, "Rate limit"), (400, "web search is enabled")])
def test_http_errors_never_contain_the_key(monkeypatch, status, muster):
    claude(monkeypatch)
    server(monkeypatch, Antwort({}, status))
    with pytest.raises(llm.LLMError, match=muster) as fehler:
        llm.research("Question")
    assert SYNTHETIC_KEY not in str(fehler.value)


def test_timeout_is_a_readable_error(monkeypatch):
    claude(monkeypatch)
    def langsam(*_, **__):
        raise httpx.ReadTimeout("synthetic")
    monkeypatch.setattr(httpx, "post", langsam)
    with pytest.raises(llm.LLMError, match="within 5 s"):
        llm.research("Question", timeout=5)


def test_missing_key_raises_without_a_call(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    with pytest.raises(llm.LLMError, match="Missing ANTHROPIC_API_KEY"):
        llm.research("Question")


def test_mock_answers_offline_without_citations():
    antwort = llm.research("Question: Which standards apply?")
    assert antwort.provider == "mock" and antwort.web_search is False
    assert antwort.citations == [] and antwort.sources == [] and "[Mock response]" in antwort.text


def test_other_providers_answer_without_web_search(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", SYNTHETIC_KEY)
    anfragen = server(monkeypatch, {"candidates": [{"content": {"parts": [{"text": "plain"}]}}]})
    antwort = llm.research("Question", max_searches=3)
    [anfrage] = anfragen
    assert "tools" not in anfrage["json"] and antwort.text == "plain" and antwort.web_search is False

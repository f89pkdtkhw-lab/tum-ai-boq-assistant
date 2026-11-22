"""#147: real AI through the Claude API (documented default) or Gemini, with timeout and visible mock fallback.

Offline only: `httpx.post` is replaced by stubs that answer like the Anthropic Messages API or the
Gemini REST API, sockets are blocked, and keys are synthetic values. No real network call.
"""
import json
import os
import socket
import threading
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main
from app.ai import llm
from app.modelle import LV, Position
from app.pruefung import llm_pruefung
from app.pruefung.llm_pruefung import mock_pruefung, pruefe_mit_llm_status, validiere_antwort

ROOT = Path(__file__).resolve().parents[2]
FAKE_KEY = "synthetic-gemini-test-value"
client = TestClient(main.app)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("network access in offline test")
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(httpx, "post", blocked)


@pytest.fixture
def gemini(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_KEY)
    monkeypatch.setenv("NORM_KI_RECHERCHE", "off")  # N5 has its own tests; count only item-review calls


def gemini_reply(text, **candidate):
    return {"candidates": [{"content": {"parts": [{"text": text}]}, **candidate}]}


def items_of(payload):
    prompt = (payload["messages"][0]["content"] if "messages" in payload
              else payload["contents"][0]["parts"][0]["text"])
    return json.loads(prompt.split("Items:\n", 1)[1])


def stub(monkeypatch, answer, calls=None):
    """Stub the HTTP layer; `answer(items, payload)` returns the model text or raises."""
    lock = threading.Lock()

    def fake_post(url, headers, json, timeout):
        items = items_of(json)
        with lock:
            if calls is not None:
                calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout, "items": items})
        text = answer(items, json)
        return httpx.Response(200, json=gemini_reply(text), request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "post", fake_post)


def finding_for(oz, **over):
    base = {"oz": oz, "kategorie": "risiko", "schwere": "mittel", "titel": "Open wording",
            "begruendung": "The long text says 'as required'.", "vorschlag": "Define the demand.",
            "regel_id": "LLM_VAGUE"}
    base.update(over)
    return base


def synthetic_lv(n):
    return LV(name="Synthetic", quelle="synthetisch", positionen=[
        Position(oz=f"01.{i:03d}", kurztext=f"Item {i}", langtext="as required", menge=1, einheit="m2")
        for i in range(n)])


def beispiel():
    return json.loads((ROOT / "data" / "beispiel_lv.json").read_text(encoding="utf-8"))


# --- Acceptance 1: without any key -------------------------------------------------------------

def test_without_key_health_and_review_run_on_the_mock_with_unchanged_findings():
    health = client.get("/health").json()
    assert health["provider"] == "mock" and health["mock"] is True and health["reason"] is None
    lv = LV.model_validate(beispiel())
    expected = main.bewerte(lv, main.pruefe_regeln(lv) + main.pruefe_mengen(lv) + main.pruefe_mit_llm(lv)) \
        + main.pruefe_normen_sicher(lv)
    response = client.post("/api/lv/pruefen", json=beispiel())
    assert response.status_code == 200
    body = response.json()
    assert body["findings"] == [f.model_dump(mode="json") for f in expected]
    assert body["kennzahlen"]["modell_mock"] is True
    assert "modell_reason" not in body["kennzahlen"] and "modell" not in body["kennzahlen"]
    assert [f["regel_id"] for f in body["findings"]].count("MOCK_LLM") == 1


def test_provider_without_key_falls_back_with_a_reason(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    state = llm.status()
    assert state["provider"] == "gemini" and state["mock"] is True and "GEMINI_API_KEY" in state["reason"]
    body = client.post("/api/lv/pruefen", json=beispiel()).json()
    assert body["kennzahlen"]["modell_mock"] is True and "GEMINI_API_KEY" in body["kennzahlen"]["modell_reason"]


def test_unknown_provider_never_crashes_health(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "nonsense")
    health = client.get("/health").json()
    assert health["ok"] and health["mock"] is True and "nonsense" in health["reason"]


# --- Acceptance 2: Gemini with a fake key against the stubbed HTTP layer ---------------------------

def test_health_reports_gemini_and_the_configured_model(gemini, monkeypatch):
    health = client.get("/health").json()
    assert (health["provider"], health["model"], health["mock"]) == ("gemini", "gemini-2.5-flash", False)
    assert health["keys"]["gemini"] is True and FAKE_KEY not in json.dumps(health)
    monkeypatch.setenv("LLM_MODEL", "gemini-test-model")
    assert client.get("/health").json()["model"] == "gemini-test-model"


def test_review_sends_all_positions_in_batches(gemini, monkeypatch):
    monkeypatch.setenv("LLM_BATCH_SIZE", "20")
    calls = []
    stub(monkeypatch, lambda items, payload: json.dumps({"findings": [finding_for(items[0]["oz"])]}), calls)
    lv = synthetic_lv(45)
    response = client.post("/api/lv/pruefen", json=lv.model_dump(mode="json"))
    assert response.status_code == 200
    assert len(calls) == 3 and sorted(len(c["items"]) for c in calls) == [5, 20, 20]
    assert sorted(i["oz"] for c in calls for i in c["items"]) == [p.oz for p in lv.positionen]
    call = calls[0]
    assert call["url"].endswith("/models/gemini-2.5-flash:generateContent")
    assert call["headers"] == {"x-goog-api-key": FAKE_KEY}
    assert call["json"]["generationConfig"]["responseMimeType"] == "application/json"
    assert call["json"]["systemInstruction"]["parts"][0]["text"] == llm_pruefung.SYSTEM
    assert 0 < call["timeout"] <= llm_pruefung.DEFAULT_REVIEW_TIMEOUT
    kennzahlen = response.json()["kennzahlen"]
    assert kennzahlen["modell_mock"] is False and kennzahlen["modell"] == "gemini/gemini-2.5-flash"
    assert "modell_reason" not in kennzahlen
    model_findings = [f for f in response.json()["findings"] if f["quelle"] == "modell"]
    assert sorted(f["oz"] for f in model_findings) == ["01.000", "01.020", "01.040"]
    assert all(f["regel_id"] == "LLM_VAGUE" and f["euro_wirkung"] is None for f in model_findings)
    assert all("Demonstration" not in f["titel"] for f in model_findings)
    assert FAKE_KEY not in response.text


@pytest.mark.parametrize("wrap", [
    lambda raw: f"```json\n{raw}\n```",
    lambda raw: f"Here is the review:\n{raw}\nHope this helps.",
    lambda raw: f"Sure!\n```\n{raw}\n```",
])
def test_fenced_or_prefixed_json_is_still_parsed(gemini, monkeypatch, wrap):
    stub(monkeypatch, lambda items, payload: wrap(json.dumps({"findings": [finding_for(items[0]["oz"])]})))
    result = pruefe_mit_llm_status(synthetic_lv(3))
    assert result.mock is False and [f.oz for f in result.findings] == ["01.000"]


def test_malformed_findings_are_normalised_or_rejected_never_raised(gemini, monkeypatch):
    raw = json.dumps({"findings": [
        finding_for("01.000", regel_id="vague wording", kategorie="Risiko", euro_wirkung=5000, extra="x"),
        finding_for("99.999"),                     # invented OZ
        finding_for("01.001", schwere="extreme"),  # severity outside the contract
        "not an object",
    ]})
    stub(monkeypatch, lambda items, payload: raw)
    result = pruefe_mit_llm_status(synthetic_lv(2))
    assert result.mock is False and len(result.findings) == 1
    finding = result.findings[0]
    assert (finding.oz, finding.regel_id, finding.kategorie, finding.euro_wirkung, finding.quelle) == (
        "01.000", "LLM_VAGUE_WORDING", "risiko", None, "modell")
    assert len(result.rejected) == 3


def test_unreadable_answer_falls_back_to_mock(gemini, monkeypatch):
    stub(monkeypatch, lambda items, payload: "I cannot help with that.")
    result = pruefe_mit_llm_status(synthetic_lv(3))
    assert result.mock is True and "readable JSON" in result.reason
    assert result.findings == mock_pruefung(synthetic_lv(3)).findings


def raising(exc):
    def answer(items, payload):
        raise exc
    return answer


@pytest.mark.parametrize("error, expected", [
    (httpx.ReadTimeout("slow"), "did not answer within"),
    (httpx.ConnectError("down"), "unreachable"),
])
def test_timeout_or_network_error_falls_back_to_mock_and_endpoint_returns_200(gemini, monkeypatch, error, expected):
    stub(monkeypatch, raising(error))
    response = client.post("/api/lv/pruefen", json=beispiel())
    assert response.status_code == 200
    kennzahlen = response.json()["kennzahlen"]
    assert kennzahlen["modell_mock"] is True and expected in kennzahlen["modell_reason"]
    assert "No AI findings in this run" in kennzahlen["modell_reason"]
    assert "modell" not in kennzahlen
    assert [f["regel_id"] for f in response.json()["findings"]].count("MOCK_LLM") == 1


@pytest.mark.parametrize("code, expected", [(429, "HTTP 429"), (500, "HTTP 500"), (403, "HTTP 403")])
def test_http_error_falls_back_to_mock_with_readable_reason(gemini, monkeypatch, code, expected):
    def fake_post(url, headers, json, timeout):
        return httpx.Response(code, json={"error": {"message": f"bad {FAKE_KEY}"}}, request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "post", fake_post)
    response = client.post("/api/lv/pruefen", json=beispiel())
    assert response.status_code == 200
    reason = response.json()["kennzahlen"]["modell_reason"]
    assert response.json()["kennzahlen"]["modell_mock"] is True and expected in reason
    assert FAKE_KEY not in response.text


def test_hanging_provider_is_cut_off_by_the_review_deadline(gemini, monkeypatch):
    release = threading.Event()

    def hang(items, payload):
        release.wait(5)
        return json.dumps({"findings": []})
    stub(monkeypatch, hang)
    started = time.perf_counter()
    try:
        result = pruefe_mit_llm_status(synthetic_lv(3), timeout=0.2)
    finally:
        release.set()
    assert time.perf_counter() - started < 3
    assert result.mock is True and "within 0.2 s" in result.reason


def test_one_failing_batch_keeps_the_other_batches_and_names_the_failure(gemini, monkeypatch):
    """#167: no silent mock fallback; partial results stay, the failed batch is reported."""
    def answer(items, payload):
        if items[0]["oz"] == "01.002":
            raise httpx.ReadTimeout("slow")
        return json.dumps({"findings": [finding_for(items[0]["oz"])]})
    stub(monkeypatch, answer)
    result = pruefe_mit_llm_status(synthetic_lv(4), batch_size=2, parallel=1)
    assert result.mock is False and [f.oz for f in result.findings] == ["01.000"]
    assert (result.batches, result.fehlgeschlagen) == (2, 1)
    assert result.reason.startswith("1/2 model batch(es) failed")
    assert "batch 2 (OZ 01.002–01.003)" in result.reason and "did not answer within" in result.reason


def test_partial_failure_is_visible_in_kennzahlen(gemini, monkeypatch):
    monkeypatch.setenv("LLM_BATCH_SIZE", "20")

    def answer(items, payload):
        if items[0]["oz"] == "01.020":
            raise httpx.ConnectError("down")
        return json.dumps({"findings": [finding_for(items[0]["oz"])]})
    stub(monkeypatch, answer)
    response = client.post("/api/lv/pruefen", json=synthetic_lv(45).model_dump(mode="json"))
    kennzahlen = response.json()["kennzahlen"]
    assert kennzahlen["modell_mock"] is False and kennzahlen["modell"] == "gemini/gemini-2.5-flash"
    assert (kennzahlen["modell_batches"], kennzahlen["modell_batches_fehlgeschlagen"]) == (3, 1)
    assert "1/3 model batch(es) failed" in kennzahlen["modell_reason"]
    assert sorted(f["oz"] for f in response.json()["findings"] if f["quelle"] == "modell") == ["01.000", "01.040"]


def test_progress_callback_reports_every_batch(gemini, monkeypatch):
    stub(monkeypatch, lambda items, payload: json.dumps({"findings": []}))
    seen = []
    result = pruefe_mit_llm_status(synthetic_lv(5), batch_size=2, parallel=2, fortschritt=lambda d, t: seen.append((d, t)))
    assert result.mock is False and sorted(seen) == [(1, 3), (2, 3), (3, 3)]


def test_broken_progress_callback_never_breaks_the_review(gemini, monkeypatch):
    stub(monkeypatch, lambda items, payload: json.dumps({"findings": [finding_for(items[0]["oz"])]}))

    def kaputt(done, total):
        raise RuntimeError("listener gone")
    result = pruefe_mit_llm_status(synthetic_lv(3), fortschritt=kaputt)
    assert result.mock is False and len(result.findings) == 1


def test_progress_callback_runs_once_on_the_mock(monkeypatch):
    seen = []
    result = pruefe_mit_llm_status(synthetic_lv(3), fortschritt=lambda d, t: seen.append((d, t)))
    assert result.mock is True and seen == [(1, 1)]


def test_batch_timeout_is_per_call_and_configurable(gemini, monkeypatch):
    monkeypatch.setenv("LLM_BATCH_TIMEOUT", "12")
    calls = []
    stub(monkeypatch, lambda items, payload: json.dumps({"findings": []}), calls)
    pruefe_mit_llm_status(synthetic_lv(3))
    assert calls and all(c["timeout"] == 12 for c in calls)


def test_unfinished_batches_at_the_deadline_keep_finished_ones(gemini, monkeypatch):
    release = threading.Event()

    def answer(items, payload):
        if items[0]["oz"] == "01.002":
            release.wait(5)
        return json.dumps({"findings": [finding_for(items[0]["oz"])]})
    stub(monkeypatch, answer)
    try:
        result = pruefe_mit_llm_status(synthetic_lv(4), batch_size=2, parallel=2, timeout=0.3)
    finally:
        release.set()
    assert result.mock is False and [f.oz for f in result.findings] == ["01.000"]
    assert result.fehlgeschlagen == 1 and "did not finish the review within 0.3 s" in result.reason


# --- llm.py: Gemini path, JSON parsing, fallback helper (also for the Excel import #9) -------------

@pytest.mark.parametrize("text, expected", [
    ('{"a": 1}', {"a": 1}),
    ('```json\n{"a": 1}\n```', {"a": 1}),
    ('Answer: {"a": {"b": [1, 2]}} done', {"a": {"b": [1, 2]}}),
    ('```\n[1, 2]\n```', [1, 2]),
    ('prefix {not json} then {"a": 2}', {"a": 2}),
])
def test_parse_json_accepts_fenced_and_prefixed_answers(text, expected):
    assert llm.parse_json(text) == expected


@pytest.mark.parametrize("text", ["", "no json here", None, "{broken"])
def test_parse_json_raises_value_error_on_garbage(text):
    with pytest.raises(ValueError):
        llm.parse_json(text)


def test_gemini_skips_thought_parts_and_reports_empty_answers(gemini, monkeypatch):
    replies = iter([
        {"candidates": [{"content": {"parts": [{"text": "thinking...", "thought": True}, {"text": "ok"}]}}]},
        {"candidates": [{"content": {"parts": []}, "finishReason": "MAX_TOKENS"}]},
        {"promptFeedback": {"blockReason": "SAFETY"}},
    ])

    def fake_post(url, headers, json, timeout):
        return httpx.Response(200, json=next(replies), request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "post", fake_post)
    assert llm.complete("x").text == "ok"
    with pytest.raises(llm.LLMError, match="MAX_TOKENS"):
        llm.complete("x")
    with pytest.raises(llm.LLMError, match="SAFETY"):
        llm.complete("x")


def test_complete_keeps_its_interface_for_existing_callers(gemini, monkeypatch):
    """`llm.complete(prompt, system, max_tokens)` and `llm.config()` stay compatible (Excel import #9)."""
    seen = {}

    def fake_post(url, headers, json, timeout):
        seen.update(json=json, timeout=timeout)
        return httpx.Response(200, json=gemini_reply('{"positionen": []}'), request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "post", fake_post)
    answer = llm.complete("prompt", "system", 123)
    assert (answer.text, answer.provider, answer.reason) == ('{"positionen": []}', "gemini", None)
    assert seen["json"]["generationConfig"] == {"maxOutputTokens": 123}
    assert seen["timeout"] == llm.DEFAULT_TIMEOUT
    assert set(llm.config()) == {"provider", "model", "mock", "keys"} and llm.config()["mock"] is False
    monkeypatch.setenv("LLM_TIMEOUT", "7")
    llm.complete("prompt")
    assert seen["timeout"] == 7


def test_complete_with_fallback_never_raises(gemini, monkeypatch):
    def slow(url, headers, json, timeout):
        raise httpx.ReadTimeout("slow")
    monkeypatch.setattr(httpx, "post", slow)
    answer = llm.complete_with_fallback("Question: hi", timeout=1, mock_text='{"positionen": []}')
    assert answer.provider == "mock" and answer.text == '{"positionen": []}'
    assert "did not answer within" in answer.reason and "No AI answer used" in answer.reason
    monkeypatch.setattr(llm, "complete", lambda *a, **k: llm.Answer("real answer", "gemini", "m", 1))
    assert llm.complete_with_fallback("x").text == "real answer"


def test_ask_uses_gemini_and_falls_back_visibly(gemini, monkeypatch):
    def fake_post(url, headers, json, timeout):
        return httpx.Response(200, json=gemini_reply("Gemini says hi"), request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "post", fake_post)
    body = client.post("/api/ask", json={"question": "Hi?", "use_data": False}).json()
    assert (body["answer"], body["provider"], body["mock"], body["reason"]) == ("Gemini says hi", "gemini", False, None)
    monkeypatch.setattr(httpx, "post", lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("down")))
    body = client.post("/api/ask", json={"question": "Hi?", "use_data": False}).json()
    assert body["provider"] == "mock" and body["mock"] is True and "unreachable" in body["reason"]


def test_validator_keeps_mock_mode_strict():
    batch = synthetic_lv(1).positionen
    real_style = json.dumps({"findings": [finding_for("01.000", quelle="modell", euro_wirkung=None)]})
    assert validiere_antwort(real_style, batch).findings == []  # LLM_ prefix is not a MOCK_ finding
    assert len(validiere_antwort(real_style, batch, real=True).findings) == 1


def test_env_file_loader_reads_keys_without_overriding_the_environment(tmp_path, monkeypatch):
    path = tmp_path / "synthetic.env"
    path.write_text("# comment\nLLM_PROVIDER=gemini\nexport GEMINI_API_KEY=\"synthetic-value\"\n"
                    "LLM_MODEL=\nLLM_TIMEOUT=30 # seconds\nnot a line\n", encoding="utf-8")
    for name in ("GEMINI_API_KEY", "LLM_TIMEOUT", "LLM_MODEL"):  # restored to "absent" after the test
        monkeypatch.setenv(name, "placeholder")
        monkeypatch.delenv(name)
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    loaded = llm.load_env_file(path)
    assert sorted(loaded) == ["GEMINI_API_KEY", "LLM_TIMEOUT"]
    assert os.environ["LLM_PROVIDER"] == "mock" and os.environ["GEMINI_API_KEY"] == "synthetic-value"
    assert os.environ["LLM_TIMEOUT"] == "30" and "LLM_MODEL" not in os.environ
    assert llm.load_env_file(tmp_path / "missing.env") == []


# --- Claude API (Anthropic), the documented default provider -----------------------------------

FAKE_ANTHROPIC_KEY = "synthetic-anthropic-test-value"


@pytest.fixture
def claude(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_ANTHROPIC_KEY)  # no LLM_PROVIDER: the key alone selects Claude
    monkeypatch.setenv("NORM_KI_RECHERCHE", "off")


def claude_reply(text, stop_reason="end_turn", **extra):
    return {"type": "message", "role": "assistant", "content": [{"type": "text", "text": text}],
            "stop_reason": stop_reason, **extra}


def stub_claude(monkeypatch, reply, calls=None):
    """`reply(items, payload)` returns a Messages API response dict or raises."""
    lock = threading.Lock()

    def fake_post(url, headers, json, timeout):
        items = items_of(json)
        with lock:
            if calls is not None:
                calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout, "items": items})
        return httpx.Response(200, json=reply(items, json), request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "post", fake_post)


def test_claude_health_reports_anthropic_and_the_default_model(claude, monkeypatch):
    health = client.get("/health").json()
    assert (health["provider"], health["model"], health["mock"]) == ("anthropic", "claude-sonnet-5-5", False)
    assert FAKE_ANTHROPIC_KEY not in json.dumps(health)
    monkeypatch.setenv("LLM_MODEL", "claude-test-model")
    assert client.get("/health").json()["model"] == "claude-test-model"


def test_claude_review_sends_all_positions_in_batches_with_a_clean_request(claude, monkeypatch):
    monkeypatch.setenv("LLM_BATCH_SIZE", "20")
    calls = []
    stub_claude(monkeypatch, lambda items, payload: claude_reply(
        "```json\n" + json.dumps({"findings": [finding_for(items[0]["oz"])]}) + "\n```"), calls)
    lv = synthetic_lv(45)
    response = client.post("/api/lv/pruefen", json=lv.model_dump(mode="json"))
    assert response.status_code == 200
    assert len(calls) == 3 and sorted(len(c["items"]) for c in calls) == [5, 20, 20]
    assert sorted(i["oz"] for c in calls for i in c["items"]) == [p.oz for p in lv.positionen]
    call = calls[0]
    assert call["url"] == "https://api.anthropic.com/v1/messages"
    assert call["headers"]["x-api-key"] == FAKE_ANTHROPIC_KEY and call["headers"]["anthropic-version"]
    assert call["headers"]["content-type"] == "application/json"
    body = call["json"]
    assert body["model"] == "claude-sonnet-5-5" and body["system"] == llm_pruefung.SYSTEM
    assert [m["role"] for m in body["messages"]] == ["user"]  # no assistant prefill
    assert not {"temperature", "top_p", "top_k", "thinking"} & set(body)
    assert body["output_config"] == {"effort": "low"}
    kennzahlen = response.json()["kennzahlen"]
    assert kennzahlen["modell_mock"] is False and kennzahlen["modell"] == "anthropic/claude-sonnet-5-5"
    model_findings = [f for f in response.json()["findings"] if f["quelle"] == "modell"]
    assert sorted(f["oz"] for f in model_findings) == ["01.000", "01.020", "01.040"]
    assert FAKE_ANTHROPIC_KEY not in response.text


@pytest.mark.parametrize("reply, expected", [
    (claude_reply("", "refusal", stop_details={"type": "refusal", "category": "cyber"}), "declined the request (refusal: cyber)"),
    (claude_reply('{"findings": [', "max_tokens"), "stopped at max_tokens"),
    ({"content": [], "stop_reason": "end_turn"}, "no text"),
])
def test_claude_refusal_or_truncation_falls_back_to_mock(claude, monkeypatch, reply, expected):
    stub_claude(monkeypatch, lambda items, payload: reply)
    response = client.post("/api/lv/pruefen", json=beispiel())
    assert response.status_code == 200
    kennzahlen = response.json()["kennzahlen"]
    assert kennzahlen["modell_mock"] is True and expected in kennzahlen["modell_reason"]
    assert [f["regel_id"] for f in response.json()["findings"]].count("MOCK_LLM") == 1


@pytest.mark.parametrize("code", [401, 429, 529])
def test_claude_http_error_falls_back_with_readable_reason(claude, monkeypatch, code):
    def fake_post(url, headers, json, timeout):
        return httpx.Response(code, json={"type": "error", "error": {"message": FAKE_ANTHROPIC_KEY}},
                              request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "post", fake_post)
    response = client.post("/api/lv/pruefen", json=beispiel())
    assert response.status_code == 200
    assert f"anthropic returned HTTP {code}" in response.json()["kennzahlen"]["modell_reason"]
    assert FAKE_ANTHROPIC_KEY not in response.text


def test_claude_timeout_falls_back_and_endpoint_returns_200(claude, monkeypatch):
    stub_claude(monkeypatch, raising(httpx.ReadTimeout("slow")))
    response = client.post("/api/lv/pruefen", json=beispiel())
    assert response.status_code == 200
    reason = response.json()["kennzahlen"]["modell_reason"]
    assert response.json()["kennzahlen"]["modell_mock"] is True and "anthropic did not answer within" in reason


def test_claude_effort_is_optional_for_other_callers(claude, monkeypatch):
    """`llm.complete(prompt, system, max_tokens)` (Excel import #9) sends no effort unless configured."""
    seen = []
    def fake_post(url, headers, json, timeout):
        seen.append(json)
        return httpx.Response(200, json=claude_reply("ok"), request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "post", fake_post)
    assert llm.complete("prompt", "system", 99).text == "ok"
    assert "output_config" not in seen[-1] and seen[-1]["max_tokens"] == 99
    monkeypatch.setenv("ANTHROPIC_EFFORT", "medium")
    llm.complete("prompt")
    assert seen[-1]["output_config"] == {"effort": "medium"}
    llm.complete("prompt", effort="nonsense")
    assert "output_config" not in seen[-1]


def test_batch_progress_and_failed_batches_reach_the_job_progress_api(gemini, monkeypatch):
    """#167 on #165: each model batch reports into step 3 of the job's progress; a failed batch is a visible error."""
    from app import main
    from app.fortschritt import Aufzeichnung
    monkeypatch.setenv("LLM_BATCH_SIZE", "2")
    monkeypatch.setenv("LLM_PARALLEL", "1")

    def answer(items, payload):
        if items[0]["oz"] == "01.002":
            raise httpx.ConnectError("down")
        return json.dumps({"findings": []})
    stub(monkeypatch, answer)
    aufzeichnung = Aufzeichnung()
    bericht = main._pruefbericht(synthetic_lv(5), fortschritt=aufzeichnung)
    batches = [(m[2], m[3]) for m in aufzeichnung.meldungen if m[0] == 3 and "batch" in m[2]]
    assert batches == [("AI item review: batch 1 of 3 done …", 1 / 3), ("AI item review: batch 2 of 3 done …", 2 / 3),
                       ("AI item review: batch 3 of 3 done …", 1.0)]
    assert len(aufzeichnung.fehlerliste) == 1 and "1/3 model batch(es) failed" in aufzeichnung.fehlerliste[0]
    assert bericht.kennzahlen.modell_batches_fehlgeschlagen == 1
    schritt = next(s for s in bericht.ki_schritte if s.schritt == "positionspruefung")
    assert schritt.status == "fehler" and "batch 2" in schritt.grund


def test_job_abort_inside_the_review_is_not_swallowed(gemini, monkeypatch):
    from app.fortschritt import AnalyseAbgebrochen
    stub(monkeypatch, lambda items, payload: json.dumps({"findings": []}))

    def abbrechen(done, total):
        raise AnalyseAbgebrochen()
    with pytest.raises(AnalyseAbgebrochen):
        pruefe_mit_llm_status(synthetic_lv(3), fortschritt=abbrechen)

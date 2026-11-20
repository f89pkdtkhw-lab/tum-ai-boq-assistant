"""Offline contract tests for the structured provider boundary."""
import pytest

from app.ai import llm


@pytest.fixture(autouse=True)
def clean_run_configuration(monkeypatch):
    for name in ("LLM_RUN_MAX_TOKENS", "LLM_RUN_MAX_COST", "LLM_BATCH_SIZE"):
        monkeypatch.delenv(name, raising=False)


def test_structured_default_is_offline_even_with_provider_keys(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic-test-key")

    def forbid_network(*args, **kwargs):
        pytest.fail("Structured mock attempted network access")

    monkeypatch.setattr(llm.httpx, "post", forbid_network)
    request = llm.JsonRequest("comparison", {"oz": "01.001"}, {"findings": [], "demo": True})
    answer, = llm.StructuredRun().complete_batch([request])
    assert answer.data == {"findings": [], "demo": True}
    assert answer.source == "model_mock"
    assert not answer.cached
    assert len(answer.input_hash) == 64
    assert llm.mock("offline").provider == "mock"


def test_batches_cache_and_caller_mutation_are_isolated():
    calls = []

    def simulator(payloads, max_output_tokens):
        calls.append(payloads)
        return [{"oz": payload["input"]["oz"], "demo": True} for payload in payloads]

    run = llm.StructuredRun(batch_size=2, simulator=simulator)
    requests = [llm.JsonRequest("comparison", {"oz": str(i)}, {"demo": True}) for i in range(5)]
    answers = run.complete_batch(requests + [requests[0]])
    assert [len(call) for call in calls] == [2, 2, 1]
    assert [a.data["oz"] for a in answers] == ["0", "1", "2", "3", "4", "0"]
    assert answers[-1].cached
    answers[0].data["oz"] = "mutated"
    cached, = run.complete_batch([requests[0]])
    assert cached.cached and cached.data["oz"] == "0"
    assert len(calls) == 3


def test_cache_uses_canonical_full_request_and_output_limit():
    run = llm.StructuredRun()
    first = llm.JsonRequest("comparison", {"oz": "1", "text": "x"}, {"demo": True})
    reordered = llm.JsonRequest("comparison", {"text": "x", "oz": "1"}, {"demo": True})
    a, = run.complete_batch([first])
    b, = run.complete_batch([reordered])
    assert a.input_hash == b.input_hash and b.cached
    variants = [
        llm.JsonRequest("metadata", first.input, first.mock_response),
        llm.JsonRequest(first.task, {"oz": "2"}, first.mock_response),
        llm.JsonRequest(first.task, first.input, {"demo": False}),
    ]
    assert all(not answer.cached for answer in run.complete_batch(variants))
    c, = run.complete_batch([first], max_output_tokens=512)
    assert not c.cached and c.input_hash != a.input_hash
    assert not llm.StructuredRun().complete_batch([first])[0].cached


@pytest.mark.parametrize("limits", [
    {"max_tokens": 39},
    {"max_cost": "0.039", "cost_per_token": "0.001"},
])
def test_budget_reserves_before_call_and_cache_hits_are_free(limits):
    calls = []

    def simulator(payloads, max_output_tokens):
        calls.append(payloads)
        return [{"ok": True}]

    # Canonical {"task":"x","input":{}} is 23 UTF-8 bytes + 16 reserved output.
    run = llm.StructuredRun(simulator=simulator, **limits)
    first = llm.JsonRequest("x", {}, {"ok": True})
    run.complete_batch([first], max_output_tokens=16)
    assert run.reserved_tokens == 39
    assert run.complete_batch([first], max_output_tokens=16)[0].cached
    with pytest.raises(llm.BudgetExceeded, match="budget"):
        run.complete_batch([llm.JsonRequest("y", {}, {"ok": True})], max_output_tokens=16)
    assert len(calls) == 1


def test_zero_token_cap_rejects_work_but_accepts_empty_input():
    run = llm.StructuredRun(max_tokens=0)
    assert run.complete_batch([]) == []
    with pytest.raises(llm.BudgetExceeded):
        run.complete_batch([llm.JsonRequest("x", {}, {})])


@pytest.mark.parametrize("reply", [
    ["not JSON"], ["[]"], ["null"], ["{\"x\":NaN}"],
    [], [{}, {}], [{"x": "a" * 100}],
])
def test_invalid_response_fails_without_cache_and_retains_reservation(reply):
    calls = []

    def simulator(payloads, max_output_tokens):
        calls.append(payloads)
        return reply

    run = llm.StructuredRun(simulator=simulator, max_tokens=39)
    request = llm.JsonRequest("x", {}, {})
    with pytest.raises(llm.LLMError, match="response"):
        run.complete_batch([request], max_output_tokens=16)
    assert run.reserved_tokens == 39
    with pytest.raises(llm.BudgetExceeded):
        run.complete_batch([request], max_output_tokens=16)
    assert len(calls) == 1


def test_simulator_error_is_sanitized_and_not_retried():
    calls = []

    def simulator(payloads, max_output_tokens):
        calls.append(payloads)
        raise RuntimeError("synthetic-secret and confidential LV")

    run = llm.StructuredRun(simulator=simulator)
    with pytest.raises(llm.LLMError) as error:
        run.complete_batch([llm.JsonRequest("x", {}, {})])
    assert "synthetic-secret" not in str(error.value)
    assert "confidential" not in str(error.value)
    assert error.value.__cause__ is None
    assert len(calls) == 1 and run.reserved_tokens > 0


def test_json_strings_are_parsed_and_batches_fail_atomically():
    replies = ['{"demo":true}', "invalid"]
    run = llm.StructuredRun(simulator=lambda payloads, limit: replies)
    requests = [llm.JsonRequest("x", {"oz": str(i)}, {}) for i in range(2)]
    with pytest.raises(llm.LLMError):
        run.complete_batch(requests)
    replies[:] = ['{"demo":true}', '{"demo":false}']
    answers = run.complete_batch(requests)
    assert [a.data for a in answers] == [{"demo": True}, {"demo": False}]
    assert all(not a.cached for a in answers)


@pytest.mark.parametrize("input_data", [[], {"bad": float("nan")}, {1: "bad"}, {"bad": object()}])
def test_invalid_json_input_fails_before_budget_is_reserved(input_data):
    run = llm.StructuredRun()
    with pytest.raises(llm.LLMError, match="request"):
        run.complete_batch([llm.JsonRequest("x", input_data, {})])
    assert run.reserved_tokens == 0


@pytest.mark.parametrize("name,value", [
    ("LLM_RUN_MAX_TOKENS", "-1"), ("LLM_RUN_MAX_TOKENS", "1.5"),
    ("LLM_RUN_MAX_COST", "NaN"), ("LLM_RUN_MAX_COST", "Infinity"),
    ("LLM_RUN_MAX_COST", "-1"), ("LLM_BATCH_SIZE", "0"),
    ("LLM_BATCH_SIZE", "synthetic-secret"),
])
def test_invalid_environment_configuration_is_safe(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(llm.LLMError) as error:
        llm.StructuredRun()
    assert name in str(error.value)
    assert "synthetic-secret" not in str(error.value)


def test_environment_limits_and_explicit_override(monkeypatch):
    monkeypatch.setenv("LLM_RUN_MAX_TOKENS", "0")
    monkeypatch.setenv("LLM_RUN_MAX_COST", "0")
    monkeypatch.setenv("LLM_BATCH_SIZE", "1")
    request = llm.JsonRequest("x", {}, {})
    with pytest.raises(llm.BudgetExceeded):
        llm.StructuredRun().complete_batch([request])
    assert llm.StructuredRun(max_tokens=2000).complete_batch([request])[0].data == {}


def test_utf8_input_reservation_and_batch_cap_apply_before_invocation():
    calls = []
    run = llm.StructuredRun(max_tokens=39, simulator=lambda *args: calls.append(args))
    with pytest.raises(llm.BudgetExceeded):
        # Two-byte UTF-8 task exceeds the 39-token ASCII example by one byte.
        run.complete_batch([llm.JsonRequest("ä", {}, {})], max_output_tokens=16)
    assert calls == [] and run.reserved_tokens == 0
    with pytest.raises(llm.BudgetExceeded):
        run.complete_batch([llm.JsonRequest("x", {}, {}), llm.JsonRequest("y", {}, {})],
                           max_output_tokens=16)
    assert calls == [] and run.reserved_tokens == 0


def test_concurrent_calls_share_the_same_token_cap():
    from concurrent.futures import ThreadPoolExecutor

    run = llm.StructuredRun(max_tokens=39)

    def invoke(task):
        try:
            run.complete_batch([llm.JsonRequest(task, {}, {})], max_output_tokens=16)
            return "ok"
        except llm.BudgetExceeded:
            return "capped"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(invoke, ["x", "y"])) == ["capped", "ok"]
    assert run.reserved_tokens == 39

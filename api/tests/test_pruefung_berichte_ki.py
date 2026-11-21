"""#167: AI checks 2/3 with Claude on top of the deterministic Reports 2/3.

Synthetic records only (from test_pruefung_berichte); the HTTP layer is stubbed, no network.
"""
import json

import httpx
import pytest

from app.pruefung import berichte_ki
from app.pruefung.berichte import erstelle_berichte

from tests.test_pruefung_berichte import BRIDGE, ROAD, FakeDB, synthetic_lv

FAKE_KEY = "sk-ant-test-berichte"


@pytest.fixture
def claude(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)


def stub(monkeypatch, answer, calls):
    """`answer(system, prompt)` returns the model text or raises."""
    def fake_post(url, headers, json, timeout):
        calls.append(json)
        text = answer(json.get("system", ""), json["messages"][0]["content"])
        return httpx.Response(200, json={"content": [{"type": "text", "text": text}], "stop_reason": "end_turn"},
                              request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "post", fake_post)


def rating_from(prompt, chance, oz):
    problems = json.loads(prompt.split("Problems from past projects:\n", 1)[1])
    return [{"index": p["index"], "chance": chance, "oz": oz, "empfehlung": "Raise the pumping hours.",
             "begruendung": "Same groundwater work."} for p in problems]


def test_without_a_key_no_model_call_and_identical_result(monkeypatch):
    calls = []
    stub(monkeypatch, lambda s, p: "{}", calls)
    teile = erstelle_berichte(synthetic_lv(), [], db=FakeDB(BRIDGE + ROAD))
    assert calls == []
    assert "Claude" not in teile["berichte"][1].meldung and "Claude" not in teile["berichte"][2].meldung


def test_claude_adds_tags_from_the_db_list_only_and_rates_chances(claude, monkeypatch):
    calls = []

    def answer(system, prompt):
        if system == berichte_ki.SYSTEM_TAGS:
            return json.dumps({"tags": ["road", "invented-tag", "bridge"]})
        return json.dumps({"ratings": rating_from(prompt, "hoch", "01.002")})
    stub(monkeypatch, answer, calls)
    teile = erstelle_berichte(synthetic_lv(), [], db=FakeDB(BRIDGE + ROAD))
    vergleich, was_wenn = teile["berichte"][1], teile["berichte"][2]
    assert vergleich.tags == ["bridge", "concrete", "road"]  # deterministic first, invented tag dropped
    assert "Claude matched tag(s) road" in vergleich.meldung and "rated by Claude" in was_wenn.meldung
    asphalt = next(w for w in was_wenn.probleme if "Asphalt" in w.problem)
    assert not asphalt.begruendung.startswith(berichte_ki.MODELL_PRAEFIX)  # 01.002 is no candidate: rejected
    grundwasser = next(w for w in was_wenn.probleme if "Groundwater" in w.problem)
    assert (grundwasser.chance, grundwasser.oz) == ("hoch", "01.002")
    assert grundwasser.begruendung == berichte_ki.MODELL_PRAEFIX + "Same groundwater work."
    assert grundwasser.empfehlung.endswith(berichte_ki.FREIGABE)
    assert all(not {"temperature", "top_p", "top_k", "thinking"} & set(c) for c in calls)
    assert len(calls) == 3  # tags, Report 2 problems, Report 3 problems


def test_invented_oz_is_rejected_and_keeps_the_deterministic_rating(claude, monkeypatch):
    def answer(system, prompt):
        if system == berichte_ki.SYSTEM_TAGS:
            return json.dumps({"tags": []})
        return json.dumps({"ratings": rating_from(prompt, "hoch", "99.999")})
    stub(monkeypatch, answer, [])
    was_wenn = erstelle_berichte(synthetic_lv(), [], db=FakeDB(BRIDGE + ROAD))["berichte"][2]
    assert not any(w.begruendung.startswith(berichte_ki.MODELL_PRAEFIX) for w in was_wenn.probleme)


@pytest.mark.parametrize("reply", ["not json", json.dumps({"something": 1})])
def test_invalid_model_answer_keeps_the_deterministic_reports(claude, monkeypatch, reply):
    stub(monkeypatch, lambda s, p: reply, [])
    offline = erstelle_berichte(synthetic_lv(), [], db=FakeDB(BRIDGE + ROAD))
    assert [w.model_dump() for w in offline["berichte"][2].probleme]
    assert "Claude" not in offline["berichte"][2].meldung


def test_model_http_error_never_breaks_the_reports(claude, monkeypatch):
    def fake_post(url, headers, json, timeout):
        return httpx.Response(529, json={}, request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "post", fake_post)
    teile = erstelle_berichte(synthetic_lv(), [], db=FakeDB(BRIDGE + ROAD))
    assert [b.status for b in teile["berichte"]] == ["ok", "ok", "ok"]

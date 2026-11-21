"""E #169: deep research with web search in every AI step. Offline: the Claude call is stubbed."""
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main
from app.ai import llm
from app.modelle import (
    Bericht, Finding, Kalkulation, KalkulationsPosition, Kennzahlen, LV, Position, Pruefbericht, WasWenn,
)
from app.pruefung import berichte, recherche
from app.pruefung.recherche import Antwort, Einstellungen

DATA = Path(__file__).resolve().parents[2] / "data"
URL_A, URL_B = "https://example.org/trockenbau", "https://example.org/preise"


def _lv(n=4):
    return LV(name="Synthetic", quelle="test", positionen=[
        Position(oz=f"01.{i:02d}", kurztext=f"Item {i}", langtext="Synthetic text", menge=10, einheit="m2",
                 ep=100.0, titel_pfad=["Drywall" if i % 2 else "Concrete"]) for i in range(1, n + 1)])


def _finding(oz, schwere="hoch", kategorie="fehler", regel="TEXT_WIDERSPRUCH"):
    return Finding(id=f"f-{oz}", oz=oz, kategorie=kategorie, schwere=schwere, titel="Contradiction",
                   begruendung="Short and long text disagree.", vorschlag="Clarify.", quelle="regel", regel_id=regel)


def _bericht(findings, lv=None, **extra):
    lv = lv or _lv()
    return Pruefbericht(lv=lv, findings=findings, kennzahlen=Kennzahlen(
        positionen=len(lv.positionen), findings=len(findings), kritisch=0, modell_mock=False), **extra)


def _cfg(**k):
    base = dict(max_uses=2, max_calls=6, budget=10, max_items=8, timeout=10.0, parallel=2)
    return Einstellungen(**{**base, **k})


class Stub:
    """Fake research call: answers every finding/oz/index of the input with the given sources."""

    def __init__(self, einschaetzung="bestaetigt", quellen=(URL_A,), gesehen=(URL_A,), suchen=1):
        self.calls, self.einschaetzung, self.quellen, self.gesehen, self.suchen = [], einschaetzung, quellen, gesehen, suchen

    def __call__(self, prompt, *, system, max_uses, max_tokens, timeout):
        self.calls.append({"prompt": prompt, "max_uses": max_uses})
        eingabe = json.loads(prompt.split("Input:\n", 1)[1])
        out = []
        for e in eingabe:
            key = "finding_id" if "finding_id" in e else "oz" if "ep_lv" in e else "index"
            out.append({key: e[key], "einschaetzung": self.einschaetzung, "text": "Sources agree.",
                        "quellen": list(self.quellen), "marktpreis_von": 40, "marktpreis_bis": 60})
        return Antwort("Research notes.\n" + json.dumps({"ergebnisse": out}),
                       {u: "Example source" for u in self.gesehen}, self.suchen)


def test_mock_mode_report_is_unchanged_and_has_no_recherche_field():
    lv = LV.model_validate_json((DATA / "beispiel_lv.json").read_bytes())
    client = TestClient(main.app)
    antwort = client.post("/api/lv/pruefen", json=lv.model_dump()).json()
    assert "recherche" not in antwort
    assert antwort == json.loads(main._pruefbericht(lv).model_dump_json())


def test_no_research_without_claude_but_reason_for_other_provider(monkeypatch):
    monkeypatch.delenv("DEEP_RESEARCH")
    bericht = _bericht([_finding("01.01")])
    assert recherche.vertiefe_recherche(bericht) is bericht
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    ergebnis = recherche.vertiefe_recherche(bericht)
    assert ergebnis.recherche.status == "aus" and "Claude" in ergebnis.recherche.meldung
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("DEEP_RESEARCH", "off")
    assert recherche.vertiefe_recherche(bericht) is bericht


def test_findings_get_sourced_research_grouped_by_trade():
    bericht = _bericht([_finding("01.01"), _finding("01.03"), _finding("01.02", schwere="niedrig")])
    stub = Stub()
    ergebnis = recherche.vertiefe_recherche(bericht, aufruf=stub, einstellungen=_cfg())
    assert len(stub.calls) == 1  # one trade group (Drywall); the low-severity error is not researched
    texte = {f.id: f.begruendung for f in ergebnis.findings}
    assert URL_A in texte["f-01.01"] and "Web research (confirmed)" in texte["f-01.03"]
    assert "Web research" not in texte["f-01.02"]
    r = ergebnis.recherche
    assert r.status == "ok" and r.aufrufe == 1 and r.suchen == 1
    assert {e.finding_id for e in r.ergebnisse} == {"f-01.01", "f-01.03"}
    assert r.ergebnisse[0].quellen[0].url == URL_A
    assert [(s.schritt, s.status) for s in ergebnis.ki_schritte] == [("recherche", "ok")]


def test_unseen_source_urls_are_dropped():
    bericht = _bericht([_finding("01.01")])
    ergebnis = recherche.vertiefe_recherche(
        bericht, aufruf=Stub(quellen=("https://invented.example/x",)), einstellungen=_cfg())
    assert ergebnis.recherche.ergebnisse == []
    assert ergebnis.findings == bericht.findings


def test_calls_and_searches_are_capped_for_a_large_bill():
    lv = LV(name="Big", quelle="t", positionen=[
        Position(oz=f"{g:02d}.{i:03d}", kurztext="x", einheit="m2", menge=1, titel_pfad=[f"Trade {g}"])
        for g in range(12) for i in range(200)])
    bericht = _bericht([_finding(p.oz) for p in lv.positionen], lv=lv)
    stub = Stub(suchen=2)
    ergebnis = recherche.vertiefe_recherche(bericht, aufruf=stub,
                                            einstellungen=_cfg(max_calls=6, budget=6, max_uses=2, max_items=5))
    assert len(stub.calls) == 3  # budget 6 / 2 searches per call
    assert all(len(json.loads(c["prompt"].split("Input:\n", 1)[1])) == 5 for c in stub.calls)
    assert ergebnis.recherche.suchen == 6 and "skipped" in ergebnis.recherche.meldung


def test_price_research_creates_a_sourced_finding_and_recounts_report_1():
    lv = _lv(2)
    kalk = Kalkulation(mwst_satz=0.19, summe_netto=0, summe_brutto=0, ohne_preis=0, ohne_menge=0, vollstaendig=True,
                       positionen=[KalkulationsPosition(oz="01.01", einheit="m2", ep=50.0, ep_lv=100.0,
                                                        treffer="oz", in_summe=True),
                                   KalkulationsPosition(oz="01.02", einheit="m2", ep=98.0, ep_lv=100.0,
                                                        treffer="oz", in_summe=True)])
    teile = berichte.erstelle_berichte(lv, [], db=None)
    bericht = _bericht([], lv=lv, kalkulation=kalk, berichte=teile["berichte"],
                       schlussbericht=teile["schlussbericht"])
    stub = Stub(einschaetzung="zu_hoch", quellen=(URL_B,), gesehen=(URL_B,))
    ergebnis = recherche.vertiefe_recherche(bericht, aufruf=stub, einstellungen=_cfg())
    assert len(stub.calls) == 1 and '"01.02"' not in stub.calls[0]["prompt"]  # only the 100 % outlier
    [f] = ergebnis.findings
    assert f.regel_id == recherche.REGEL_PREIS and f.quelle == "modell" and f.euro_wirkung is None
    assert URL_B in f.begruendung and "40–60 EUR" in f.begruendung
    assert ergebnis.kennzahlen.findings == 1 and ergebnis.berichte[0].finding_ids == [f.id]
    assert ergebnis.schlussbericht.positionen[0].probleme[0].finding_id == f.id
    assert ergebnis.recherche.ergebnisse[0].finding_id == f.id


def test_report_problems_get_sources():
    lv = _lv(2)
    regelwerk = berichte.bericht_regelwerk([])
    vergleich = Bericht(id="vergleich", titel="2", status="ok")
    was_wenn = Bericht(id="was_wenn", titel="3", status="ok", probleme=[
        WasWenn(oz="01.01", problem="Groundwater in excavation", chance="hoch", begruendung="Seen in 2 cases.")])
    bericht = _bericht([], lv=lv, berichte=[regelwerk, vergleich, was_wenn], was_wenn=was_wenn.probleme)
    ergebnis = recherche.vertiefe_recherche(bericht, aufruf=Stub(), einstellungen=_cfg())
    text = ergebnis.berichte[2].probleme[0].begruendung
    assert text.startswith("Seen in 2 cases.") and URL_A in text
    assert ergebnis.was_wenn[0].begruendung == text
    assert bericht.berichte[2].probleme[0].begruendung == "Seen in 2 cases."  # input not mutated


def test_failures_are_visible_not_silent():
    def kaputt(*a, **k):
        raise llm.LLMError("anthropic research returned HTTP 529. Check the key, model and web search access.")
    bericht = _bericht([_finding("01.01")])
    ergebnis = recherche.vertiefe_recherche(bericht, aufruf=kaputt, einstellungen=_cfg())
    assert ergebnis.recherche.status == "fehler" and "HTTP 529" in ergebnis.recherche.meldung
    [schritt] = ergebnis.ki_schritte  # D #168: the failure is also an AI step status
    assert schritt.schritt == "recherche" and schritt.status == "fehler" and "HTTP 529" in schritt.grund
    assert ergebnis.findings == bericht.findings


def test_nothing_conspicuous_makes_no_call():
    stub = Stub()
    ergebnis = recherche.vertiefe_recherche(_bericht([_finding("01.01", schwere="niedrig")]), aufruf=stub,
                                            einstellungen=_cfg())
    assert stub.calls == [] and ergebnis.recherche.status == "ok"


def _antwort(content, stop="end_turn", searches=1):
    return {"content": content, "stop_reason": stop, "usage": {"server_tool_use": {"web_search_requests": searches}}}


def test_claude_call_sends_web_search_tool_and_continues_pause_turn(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")
    gesendet = []
    antworten = [
        _antwort([{"type": "server_tool_use", "id": "s1", "name": "web_search", "input": {"query": "q"}},
                  {"type": "web_search_tool_result", "tool_use_id": "s1",
                   "content": [{"type": "web_search_result", "url": URL_A + "/", "title": "Drywall guide"}]}],
                 stop="pause_turn"),
        _antwort([{"type": "text", "text": "Found it.", "citations": [
            {"type": "web_search_result_location", "url": URL_B, "title": "Prices", "cited_text": "x"}]},
                  {"type": "text", "text": '{"ergebnisse": []}'}]),
    ]

    def post(url, headers, payload, timeout=None):
        gesendet.append(json.loads(json.dumps(payload)))
        return antworten[len(gesendet) - 1]

    monkeypatch.setattr(llm, "_post", post)
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    antwort = recherche.claude_recherche("prompt", "system", max_uses=2, timeout=5)
    assert gesendet[0]["tools"] == [{"type": "web_search_20250305", "name": "web_search", "max_uses": 2}]
    assert not {"temperature", "top_p", "top_k", "thinking"} & set(gesendet[0])
    assert gesendet[1]["messages"][-1]["role"] == "assistant"  # pause_turn sent back to continue
    assert antwort.quellen == {URL_A: "Drywall guide", URL_B: "Prices"}
    assert antwort.suchen == 2 and antwort.text.endswith('{"ergebnisse": []}')


@pytest.mark.parametrize("daten,meldung", [
    (_antwort([], stop="refusal"), "refusal"),
    (_antwort([], stop="max_tokens"), "max_tokens"),
])
def test_claude_call_raises_readable_errors(monkeypatch, daten, meldung):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")
    monkeypatch.setattr(llm, "_post", lambda *a, **k: daten)
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    with pytest.raises(llm.LLMError, match=meldung):
        recherche.claude_recherche("p", max_uses=1, timeout=5)


def test_claude_keeps_complete_results_when_cut_off_at_max_tokens(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    vollständig = {"finding_id": "f-01.01", "einschaetzung": "bestaetigt", "text": "Sources agree.",
                   "quellen": [URL_A]}
    text = json.dumps({"ergebnisse": [vollständig, {"finding_id": "f-01.03", "einschaetzung": "bestaetigt"}]})
    text = text[:text.find('"f-01.03"') + 20]  # cut mid-object, as a max_tokens stop would
    daten = _antwort([{"type": "text", "text": text, "citations": [
        {"type": "web_search_result_location", "url": URL_A, "title": "Drywall guide", "cited_text": "x"}]}],
                     stop="max_tokens")
    monkeypatch.setattr(llm, "_post", lambda *a, **k: daten)
    antwort = recherche.claude_recherche("p", max_uses=1, timeout=5)
    assert antwort.unvollstaendig and URL_A in antwort.quellen
    bericht = _bericht([_finding("01.01"), _finding("01.03")])
    ergebnis = recherche.vertiefe_recherche(bericht, aufruf=lambda *a, **k: antwort, einstellungen=_cfg())
    ids = {e.finding_id for e in ergebnis.recherche.ergebnisse}
    assert ids == {"f-01.01"} and "max_tokens" in ergebnis.recherche.meldung
    assert ergebnis.recherche.status == "teilweise"
    assert URL_A in {f.id: f.begruendung for f in ergebnis.findings}["f-01.01"]


def test_claude_http_error_is_ui_safe(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret-value")

    def post(*a, **k):
        raise httpx.HTTPStatusError("x", request=httpx.Request("POST", "https://x"), response=httpx.Response(401))

    monkeypatch.setattr(llm, "_post", post)
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    with pytest.raises(llm.LLMError) as info:
        recherche.claude_recherche("p", max_uses=1, timeout=5)
    assert "HTTP 401" in str(info.value) and "secret-value" not in str(info.value)


def test_progress_reports_one_step_with_shares_and_visible_errors():
    from app.fortschritt import Aufzeichnung
    aufzeichnung = Aufzeichnung()
    bericht = _bericht([_finding("01.01"), _finding("01.02")])  # two trades → two groups
    recherche.vertiefe_recherche(bericht, aufruf=Stub(), einstellungen=_cfg(), fortschritt=aufzeichnung,
                                 schritt=9, gesamt=9)
    assert {(s, g) for s, g, _, _ in aufzeichnung.meldungen} == {(9, 9)}
    assert aufzeichnung.meldungen[0][3] == 0.0 and aufzeichnung.meldungen[-1][3] == 1.0
    assert aufzeichnung.fehlerliste == []

    def kaputt(*a, **k):
        raise llm.LLMError("anthropic research returned HTTP 529.")
    aufzeichnung = Aufzeichnung()
    recherche.vertiefe_recherche(bericht, aufruf=kaputt, einstellungen=_cfg(), fortschritt=aufzeichnung)
    assert aufzeichnung.fehlerliste == ["Web research: anthropic research returned HTTP 529."]


def test_job_with_claude_counts_the_research_step(monkeypatch):
    from app.pruefung import llm_pruefung
    from tests.test_api_analyse_job import warte
    monkeypatch.delenv("DEEP_RESEARCH")
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic-not-a-key")
    monkeypatch.setenv("NORM_KI_RECHERCHE", "off")
    monkeypatch.setattr(main, "pruefe_mit_llm_status", llm_pruefung.mock_pruefung)
    stub = Stub()
    monkeypatch.setattr(recherche, "claude_recherche", stub)
    lv = LV.model_validate_json((DATA / "beispiel_lv.json").read_bytes()).model_dump(mode="json")
    client = TestClient(main.app)
    stand = warte(client.post("/api/lv/analyse/start", json={"lv": lv, "nur_pruefen": True}).json()["job_id"])
    assert stand["status"] == "fertig" and stand["schritte_gesamt"] == 8
    assert stand["fertige_schritte"][-1]["meldung"].startswith("Web research:")
    assert stand["ergebnis"]["recherche"]["status"] == "ok" and stub.calls
    sync = client.post("/api/lv/pruefen", json=lv).json()
    assert sync["recherche"] == stand["ergebnis"]["recherche"]

def test_plan_gives_every_step_a_call_even_with_many_trades():
    # Many finding-trades must not use up a small call cap before prices and reports get a turn.
    pos = [recherche.Gruppe("positionen", f"Trade {i}", [{"finding_id": f"f{i}"}], 1) for i in range(12)]
    preise = [recherche.Gruppe("preise", "Concrete", [{"oz": "01.01"}], 1)]
    berichte = [recherche.Gruppe("berichte", "Reports 2/3", [{"index": 0}], 2)]
    plan = recherche.plane([pos, preise, berichte], 5)
    schritte = [g.schritt for g in plan]
    assert schritte[:3] == ["positionen", "preise", "berichte"]
    assert schritte.count("positionen") == 3 and len(plan) == 5


def test_medium_severity_findings_are_researched():
    stub = Stub()
    bericht = _bericht([_finding("01.01", schwere="mittel")])
    ergebnis = recherche.vertiefe_recherche(bericht, aufruf=stub, einstellungen=_cfg())
    assert stub.calls and ergebnis.recherche.ergebnisse[0].finding_id == "f-01.01"


def test_truncated_json_keeps_complete_result_objects():
    text = ('{"ergebnisse": [{"finding_id": "f-01.01", "einschaetzung": "bestaetigt", '
            '"text": "Sources agree.", "quellen": ["' + URL_A + '"]}, {"finding_id": "f-01.03", '
            '"einschaetzung": "best')
    bericht = _bericht([_finding("01.01"), _finding("01.03")])
    gruppe = recherche.gruppen_positionen(bericht, 8)[0]
    paare = recherche.validiere(gruppe, Antwort(text, {URL_A: "Example source"}))
    assert [e["finding_id"] for e, _ in paare] == ["f-01.01"]


def test_default_limits_cover_all_steps_without_starving_the_budget():
    cfg = recherche.Einstellungen.aus_env()
    assert cfg.max_uses == 8 and cfg.max_calls == 24 and cfg.budget == 192
    assert cfg.max_items == 12 and cfg.timeout == 420 and cfg.parallel == 6
    assert recherche.MAX_TOKENS == 16000
    assert cfg.budget >= cfg.max_calls * cfg.max_uses

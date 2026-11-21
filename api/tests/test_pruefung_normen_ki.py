"""Norm check N5 (issue #87): AI research for missed standards, with a mocked model only.

Synthetic fixtures only; no dataset text. Offline: every model call goes to an injected fake,
and httpx is blocked so an accidental real call fails loudly.
"""
import json
import logging
import re
import threading
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main
from app.ai import llm
from app.modelle import LV, Position
from app.pruefung import llm_pruefung, normen, normen_ki
from app.pruefung.normen import KEIN_NORMGUTACHTEN, lade_register, pruefe_normen, pruefe_normen_sicher
from app.pruefung.normen_ki import (
    BESTAETIGT, NORM_KI_HINWEIS, UNBESTAETIGT, norm_ki_aktiv, recherchiere_normen, recherchiere_normen_sicher,
    vorschlaege_aus_antwort,
)

LLM_KEYS = ("LLM_PROVIDER", "LLM_MODEL", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "AZURE_OPENAI_API_KEY",
            "GEMINI_API_KEY", "OPENAI_BASE_URL", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT")
CLAIM_WORDS = re.compile(r"violat|breach|verstoß|verstoss|non-?complian", re.IGNORECASE)
UNBEKANNT = "DIN 99901"  # synthetic designation, deliberately absent from the register

LV_N5 = LV(name="Synthetic N5 LV", quelle="test", positionen=[
    Position(oz="01.01", kurztext="Bodenaushub", langtext="Boden lösen nach ATV DIN 18300 (2012-09), Bodenklasse 3-5.",
             menge=100, einheit="m³", titel_pfad=["Erdarbeiten"]),
    Position(oz="01.02", kurztext="Innenwand Mauerwerk", langtext="Wohnungstrennwand, schalltechnisch hochwertig.",
             menge=40, einheit="m²", titel_pfad=["Rohbau"]),
    Position(oz="01.03", kurztext="Stahlbeton Decke", langtext="Beton nach DIN 1045-2, C25/30, XC1.",
             menge=20, einheit="m³", titel_pfad=["Rohbau"]),
])


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """No keys from the developer's shell, no network, default switches."""
    for key in LLM_KEYS + ("NORM_KI_RECHERCHE", "NORM_KI_TIMEOUT", "NORM_KI_MAX_SEARCHES", "NORM_KI_RUNDEN",
                           "NORMPRUEFUNG"):
        monkeypatch.delenv(key, raising=False)
    normen_ki.cache_leeren()

    def kein_netz(*_, **__):
        raise AssertionError("no real model call in tests")
    monkeypatch.setattr(httpx, "post", kein_netz)


def antwort(*vorschlaege: dict) -> str:
    return json.dumps({"vorschlaege": list(vorschlaege)})


def fake(text: str, aufrufe: list | None = None):
    def client(prompt, system="", max_tokens=1024, **_):
        if aufrufe is not None:
            aufrufe.append({"prompt": prompt, "system": system, "max_tokens": max_tokens})
        return llm.Answer(text, "fake", "fake-model", 1)
    return client


def nicht_aufrufen(*_, **__):
    raise AssertionError("the model must not be called")


DIN_4109 = {"norm_id": "DIN 4109", "titel": "Schallschutz", "oz": ["01.02"],
            "begruendung": "Partition wall with sound insulation requirement.", "konfidenz": 0.8}
UNBEKANNT_VORSCHLAG = {"norm_id": UNBEKANNT, "titel": "Synthetic title", "oz": ["01.03"],
                       "begruendung": "Synthetic reasoning.", "konfidenz": "mittel"}


# --- Acceptance 1: register hit, unknown norm, already found by N1, errors ----------------------

def test_register_hit_becomes_one_confirmed_hint():
    [f] = recherchiere_normen(LV_N5, client=fake(antwort(DIN_4109)))
    assert (f.id, f.oz, f.kategorie, f.schwere, f.quelle, f.regel_id, f.euro_wirkung) == (
        f"{NORM_KI_HINWEIS}:01.02", "01.02", "risiko", "niedrig", "modell", NORM_KI_HINWEIS, None)
    assert BESTAETIGT in f.titel and BESTAETIGT in f.begruendung and UNBESTAETIGT not in f.begruendung
    eintrag = lade_register().suche("DIN 4109")
    assert eintrag.quelle["url"] in f.begruendung and eintrag.titel in f.begruendung
    assert "fake/fake-model" in f.begruendung and "Model confidence: high (0.80)" in f.begruendung
    assert f.vorschlag == ("OZ 01.02: Does DIN 4109 apply to these items? Please confirm, or name the "
                           "applicable standards and editions.")


def test_unknown_norm_stays_an_unconfirmed_hint():
    [f] = recherchiere_normen(LV_N5, client=fake(antwort(UNBEKANNT_VORSCHLAG)))
    assert UNBESTAETIGT in f.titel and UNBESTAETIGT in f.begruendung and BESTAETIGT not in f.begruendung
    assert "has no entry for it" in f.begruendung and "Source: norm register entry" not in f.begruendung
    assert "Model confidence: medium" in f.begruendung and f.oz == "01.03"


@pytest.mark.parametrize("schon_gefunden", [
    "DIN 1045-2", "DIN 1045 Teil 2", "DIN 1045", "DIN 18300", "ATV DIN 18300", "ATV DIN 18300:2019-09",
])
def test_norm_already_found_by_n1_creates_no_hint(schon_gefunden):
    vorschlag = {**DIN_4109, "norm_id": schon_gefunden, "oz": ["01.01", "01.03"]}
    assert recherchiere_normen(LV_N5, client=fake(antwort(vorschlag))) == []


@pytest.mark.parametrize("roh", [
    "not json at all",
    '{"vorschlaege": [{"norm_id": "DIN 4109", "oz": ["01.02"]',  # cut off
    json.dumps({"something": []}),
    json.dumps({"vorschlaege": "DIN 4109"}),
    antwort("DIN 4109", 42, None),
    antwort({**DIN_4109, "oz": ["99.99"]}),  # invented OZ
    antwort({**DIN_4109, "oz": []}),
    antwort({**DIN_4109, "norm_id": None}),
    antwort({**DIN_4109, "norm_id": "nach einschlägigen Normen"}),  # no designation
    "",
])
def test_invalid_or_partial_answers_are_dropped(roh):
    assert recherchiere_normen(LV_N5, client=fake(roh)) == []


def test_valid_entries_survive_next_to_invalid_ones():
    roh = "```json\n" + antwort("junk", {**DIN_4109, "oz": ["99.99"]}, UNBEKANNT_VORSCHLAG) + "\n```"
    assert [f.oz for f in recherchiere_normen(LV_N5, client=fake(roh))] == ["01.03"]


def test_duplicates_merge_their_oz_and_hints_follow_position_order():
    roh = antwort(UNBEKANNT_VORSCHLAG, {**DIN_4109, "oz": "01.02"}, {**UNBEKANNT_VORSCHLAG, "oz": ["01.02"]})
    findings = recherchiere_normen(LV_N5, client=fake(roh))
    assert [(f.oz, f.vorschlag.split(":")[0]) for f in findings] == [  # ties keep the model's order
        ("01.02", "OZ 01.02, 01.03"), ("01.02", "OZ 01.02")]
    assert UNBEKANNT in findings[0].titel and "DIN 4109" in findings[1].titel
    assert [f.id for f in findings] == [f"{NORM_KI_HINWEIS}:01.02", f"{NORM_KI_HINWEIS}:01.02:2"]


def test_model_receives_positions_and_the_n1_list_in_one_round_per_trade():
    aufrufe = []
    recherchiere_normen(LV_N5, client=fake(antwort(), aufrufe))
    eingaben = sorted((json.loads(a["prompt"]) for a in aufrufe), key=lambda e: e["positionen"][0]["oz"])
    assert [e["bereits_gefunden"] for e in eingaben] == [["ATV DIN 18300", "DIN 1045-2"]] * 2
    assert [[p["oz"] for p in e["positionen"]] for e in eingaben] == [["01.01"], ["01.02", "01.03"]]
    assert eingaben[1]["positionen"][0]["abschnitt"] == "Rohbau"
    for aufruf in aufrufe:
        assert "ADDITIONAL" in aufruf["system"] and "JSON" in aufruf["system"] and "web" in aufruf["system"]
        assert aufruf["max_tokens"] >= 8000


def kaputt(*_, **__):
    raise llm.LLMError("synthetic provider failure")


def langsam(freigabe: threading.Event):
    def client(*_, **__):
        freigabe.wait(5)
        return llm.Answer(antwort(DIN_4109), "fake", "fake-model", 1)
    return client


@pytest.mark.parametrize("fall", ["invalid", "error", "timeout"])
def test_errors_are_logged_and_n2_n3_findings_stay_unchanged(monkeypatch, caplog, fall):
    lv = LV_N5
    ohne_n5 = pruefe_normen(lv)
    assert ohne_n5, "fixture must produce N2/N3 findings"
    freigabe = threading.Event()
    client = {"invalid": fake("{not json"), "error": kaputt, "timeout": langsam(freigabe)}[fall]
    monkeypatch.setenv("NORM_KI_TIMEOUT", "0.05")
    monkeypatch.setattr(normen_ki, "recherchiere_normen_sicher",
                        lambda lv, client=client, _echt=normen_ki.recherchiere_normen_sicher: _echt(lv, client))
    try:
        with caplog.at_level(logging.ERROR, logger=normen_ki.__name__):
            assert pruefe_normen_sicher(lv) == ohne_n5
    finally:
        freigabe.set()
    if fall == "invalid":
        assert caplog.text == ""  # dropped silently, nothing to report
    else:
        assert "Norm check N5" in caplog.text
        assert ("timed out" if fall == "timeout" else "synthetic provider failure") in caplog.text


def test_a_broken_n5_module_never_breaks_the_norm_check(monkeypatch, caplog):
    monkeypatch.setattr(normen_ki, "recherchiere_normen_sicher", kaputt)
    with caplog.at_level(logging.ERROR, logger=normen.__name__):
        assert pruefe_normen_sicher(LV_N5) == pruefe_normen(LV_N5)
    assert "Norm check N5 failed" in caplog.text


# --- Acceptance 2: switch off and mock/offline mode leave the report unchanged -----------------

@pytest.mark.parametrize("wert, aktiv", [
    (None, True), ("", True), ("1", True), ("on", True), ("0", False), ("off", False), ("FALSE", False),
    (" no ", False),
])
def test_switch(monkeypatch, wert, aktiv):
    if wert is not None:
        monkeypatch.setenv("NORM_KI_RECHERCHE", wert)
    assert norm_ki_aktiv() is aktiv


def test_switch_off_calls_nothing(monkeypatch):
    monkeypatch.setenv("NORM_KI_RECHERCHE", "off")
    monkeypatch.setattr(normen_ki, "recherchiere_normen", nicht_aufrufen)
    assert recherchiere_normen_sicher(LV_N5, client=nicht_aufrufen) == []


@pytest.mark.parametrize("env", [{}, {"LLM_PROVIDER": "mock"}, {"LLM_PROVIDER": "anthropic"},
                                 {"LLM_PROVIDER": "unknown", "ANTHROPIC_API_KEY": "synthetic"}])
def test_mock_offline_or_missing_key_makes_no_call(monkeypatch, env):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(llm, "complete", nicht_aufrufen)
    monkeypatch.setattr(llm, "research", nicht_aufrufen)
    assert recherchiere_normen_sicher(LV_N5) == []


def bericht(client: TestClient, lv: LV) -> bytes:
    response = client.post("/api/lv/pruefen", json=lv.model_dump(mode="json"))
    assert response.status_code == 200
    return response.content


def test_pruefbericht_is_identical_with_switch_off_and_in_mock_mode(monkeypatch):
    client = TestClient(main.app)
    monkeypatch.setattr(llm, "complete", nicht_aufrufen)
    monkeypatch.setattr(llm, "research", nicht_aufrufen)
    with monkeypatch.context() as m:
        m.setattr(normen_ki, "recherchiere_normen_sicher", lambda lv: [])
        heute = bericht(client, LV_N5)  # report as before N5
    standard_mock = bericht(client, LV_N5)
    monkeypatch.setenv("NORM_KI_RECHERCHE", "off")
    aus = bericht(client, LV_N5)
    # #147: the item review now uses a configured provider; pin it to the mock so only N5 is compared.
    monkeypatch.setattr(main, "pruefe_mit_llm_status", llm_pruefung.mock_pruefung)
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic-not-a-key")
    aus_mit_provider = bericht(client, LV_N5)
    assert heute == standard_mock == aus == aus_mit_provider


def test_live_provider_appends_hints_after_n2_n3_findings(monkeypatch):
    client = TestClient(main.app)
    heute = json.loads(bericht(client, LV_N5))["findings"]
    monkeypatch.setattr(main, "pruefe_mit_llm_status", llm_pruefung.mock_pruefung)  # #147: N5 only
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic-not-a-key")
    monkeypatch.setattr(llm, "research", fake(antwort(UNBEKANNT_VORSCHLAG, DIN_4109)))
    an = json.loads(bericht(client, LV_N5))["findings"]
    assert an[:len(heute)] == heute
    assert [(f["regel_id"], f["oz"]) for f in an[len(heute):]] == [
        (NORM_KI_HINWEIS, "01.02"), (NORM_KI_HINWEIS, "01.03")]


# --- Acceptance 3: wording ---------------------------------------------------------------------

def test_wording_never_claims_a_breach_and_always_carries_the_note():
    gefaehrlich = {**UNBEKANNT_VORSCHLAG, "titel": "Violation of the standard",
                   "begruendung": "This is a clear Verstoß and non-compliant."}
    findings = recherchiere_normen(LV_N5, client=fake(antwort(DIN_4109, gefaehrlich)))
    assert len(findings) == 2
    for f in findings:
        for text in (f.titel, f.begruendung, f.vorschlag):
            assert not CLAIM_WORDS.search(text)
        assert KEIN_NORMGUTACHTEN in f.begruendung
        assert "not a standards expert opinion" in f.begruendung and "kein Normgutachten" in f.begruendung
        assert "Source: model" in f.begruendung


def test_long_model_text_is_shortened():
    lang = {**UNBEKANNT_VORSCHLAG, "begruendung": "word " * 200}
    [f] = recherchiere_normen(LV_N5, client=fake(antwort(lang)))
    assert len(f.begruendung) < 1200 and "…" in f.begruendung


def test_other_rule_sets_are_kept_as_written_and_unconfirmed():
    roh = antwort({**UNBEKANNT_VORSCHLAG, "norm_id": "DGUV Regel 99901", "oz": ["01.01"]})
    [vorschlag] = vorschlaege_aus_antwort(roh, LV_N5, set())
    assert (vorschlag["norm_id"], vorschlag["oz"]) == ("DGUV Regel 99901", ["01.01"])


# --- #166: real research with web search: sources, rounds, deadline, cache, background ---------

def recherche(text: str, citations=(), sources=(), aufrufe: list | None = None):
    """Fake `llm.research` client answering with web evidence (synthetic URLs only)."""
    def client(prompt, system="", max_tokens=1024, **_):
        if aufrufe is not None:
            aufrufe.append(prompt)
        return llm.ResearchAnswer(text, "anthropic", "fake-model", 1, list(citations), list(sources), 2, True)
    return client


ZITAT = llm.Citation("https://example.org/din-4109", "DIN 4109 Schallschutz im Hochbau",
                     "DIN 4109-1 legt Mindestanforderungen an den Schallschutz fest.")
NICHT_GEFUNDEN = "https://example.org/never-retrieved"


def test_hint_names_web_sources_with_url_designation_and_quote():
    vorschlag = {**DIN_4109, "quellen": [{"url": ZITAT.url}, {"url": NICHT_GEFUNDEN}]}
    [f] = recherchiere_normen(LV_N5, client=recherche(antwort(vorschlag), [ZITAT]))
    assert "Web sources" in f.begruendung and ZITAT.url in f.begruendung and "DIN 4109" in f.begruendung
    assert ZITAT.cited_text in f.begruendung
    assert NICHT_GEFUNDEN not in f.begruendung  # named by the model, never returned by the search
    assert "web search: 2 searches" in f.begruendung and KEIN_NORMGUTACHTEN in f.begruendung


def test_search_hit_naming_the_designation_counts_as_a_source():
    treffer = llm.Citation("https://example.org/din-99901", f"{UNBEKANNT} overview")
    [f] = recherchiere_normen(LV_N5, client=recherche(antwort(UNBEKANNT_VORSCHLAG), sources=[treffer, ZITAT]))
    assert treffer.url in f.begruendung and ZITAT.url not in f.begruendung and UNBESTAETIGT in f.titel


def test_plain_answer_without_web_evidence_shows_no_web_sources():
    vorschlag = {**DIN_4109, "quellen": [{"url": ZITAT.url}]}
    [f] = recherchiere_normen(LV_N5, client=fake(antwort(vorschlag)))
    assert "Web sources" not in f.begruendung and ZITAT.url not in f.begruendung


def test_oz_of_another_round_is_dropped():
    """Each round only sees its trade; an OZ the round never saw is not accepted from it."""
    aufrufe = []
    def client(prompt, system="", max_tokens=1024):
        aufrufe.append(prompt)
        erdarbeiten = json.loads(prompt)["positionen"][0]["oz"] == "01.01"
        return llm.Answer(antwort(DIN_4109) if erdarbeiten else antwort(), "fake", "fake-model", 1)
    assert recherchiere_normen(LV_N5, client=client) == [] and len(aufrufe) == 2


def test_rounds_follow_trades_and_are_capped():
    positionen = [Position(oz=f"{g:02d}.{i:02d}", kurztext="Arbeit", langtext="", menge=1, einheit="St",
                           titel_pfad=[f"Gewerk {g}"]) for g in range(1, 11) for i in range(1, 4)]
    lv = LV(name="Synthetic rounds", quelle="test", positionen=positionen)
    runden = normen_ki._runden(lv, 4)
    assert len(runden) <= 4 and [p.oz for r in runden for p in r] == [p.oz for p in positionen]
    assert [len(r) for r in normen_ki._runden(LV_N5, 6)] == [1, 2]


def test_failed_round_is_logged_and_the_other_rounds_still_count(caplog):
    def client(prompt, system="", max_tokens=1024):
        if json.loads(prompt)["positionen"][0]["oz"] == "01.01":
            raise llm.LLMError("synthetic round failure")
        return llm.Answer(antwort(DIN_4109), "fake", "fake-model", 1)
    with caplog.at_level(logging.WARNING, logger=normen_ki.__name__):
        [f] = recherchiere_normen(LV_N5, client=client)
    assert f.oz == "01.02" and "1 of 2 research rounds" in f.begruendung
    assert "round 1 of 2 failed" in caplog.text and "synthetic round failure" in caplog.text


def live(monkeypatch, client):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic-not-a-key")
    monkeypatch.setattr(llm, "research", client)


def test_default_client_passes_search_budget_and_remaining_time(monkeypatch):
    erhalten = []
    def research(prompt, system="", max_tokens=1024, *, max_searches=5, timeout=None, effort=None):
        erhalten.append((max_searches, timeout, max_tokens))
        return llm.ResearchAnswer(antwort(), "anthropic", "fake-model", 1)
    live(monkeypatch, research)
    monkeypatch.setenv("NORM_KI_MAX_SEARCHES", "7")
    monkeypatch.setenv("NORM_KI_TIMEOUT", "90")
    assert recherchiere_normen_sicher(LV_N5) == []
    assert len(erhalten) == 2
    for suchen, timeout, tokens in erhalten:
        assert suchen == 7 and 0 < timeout <= 90 and tokens == normen_ki.MAX_TOKENS


def test_result_is_cached_per_lv_hash(monkeypatch):
    aufrufe = []
    live(monkeypatch, recherche(antwort(DIN_4109), [ZITAT], aufrufe=aufrufe))
    erst = recherchiere_normen_sicher(LV_N5)
    assert [f.regel_id for f in erst] == [NORM_KI_HINWEIS] and len(aufrufe) == 2
    assert recherchiere_normen_sicher(LV_N5) == erst and len(aufrufe) == 2  # cache hit: no new call
    anders = LV_N5.model_copy(update={"name": "Another synthetic LV"})
    recherchiere_normen_sicher(anders)
    assert len(aufrufe) == 4


def test_partial_result_is_not_cached(monkeypatch):
    aufrufe = []
    def client(prompt, system="", max_tokens=1024, **_):
        aufrufe.append(prompt)
        if json.loads(prompt)["positionen"][0]["oz"] == "01.01":
            raise llm.LLMError("synthetic round failure")
        return llm.ResearchAnswer(antwort(DIN_4109), "anthropic", "fake-model", 1)
    live(monkeypatch, client)
    assert len(recherchiere_normen_sicher(LV_N5)) == 1
    assert len(recherchiere_normen_sicher(LV_N5)) == 1 and len(aufrufe) == 4


def test_background_start_is_picked_up_without_a_second_call(monkeypatch):
    freigabe, aufrufe = threading.Event(), []
    def client(prompt, system="", max_tokens=1024, **_):
        aufrufe.append(prompt)
        freigabe.wait(5)
        return llm.ResearchAnswer(antwort(DIN_4109), "anthropic", "fake-model", 1)
    live(monkeypatch, client)
    normen_ki.starte_recherche(LV_N5)
    normen_ki.starte_recherche(LV_N5)  # same LV, already running: no second research
    freigabe.set()
    assert [f.oz for f in recherchiere_normen_sicher(LV_N5)] == ["01.02"]
    assert len(aufrufe) == 2


@pytest.mark.parametrize("env", [{}, {"NORM_KI_RECHERCHE": "off"}, {"NORMPRUEFUNG": "off"}])
def test_background_start_does_nothing_without_key_or_when_switched_off(monkeypatch, env):
    monkeypatch.setattr(llm, "research", nicht_aufrufen)
    if env:
        live(monkeypatch, nicht_aufrufen)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    normen_ki.starte_recherche(LV_N5)
    assert normen_ki._LAUFEND == {}


# --- #166 + F #165: every research round reports into the job progress ----------------------

def test_each_round_reports_its_trade_and_the_rounds_done():
    meldungen, sperre = [], threading.Lock()
    def melde(meldung, anteil=None):
        with sperre:
            meldungen.append((meldung, anteil))
    recherchiere_normen(LV_N5, client=fake(antwort(DIN_4109)), melde=melde)
    texte = [m for m, _ in meldungen]
    assert any(t.startswith("Researching standards for Erdarbeiten") and "(round 1 of 2)" in t for t in texte)
    assert any(t.startswith("Researching standards for Rohbau") and "(round 2 of 2)" in t for t in texte)
    assert meldungen[-1] == ("Standards research: 2 of 2 rounds done.", 1.0)


def test_a_failing_progress_callback_never_stops_the_research():
    def kaputt_melden(*_):
        raise RuntimeError("synthetic progress failure")
    assert len(recherchiere_normen(LV_N5, client=fake(antwort(DIN_4109)), melde=kaputt_melden)) == 1


def test_waiting_job_follows_the_background_rounds_and_a_cache_hit_says_so(monkeypatch):
    freigabe = threading.Event()
    def client(prompt, system="", max_tokens=1024, **_):
        freigabe.wait(5)
        return llm.ResearchAnswer(antwort(DIN_4109), "anthropic", "fake-model", 1)
    live(monkeypatch, client)
    normen_ki.starte_recherche(LV_N5)
    meldungen = []
    warten = threading.Thread(target=lambda: meldungen.append(recherchiere_normen_sicher(
        LV_N5, melde=lambda m, a=None: meldungen.append(m))))
    warten.start()
    for _ in range(200):
        if normen_ki._ZUHOERER:
            break
        time.sleep(0.01)
    freigabe.set()
    warten.join(5)
    assert any(isinstance(m, str) and m.startswith("Researching standards for") for m in meldungen)
    assert "Standards research: 2 of 2 rounds done." in meldungen and normen_ki._ZUHOERER == {}
    nochmal = []
    recherchiere_normen_sicher(LV_N5, melde=lambda m, a=None: nochmal.append((m, a)))
    assert nochmal == [("Standards research: result ready (researched in the background or cached for this BoQ).", 1.0)]


def test_job_status_shows_the_research_rounds_under_the_standards_step(monkeypatch):
    from app.fortschritt import Aufzeichnung
    monkeypatch.setattr(main, "pruefe_mit_llm_status", llm_pruefung.mock_pruefung)
    live(monkeypatch, recherche(antwort(DIN_4109), [ZITAT]))
    aufzeichnung = Aufzeichnung()
    main._pruefbericht(LV_N5, fortschritt=aufzeichnung)
    recherche_meldungen = [schritt for schritt, _, meldung, _ in aufzeichnung.meldungen
                           if meldung.startswith(("Researching standards", "Standards research:"))]
    assert recherche_meldungen and set(recherche_meldungen) == {5}

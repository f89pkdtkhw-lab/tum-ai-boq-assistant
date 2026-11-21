"""Norm check N5 (issue #87): AI research for missed standards, with a mocked model only.

Synthetic fixtures only; no dataset text. Offline: every model call goes to an injected fake,
and httpx is blocked so an accidental real call fails loudly.
"""
import json
import logging
import re
import threading

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
    for key in LLM_KEYS + ("NORM_KI_RECHERCHE", "NORM_KI_TIMEOUT", "NORMPRUEFUNG"):
        monkeypatch.delenv(key, raising=False)

    def kein_netz(*_, **__):
        raise AssertionError("no real model call in tests")
    monkeypatch.setattr(httpx, "post", kein_netz)


def antwort(*vorschlaege: dict) -> str:
    return json.dumps({"vorschlaege": list(vorschlaege)})


def fake(text: str, aufrufe: list | None = None):
    def client(prompt, system="", max_tokens=1024):
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


def test_model_receives_positions_and_the_n1_list():
    aufrufe = []
    recherchiere_normen(LV_N5, client=fake(antwort(), aufrufe))
    [aufruf] = aufrufe
    eingabe = json.loads(aufruf["prompt"])
    assert eingabe["bereits_gefunden"] == ["ATV DIN 18300", "DIN 1045-2"]
    assert [p["oz"] for p in eingabe["positionen"]] == ["01.01", "01.02", "01.03"]
    assert eingabe["positionen"][1]["abschnitt"] == "Rohbau"
    assert "ADDITIONAL" in aufruf["system"] and "JSON" in aufruf["system"]


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
    assert recherchiere_normen_sicher(LV_N5) == []


def bericht(client: TestClient, lv: LV) -> bytes:
    response = client.post("/api/lv/pruefen", json=lv.model_dump(mode="json"))
    assert response.status_code == 200
    return response.content


def test_pruefbericht_is_identical_with_switch_off_and_in_mock_mode(monkeypatch):
    client = TestClient(main.app)
    monkeypatch.setattr(llm, "complete", nicht_aufrufen)
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
    monkeypatch.setattr(llm, "complete", fake(antwort(UNBEKANNT_VORSCHLAG, DIN_4109)))
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

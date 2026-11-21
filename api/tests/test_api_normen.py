"""Norm check N2 (issue #81) through /api/lv/pruefen: switch off = unchanged report, on = appended findings.

Synthetic fixtures only; offline, model mock, no key required.
"""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main
from app.modelle import LV, Kennzahlen, Position, Pruefbericht
from app.pruefung import normen

ROOT = Path(__file__).resolve().parents[2]
LLM_KEYS = ("LLM_PROVIDER", "LLM_MODEL", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "AZURE_OPENAI_API_KEY",
            "GEMINI_API_KEY", "OPENAI_BASE_URL", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT")

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in LLM_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("NORMPRUEFUNG", raising=False)


def beispiel() -> dict:
    return json.loads((ROOT / "data" / "beispiel_lv.json").read_text(encoding="utf-8"))


def beispiel_mit_normen() -> dict:
    """The synthetic example plus synthetic items that cite standards."""
    lv = beispiel()
    lv["positionen"] += [
        Position(oz="99.01", kurztext="Rammsondierung", langtext="Sondierung gemäß DIN 4094 Teil 3.",
                 menge=3, einheit="St", ep=100, gp=300).model_dump(),
        Position(oz="99.02", kurztext="Bodenaushub", langtext="ATV DIN 18300 (2012-09), Bodenklasse 3–5.",
                 menge=10, einheit="m3", ep=20, gp=200).model_dump(),
        Position(oz="99.03", kurztext="Sonstiges", langtext="Ausführung nach DIN.",
                 menge=1, einheit="psch", ep=50, gp=50).model_dump(),
        Position(oz="99.04", kurztext="Beton XC4, C20/25", langtext="Stahlbeton liefern und einbauen.",
                 menge=120, einheit="m3", ep=150, gp=18000).model_dump(),
    ]
    return lv


def bericht_vor_n2(lv_json: dict) -> dict:
    """The report exactly as `pruefen()` built it before the N2 hook existed."""
    lv = LV.model_validate(lv_json)
    findings = main.bewerte(lv, main.pruefe_regeln(lv) + main.pruefe_mengen(lv) + main.pruefe_mit_llm(lv))
    return main.ergaenze_berichte(Pruefbericht(lv=lv, findings=findings, kennzahlen=Kennzahlen(
        positionen=len(lv.positionen), findings=len(findings),
        kritisch=sum(f.schwere == "kritisch" for f in findings), modell_mock=True,
    ), zusammenfassung=main.zusammenfassen(findings))).model_dump(mode="json")


def ohne_hook(monkeypatch, lv_json: dict) -> bytes:
    with monkeypatch.context() as m:
        m.setattr(main, "pruefe_normen_sicher", lambda lv: [])
        antwort = client.post("/api/lv/pruefen", json=lv_json)
    assert antwort.status_code == 200
    return antwort.content


@pytest.mark.parametrize("lv_json", [beispiel(), beispiel_mit_normen()], ids=["beispiel", "mit_normen"])
@pytest.mark.parametrize("aus", ["0", "off", "false", "no"])
def test_switch_off_returns_the_report_from_before_this_change(monkeypatch, lv_json, aus):
    golden = ohne_hook(monkeypatch, lv_json)
    monkeypatch.setenv("NORMPRUEFUNG", aus)
    antwort = client.post("/api/lv/pruefen", json=lv_json)
    assert antwort.status_code == 200
    assert antwort.content == golden
    assert antwort.json() == bericht_vor_n2(lv_json)
    assert [b["id"] for b in antwort.json()["berichte"]] == ["regelwerk", "vergleich", "was_wenn"]  # B5 additive


def test_switch_on_appends_norm_findings_after_the_unchanged_original_findings(monkeypatch):
    lv_json = beispiel_mit_normen()
    original = json.loads(ohne_hook(monkeypatch, lv_json))["findings"]
    body = client.post("/api/lv/pruefen", json=lv_json).json()
    findings = body["findings"]
    assert original and findings[:len(original)] == original
    angehaengt = findings[len(original):]
    assert [f["regel_id"] for f in angehaengt] == [
        "NORM_ZURUECKGEZOGEN", "NORM_AUSGABE_VERALTET", "NORM_BODENKLASSEN", "NORM_OHNE_REFERENZ",
        "NORM_KENNWERT_ABWEICHUNG",
    ]
    assert all(f["euro_wirkung"] is None and f["quelle"] == "regel" for f in angehaengt)
    assert body["kennzahlen"]["findings"] == len(findings)
    assert body["kennzahlen"]["kritisch"] == sum(f["schwere"] == "kritisch" for f in findings)
    assert len({f["id"] for f in findings}) == len(findings)


def test_switch_on_without_norms_leaves_the_example_unchanged(monkeypatch):
    golden = ohne_hook(monkeypatch, beispiel())
    assert client.post("/api/lv/pruefen", json=beispiel()).content == golden


def test_failing_norm_check_still_returns_the_original_report(monkeypatch, caplog):
    lv_json = beispiel_mit_normen()
    golden = ohne_hook(monkeypatch, lv_json)

    def kaputt(lv):
        raise RuntimeError("norm check exploded")

    monkeypatch.setattr(normen, "pruefe_normen", kaputt)
    with caplog.at_level("ERROR", logger=normen.__name__):
        antwort = client.post("/api/lv/pruefen", json=lv_json)
    assert antwort.status_code == 200
    assert antwort.content == golden
    assert "Norm check failed" in caplog.text and "norm check exploded" in caplog.text


def test_broken_register_file_still_returns_the_original_report(monkeypatch, tmp_path, caplog):
    kaputtes_register = tmp_path / "register.json"
    kaputtes_register.write_text("{not json", encoding="utf-8")
    lv_json = beispiel_mit_normen()
    golden = ohne_hook(monkeypatch, lv_json)
    monkeypatch.setattr(normen, "REGISTER_PFAD", kaputtes_register)
    with caplog.at_level("ERROR", logger=normen.__name__):
        antwort = client.post("/api/lv/pruefen", json=lv_json)
    assert antwort.status_code == 200 and antwort.content == golden
    assert "Norm check failed" in caplog.text

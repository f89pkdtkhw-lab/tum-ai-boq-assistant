"""Norm check N1 (issue #80): standard references, curated register, norm list.

Synthetic fixtures only; no dataset text. Offline, no model calls.
"""
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main
from app.modelle import LV, Finding, Position
from app.pruefung import normen
from app.pruefung.normen import (
    NICHT_IM_REGISTER, REGISTER_PFAD, NormVerweis, extrahiere_normverweise, lade_register, normenliste,
    normpruefung_aktiv,
)

ROOT = Path(__file__).resolve().parents[2]
LLM_KEYS = ("LLM_PROVIDER", "LLM_MODEL", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "AZURE_OPENAI_API_KEY",
            "GEMINI_API_KEY", "OPENAI_BASE_URL", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT")
CLAIM_WORDS = re.compile(r"violat|breach|verstoß|verstoss|non-?complian", re.IGNORECASE)


def lv_mit(*texte: tuple[str, str]) -> LV:
    return LV(name="Synthetic norm LV", quelle="test", positionen=[
        Position(oz=f"01.{i:02d}", kurztext=kurz, langtext=lang, menge=1, einheit="St")
        for i, (kurz, lang) in enumerate(texte, start=1)
    ])


ABNAHME_LV = lv_mit(
    ("Bodenaushub nach ATV DIN 18300 (2012-09)", "Boden lösen und laden."),
    ("Rammsondierung", "Sondierung gemäß DIN 4094 bis 6 m Tiefe."),
    ("Flansch", "Flansch DIN EN1092-1 PN 16."),
    ("Beton", "Beton nach DIN 1045 Teil 2 liefern."),
    ("Abdichtung", "Ausführung nach DIN, Pläne im Format DIN A4."),
)


def kern(v: NormVerweis) -> tuple:
    return (v.norm_id, v.familie, v.teil, v.ausgabe, v.oz, v.feld, v.pauschal)


def test_acceptance_fixture_yields_exactly_the_normalised_references():
    verweise = extrahiere_normverweise(ABNAHME_LV)
    assert [kern(v) for v in verweise] == [
        ("ATV DIN 18300", "ATV DIN 18300", None, "2012-09", "01.01", "kurztext", False),
        ("DIN 4094", "DIN 4094", None, None, "01.02", "langtext", False),
        ("DIN EN 1092-1", "DIN EN 1092", "-1", None, "01.03", "langtext", False),
        ("DIN 1045-2", "DIN 1045", "-2", None, "01.04", "langtext", False),
        (None, None, None, None, "01.05", "langtext", True),
    ]
    assert [v.roh for v in verweise] == [
        "ATV DIN 18300 (2012-09)", "DIN 4094", "DIN EN1092-1", "DIN 1045 Teil 2", "nach DIN",
    ]
    assert not any("A4" in v.roh for v in verweise)


@pytest.mark.parametrize("text, erwartet", [
    ("DIN 18300:2012-09", ("ATV DIN 18300", None, "2012-09")),
    ("DIN 18 300 Ausgabe 2016-09", ("ATV DIN 18300", None, "2016-09")),
    ("DIN VDE 0675-6:1989-11", ("DIN VDE 0675-6", "-6", "1989-11")),
    ("VDE 0100-410", ("DIN VDE 0100-410", "-410", None)),
    ("DIN EN ISO 22476-2:2012-03", ("DIN EN ISO 22476-2", "-2", "2012-03")),
    ("DIN ISO 10381", ("DIN ISO 10381", None, None)),
    ("DIN SPEC 91411", ("DIN SPEC 91411", None, None)),
    ("DIN-EN 1991-1-4/NA:2024-08", ("DIN EN 1991-1-4/NA", "-1-4", "2024-08")),
    ("DIN V 4108-6", ("DIN V 4108-6", "-6", None)),
    ("DIN 4094 Teil 3", ("DIN 4094-3", "-3", None)),
    ("DIN 1053-1 (1996)", ("DIN 1053-1", "-1", "1996")),
])
def test_spelling_variants_are_normalised(text, erwartet):
    [verweis] = extrahiere_normverweise(lv_mit(("Pos", text)))
    assert (verweis.norm_id, verweis.teil, verweis.ausgabe) == erwartet


@pytest.mark.parametrize("text", [
    "Papier DIN A4", "DIN A3 Plan", "DIN 18 Stück", "Normalbeton C25/30", "Schraube M12", "DINGE 12345",
])
def test_false_positives_are_ignored(text):
    assert extrahiere_normverweise(lv_mit(("Pos", text))) == []


@pytest.mark.parametrize("text", [
    "Ausführung nach einschlägigen Normen", "gemäß den gültigen DIN-Normen", "nach DIN und VOB",
    "nach den einschlägigen DIN-Vorschriften", "entsprechend der gültigen DIN",
])
def test_blanket_references_are_collected_as_pauschal(text):
    [verweis] = extrahiere_normverweise(lv_mit(("Pos", text)))
    assert verweis.pauschal and verweis.norm_id is None


def test_numbered_reference_after_nach_is_not_blanket_and_vde_alias_counts_once():
    verweise = extrahiere_normverweise(lv_mit(("Pos", "nach DIN EN IEC 61643-11 (VDE 0675-6-11), nach DIN 18196")))
    assert [(v.norm_id, v.pauschal) for v in verweise] == [("DIN EN IEC 61643-11", False), ("DIN 18196", False)]
    [verweis] = extrahiere_normverweise(lv_mit(("Pos", "nach der gültigen DIN 18196")))
    assert (verweis.norm_id, verweis.pauschal) == ("DIN 18196", False)


def test_register_file_loads_and_is_valid():
    register = lade_register()
    assert REGISTER_PFAD == ROOT / "data" / "normen" / "register.json"
    assert register.stand and len(register.eintraege) >= 20
    for eintrag in register.eintraege:
        assert eintrag.quelle["url"].startswith("https://") and eintrag.quelle["abgerufen"]
        assert eintrag.geprueft is False  # only a person sets true
        assert not CLAIM_WORDS.search(eintrag.hinweis + eintrag.titel + " ".join(eintrag.kennwerte))
    status = {e.norm_id: e.status for e in register.eintraege}
    assert status["ATV DIN 18300"] == "gueltig"
    assert status["DIN 4094-3"] == status["DIN 1055-4"] == status["DIN VDE 0675-6"] == "zurueckgezogen"
    assert status["DIN 18195"] == "teilweise_ersetzt"
    assert status["DIN 4020"] == status["DIN EN 206"] == "unklar"


def test_register_lookup_exact_then_by_family():
    register = lade_register()
    assert register.suche("DIN 4094-3", "DIN 4094").ersetzt_durch == ["DIN EN ISO 22476-2"]
    assert register.suche("DIN 1055-5", "DIN 1055").norm_id == "DIN 1055"
    assert register.suche("DIN EN 1092-1", "DIN EN 1092") is None


def schreibe_register(tmp_path, **aenderung) -> Path:
    daten = json.loads(REGISTER_PFAD.read_text(encoding="utf-8"))
    daten["eintraege"] = [{**daten["eintraege"][0], **aenderung}]
    pfad = tmp_path / "register.json"
    pfad.write_text(json.dumps(daten), encoding="utf-8")
    return pfad


def test_register_rejects_unknown_status(tmp_path):
    with pytest.raises(ValueError, match="unknown status"):
        lade_register(schreibe_register(tmp_path, status="verboten"))


@pytest.mark.parametrize("quelle", [{"abgerufen": "2026-11-21"}, {"url": "", "abgerufen": "2026-11-21"},
                                    {"url": "https://example.org"}])
def test_register_requires_source_url_and_retrieval_date(tmp_path, quelle):
    with pytest.raises(ValueError, match="quelle"):
        lade_register(schreibe_register(tmp_path, quelle=quelle))


def test_register_rejects_designations_our_normaliser_would_not_produce(tmp_path):
    with pytest.raises(ValueError, match="must be written as"):
        lade_register(schreibe_register(tmp_path, norm_id="DIN 18300", familie="DIN 18300"))


def test_normenliste_reports_status_and_unknown_norms_without_findings():
    liste = normenliste(ABNAHME_LV, lade_register())
    assert liste == [
        {"norm_id": "ATV DIN 18300", "status": "gueltig", "ersetzt_durch": [], "anzahl": 1, "oz": ["01.01"]},
        {"norm_id": "DIN 4094", "status": "unklar", "ersetzt_durch": [], "anzahl": 1, "oz": ["01.02"]},
        {"norm_id": "DIN EN 1092-1", "status": NICHT_IM_REGISTER, "ersetzt_durch": [], "anzahl": 1, "oz": ["01.03"]},
        {"norm_id": "DIN 1045-2", "status": "gueltig", "ersetzt_durch": [], "anzahl": 1, "oz": ["01.04"]},
    ]
    assert not any(isinstance(zeile, Finding) for zeile in liste)


def test_normenliste_counts_and_groups_positions():
    lv = lv_mit(("DIN 4094-3", "Rammsondierung DIN 4094 Teil 3"), ("Sondierung", "DIN 4094-3"), ("Dach", "DIN 1055-5"))
    assert normenliste(lv, lade_register()) == [
        {"norm_id": "DIN 4094-3", "status": "zurueckgezogen", "ersetzt_durch": ["DIN EN ISO 22476-2"], "anzahl": 3,
         "oz": ["01.01", "01.02"]},
        {"norm_id": "DIN 1055-5", "status": "unklar", "ersetzt_durch": [], "anzahl": 1, "oz": ["01.03"]},
    ]


@pytest.mark.parametrize("wert, aktiv", [
    (None, True), ("", True), ("1", True), ("on", True), ("0", False), ("off", False), ("FALSE", False),
    (" no ", False),
])
def test_normpruefung_switch(monkeypatch, wert, aktiv):
    if wert is None:
        monkeypatch.delenv("NORMPRUEFUNG", raising=False)
    else:
        monkeypatch.setenv("NORMPRUEFUNG", wert)
    assert normpruefung_aktiv() is aktiv


def test_pruefen_output_is_unchanged_by_the_switch(monkeypatch):
    """N1 wires nothing into pruefen(): the report is byte-identical with the switch off and on."""
    for key in LLM_KEYS:
        monkeypatch.delenv(key, raising=False)
    client = TestClient(main.app)
    beispiel = json.loads((ROOT / "data" / "beispiel_lv.json").read_text(encoding="utf-8"))
    monkeypatch.delenv("NORMPRUEFUNG", raising=False)
    standard = client.post("/api/lv/pruefen", json=beispiel)
    monkeypatch.setenv("NORMPRUEFUNG", "0")
    aus = client.post("/api/lv/pruefen", json=beispiel)
    assert standard.status_code == aus.status_code == 200
    assert standard.content == aus.content


def test_module_never_builds_findings():
    quelle = Path(normen.__file__).read_text(encoding="utf-8")
    assert "Finding(" not in quelle

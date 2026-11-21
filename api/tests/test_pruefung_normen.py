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


# --- Norm check N3 (issue #82): key values, assumption or bidder question ---------------------

import dataclasses
import logging
from datetime import date

from app.ai.step_api import SourceRecord, SourceScope, Requirement, UnitPrice, build_specification_context, standards_note
from app.pruefung.normen import (
    ANNAHME_PRAEFIX, KEIN_NORMGUTACHTEN, NORM_KENNWERT_ABWEICHUNG, annahme_note, entscheide, pruefe_kennwerte,
    pruefe_kennwerte_sicher, register_als_quellen,
)

KENNWERT_URL = "https://heidelbergmaterials.de/sites/default/files/2024-09/flyer_beton_bestellen_nach_norm.pdf"


def register_mit(geprueft: bool, status: str = "gueltig") -> normen.Register:
    basis = lade_register()
    return normen.Register(stand=basis.stand, eintraege=[
        dataclasses.replace(e, geprueft=geprueft, status=status) if e.norm_id == "DIN 1045-2" else e
        for e in basis.eintraege
    ])


def beton_lv(kurztext: str, langtext: str = "Stahlbeton liefern und einbauen.", menge=120.0, einheit="m³",
             typ="normal") -> LV:
    return LV(name="Synthetic concrete LV", quelle="test", positionen=[
        Position(oz="02.01", kurztext=kurztext, langtext=langtext, menge=menge, einheit=einheit, typ=typ),
    ])


def test_register_holds_structured_key_values_unchecked():
    eintrag = lade_register().suche("DIN 1045-2")
    assert {k.bedingung: k.value for k in eintrag.kennwert_regeln} == {
        "XC1": "C16/20", "XC2": "C16/20", "XC3": "C20/25", "XC4": "C25/30", "XD1": "C30/37", "XF1": "C25/30",
    }
    assert eintrag.geprueft is False and all(isinstance(k, str) for k in eintrag.kennwerte)
    for k in eintrag.kennwert_regeln:
        assert k.parameter == "min_strength_class" and k.quelle["url"].startswith("https://")
        assert "2008" in k.fundstelle and "not verified" in k.fundstelle
        assert not CLAIM_WORDS.search(k.fundstelle)


@pytest.mark.parametrize("kennwert, fehler", [
    ({"parameter": "max_wz", "bedingung": "XC4", "value": "C25/30"}, "unknown parameter"),
    ({"bedingung": "C4"}, "exposure class"),
    ({"value": "25/30"}, "strength class"),
    ({"quelle": {"url": "http://example.org", "abgerufen": "2026-11-21"}}, "https"),
    ({"quelle": {"url": KENNWERT_URL}}, "abgerufen"),
    ({"extra": 1}, "unknown fields"),
])
def test_register_rejects_invalid_key_values(tmp_path, kennwert, fehler):
    gueltig = {"parameter": "min_strength_class", "bedingung": "XC4", "value": "C25/30", "fundstelle": "Tabelle",
               "quelle": {"url": KENNWERT_URL, "abgerufen": "2026-11-21"}}
    with pytest.raises(ValueError, match=fehler):
        lade_register(schreibe_register(tmp_path, kennwerte=[{**gueltig, **kennwert}]))


def test_checked_entry_gives_finding_with_bidder_question_and_assumption_note():
    lv, register = beton_lv("Beton XC4, C20/25"), register_mit(geprueft=True)
    [finding] = pruefe_kennwerte(lv, register)
    assert (finding.id, finding.regel_id, finding.kategorie, finding.schwere, finding.quelle) == (
        f"{NORM_KENNWERT_ABWEICHUNG}:02.01", NORM_KENNWERT_ABWEICHUNG, "risiko", "hoch", "regel")
    assert finding.euro_wirkung is None
    assert finding.vorschlag.startswith("Bidder question") and "C25/30" in finding.vorschlag
    assert entscheide(finding, register, lv.positionen[0]) == "annahme"
    note = annahme_note(finding, register, lv.positionen[0])
    assert note.text.startswith(f"{ANNAHME_PRAEFIX}: for 120 m³ (OZ 02.01) C25/30 instead of C20/25 is assumed (XC4).")
    assert "f_ck +5 N/mm²" in note.text and "€" not in note.text and "EUR" not in note.text
    assert (note.step, note.source, note.manual_review, note.approval_required, note.placeholder) == (
        "standards", "rule", True, True, False)
    assert note.base_value is None and note.estimated_value is None
    assert [e.reference_id for e in note.evidence] == ["NORM:DIN 1045-2:min_strength_class:XC4"]
    assert pruefe_kennwerte_sicher(lv, register) == ([finding], [note])


def test_unchecked_entry_gives_bidder_question_only():
    lv, register = beton_lv("Beton XC4, C20/25"), register_mit(geprueft=False)
    [finding] = pruefe_kennwerte(lv, register)
    assert finding.vorschlag.startswith("Bidder question") and "not yet checked by a person" in finding.begruendung
    assert entscheide(finding, register, lv.positionen[0]) == "rueckfrage"
    assert annahme_note(finding, register, lv.positionen[0]) is None
    assert pruefe_kennwerte_sicher(lv, register) == ([finding], [])
    assert pruefe_kennwerte_sicher(lv) == ([finding], [])  # repository register: geprueft false


@pytest.mark.parametrize("kurztext, langtext", [
    ("Beton XC4, C30/37", "Stahlbeton."),
    ("Beton XC4, C25/30", "Stahlbeton."),
    ("Beton C20/25", "Ohne Expositionsklasse."),
    ("Leichtbeton XC4, LC16/18", "Stahlbeton."),
    ("Beton XA1, C20/25", "Kein Kennwert im Register."),
])
def test_no_finding_without_a_deviation_or_key_value(kurztext, langtext):
    assert pruefe_kennwerte(beton_lv(kurztext, langtext), register_mit(geprueft=True)) == []


def test_strictest_exposure_class_and_long_text_count():
    lv = beton_lv("Stahlbeton Wand", "Beton C25/30, Expositionsklassen XC4, XD1, XF1.")
    [finding] = pruefe_kennwerte(lv, register_mit(geprueft=True))
    assert "at least C30/37 for XD1" in finding.begruendung


def test_unclear_or_withdrawn_register_status_never_creates_a_finding():
    for status in ("unklar", "zurueckgezogen"):
        assert pruefe_kennwerte(beton_lv("Beton XC4, C20/25"), register_mit(True, status)) == []


@pytest.mark.parametrize("aenderung", [{"menge": None}, {"menge": 0}, {"einheit": None}, {"einheit": " "},
                                       {"typ": "bedarf"}, {"typ": "pauschal"}])
def test_missing_quantity_unit_or_contractual_item_type_gives_bidder_question(aenderung):
    register = register_mit(geprueft=True)
    lv = beton_lv("Beton XC4, C20/25", **aenderung)
    [finding] = pruefe_kennwerte(lv, register)
    assert entscheide(finding, register, lv.positionen[0]) == "rueckfrage"
    assert annahme_note(finding, register, lv.positionen[0]) is None


def test_findings_of_other_rules_are_bidder_questions():
    lv, register = beton_lv("Beton XC4, C20/25"), register_mit(geprueft=True)
    [finding] = pruefe_kennwerte(lv, register)
    anders = finding.model_copy(update={"regel_id": "TEXT_WIDERSPRUCH"})
    assert entscheide(anders, register, lv.positionen[0]) == "rueckfrage"
    assert entscheide(finding.model_copy(update={"quelle": "modell"}), register, lv.positionen[0]) == "rueckfrage"


def test_euro_amount_only_with_an_estimator_approved_price_for_the_same_unit():
    lv, register = beton_lv("Beton XC4, C20/25"), register_mit(geprueft=True)
    [finding] = pruefe_kennwerte(lv, register)
    position = lv.positionen[0]
    freigegeben = UnitPrice(value=8.5, currency="EUR", per_unit="m³", source="estimator", approved=True)
    note = annahme_note(finding, register, position, freigegeben)
    assert "8.5 EUR/m³ × 120 m³ = 1020 EUR" in note.text and ANNAHME_PRAEFIX in note.text
    assert finding.euro_wirkung is None
    for preis in (freigegeben.model_copy(update={"approved": False}), freigegeben.model_copy(update={"per_unit": "t"}),
                  freigegeben.model_copy(update={"value": None})):
        assert "EUR" not in annahme_note(finding, register, position, preis).text


def test_wording_cites_source_and_hint_and_avoids_claim_words():
    lv, register = beton_lv("Beton XC4, C20/25"), register_mit(geprueft=True)
    [finding], [note] = pruefe_kennwerte_sicher(lv, register)
    for text in (finding.titel, finding.begruendung, finding.vorschlag, note.text):
        assert not CLAIM_WORDS.search(text)
    for text in (finding.begruendung, finding.vorschlag, note.text):
        assert KEIN_NORMGUTACHTEN in text and KENNWERT_URL in text and "2026-11-21" in text


def test_switch_off_runs_nothing(monkeypatch):
    def nicht_aufrufen(*_):
        raise AssertionError("norm check must not run")
    monkeypatch.setattr(normen, "pruefe_kennwerte", nicht_aufrufen)
    monkeypatch.setattr(normen, "lade_register", nicht_aufrufen)
    monkeypatch.setenv("NORMPRUEFUNG", "off")
    assert pruefe_kennwerte_sicher(beton_lv("Beton XC4, C20/25")) == ([], [])


def test_errors_are_logged_and_the_check_is_skipped(monkeypatch, caplog):
    def kaputt(*_):
        raise RuntimeError("synthetic failure")
    monkeypatch.delenv("NORMPRUEFUNG", raising=False)
    monkeypatch.setattr(normen, "pruefe_kennwerte", kaputt)
    with caplog.at_level(logging.ERROR, logger=normen.__name__):
        assert pruefe_kennwerte_sicher(beton_lv("Beton XC4, C20/25"), register_mit(True)) == ([], [])
    assert "Norm check N3" in caplog.text and "synthetic failure" in caplog.text


def test_pruefen_report_is_unchanged_with_switch_off_and_appends_n3_when_on(monkeypatch):
    """Since N2 (#81) the guarded hook in pruefen() also carries the N3 findings."""
    for key in LLM_KEYS:
        monkeypatch.delenv(key, raising=False)
    client = TestClient(main.app)
    lv = beton_lv("Beton XC4, C20/25", "Stahlbeton nach DIN 1045-2 liefern.").model_dump(mode="json")
    with monkeypatch.context() as m:
        m.setattr(main, "pruefe_normen_sicher", lambda lv: [])
        ohne_hook = client.post("/api/lv/pruefen", json=lv)
    monkeypatch.setenv("NORMPRUEFUNG", "0")
    aus = client.post("/api/lv/pruefen", json=lv)
    assert ohne_hook.status_code == aus.status_code == 200 and ohne_hook.content == aus.content
    monkeypatch.delenv("NORMPRUEFUNG")
    original, an = ohne_hook.json()["findings"], client.post("/api/lv/pruefen", json=lv).json()["findings"]
    assert an[:len(original)] == original
    assert [f["regel_id"] for f in an[len(original):]] == [NORM_KENNWERT_ABWEICHUNG]


NOTE2_LV = LV(name="Synthetic Note 2 LV", quelle="test", positionen=[
    Position(oz="03.01", kurztext="Wand Beton XC4", langtext="Beton nach DIN 1045-2, C25/30.", menge=40, einheit="m³"),
    Position(oz="03.02", kurztext="Bodenplatte XC1", langtext="Beton nach DIN 1045-2.", menge=20, einheit="m³"),
    Position(oz="03.03", kurztext="Fundament XC4", langtext="Beton C25/30.", menge=10, einheit="m³"),
])
STICHTAG = date(2026, 11, 21)


def test_register_sources_are_scoped_to_citing_oz_and_exposure_class():
    verweise = extrahiere_normverweise(NOTE2_LV)
    quellen = register_als_quellen(verweise, register_mit(True), NOTE2_LV)
    assert [(q.spec_id, q.scope.oz) for q in quellen] == [
        ("NORM:DIN 1045-2:min_strength_class:XC1", ["03.02"]),
        ("NORM:DIN 1045-2:min_strength_class:XC4", ["03.01"]),
    ]
    [xc4] = [q for q in quellen if q.spec_id.endswith("XC4")]
    assert (xc4.category, xc4.source_type, xc4.document_ref, xc4.as_of, xc4.source_url, xc4.verified) == (
        "german_standard", "internet", "DIN 1045-2", "2026-11-21", KENNWERT_URL, True)
    assert (xc4.requirement.comparator, xc4.requirement.value, xc4.requirement.unit) == ("min", 25.0, "N/mm²")
    ohne_lv = register_als_quellen(verweise, register_mit(True))
    assert len(ohne_lv) == 6 and all(q.scope.oz == ["03.01", "03.02"] for q in ohne_lv)
    assert register_als_quellen(verweise, register_mit(True, "unklar"), NOTE2_LV) == []


def test_verified_register_source_is_priority_1_and_cited_by_note_2():
    quellen = register_als_quellen(extrahiere_normverweise(NOTE2_LV), register_mit(True), NOTE2_LV)
    item = build_specification_context(NOTE2_LV, quellen, checked_on=STICHTAG).items[0]
    assert [(e.spec_id, e.priority, e.verification) for e in item.sources] == [
        ("NORM:DIN 1045-2:min_strength_class:XC4", 1, "verified")]
    note = standards_note(item)
    assert "NORM:DIN 1045-2:min_strength_class:XC4" in note.text
    assert [e.reference_id for e in note.evidence] == ["NORM:DIN 1045-2:min_strength_class:XC4"]


def test_verified_register_source_exposes_a_deviating_user_requirement_in_note_2():
    quellen = register_als_quellen(extrahiere_normverweise(NOTE2_LV), register_mit(True), NOTE2_LV)
    nutzer = SourceRecord(spec_id="U1", source_type="user", category="user_requirement",
                          document_ref="client spec", location="p. 3", as_of="2026-11-20",
                          scope=SourceScope(oz=["03.01"]), verified=True,
                          requirement=Requirement(parameter=quellen[1].requirement.parameter, comparator="eq",
                                                  value=20, unit="N/mm²"))
    item = build_specification_context(NOTE2_LV, [*quellen, nutzer], checked_on=STICHTAG).items[0]
    note = standards_note(item)
    assert note.text.startswith("Deviation for OZ 03.01") and "below the minimum of 25 N/mm²" in note.text


def test_unverified_register_source_stays_priority_4_and_manual_review():
    quellen = register_als_quellen(extrahiere_normverweise(NOTE2_LV), register_mit(False), NOTE2_LV)
    item = build_specification_context(NOTE2_LV, quellen, checked_on=STICHTAG).items[0]
    assert [(e.priority, e.verification, e.unverified_reasons) for e in item.sources] == [
        (4, "unverified", ["not_confirmed"])]
    assert standards_note(item).text.startswith("Manual review: no verified applicable German source for OZ 03.01")


# ---------------------------------------------------------------------------
# N2 (issue #81): status findings, wording and the guarded hook.
# ---------------------------------------------------------------------------
from app.pruefung.normen import HINWEIS, pruefe_normen, pruefe_normen_sicher, pruefe_status  # noqa: E402


def codes(lv: LV) -> list[tuple[str, str]]:
    return [(f.regel_id, f.oz) for f in pruefe_normen(lv)]


def test_withdrawn_part_yields_finding_with_replacement_and_source():
    # The register only assesses the parts of DIN 4094; the bare family entry is `unklar`.
    findings = pruefe_normen(lv_mit(("Rammsondierung", "Sondierung gemäß DIN 4094 Teil 3 bis 6 m.")))
    assert [(f.regel_id, f.oz, f.kategorie, f.schwere) for f in findings] == [
        ("NORM_ZURUECKGEZOGEN", "01.01", "risiko", "mittel"),
    ]
    f = findings[0]
    assert f.id == "NORM_ZURUECKGEZOGEN:01.01" and f.quelle == "regel" and f.euro_wirkung is None
    assert "DIN EN ISO 22476-2" in f.vorschlag and f.vorschlag.startswith("OZ 01.01:")
    assert f.vorschlag.endswith("Please confirm.")
    assert "https://www.dinmedia.de/en/standard/din-4094-3/" in f.begruendung and "retrieved 2026-11-21" in f.begruendung


def test_withdrawn_costing_relevant_norm_is_high(tmp_path):
    pfad = tmp_path / "register.json"
    daten = json.loads(REGISTER_PFAD.read_text(encoding="utf-8"))
    for e in daten["eintraege"]:
        if e["norm_id"] == "DIN 4094-3":
            e["kalkulationsrelevant"] = True
    pfad.write_text(json.dumps(daten), encoding="utf-8")
    findings = pruefe_normen(lv_mit(("Sondierung", "DIN 4094-3")), lade_register(pfad))
    assert [(f.regel_id, f.schwere) for f in findings] == [("NORM_ZURUECKGEZOGEN", "hoch")]


def test_bare_family_with_assessed_parts_is_unclear_not_withdrawn():
    findings = pruefe_normen(lv_mit(("Rammsondierung", "Sondierung gemäß DIN 4094."), ("Beton", "nach DIN 1045")))
    assert [(f.regel_id, f.oz, f.schwere) for f in findings] == [
        ("NORM_AUSGABE_UNKLAR", "01.01", "niedrig"), ("NORM_AUSGABE_UNKLAR", "01.02", "niedrig"),
    ]
    assert "DIN 4094-3 (withdrawn)" in findings[0].vorschlag and "DIN 1045-2 (valid)" in findings[1].vorschlag


def test_family_known_only_through_its_parts_is_unclear():
    assert codes(lv_mit(("Trinkwasser", "Leitungen nach DIN 1988 verlegen."))) == [("NORM_AUSGABE_UNKLAR", "01.01")]


def test_edition_or_part_given_is_not_unclear():
    assert codes(lv_mit(("Beton", "DIN 1045-2 (2023-08)"), ("Beton", "DIN 1045:2023"))) == []


def test_atv_18300_2012_with_bodenklassen_yields_outdated_edition_and_bodenklassen():
    lv = lv_mit(("Bodenaushub", "Boden lösen nach ATV DIN 18300 (2012-09), Bodenklasse 3–5, laden."))
    findings = pruefe_normen(lv)
    assert [(f.regel_id, f.kategorie, f.schwere) for f in findings] == [
        ("NORM_AUSGABE_VERALTET", "risiko", "mittel"), ("NORM_BODENKLASSEN", "nachtrag", "hoch"),
    ]
    veraltet, boden = findings
    assert "2012-09" in veraltet.vorschlag and "2019-09" in veraltet.vorschlag
    assert "Nachtrag potential is possible" in boden.begruendung
    assert "this does not establish an entitlement to additional payment" in boden.begruendung
    assert "Homogenbereich" in boden.vorschlag and boden.euro_wirkung is None


def test_bodenklassen_with_homogenbereich_is_quiet():
    lv = lv_mit(("Bodenaushub", "ATV DIN 18300 (2012-09), Bodenklasse 3–5, Homogenbereich B1."))
    assert codes(lv) == [("NORM_AUSGABE_VERALTET", "01.01")]


@pytest.mark.parametrize("text", ["DIN 18301 Bohrarbeiten, Bodenklasse 6", "ATV DIN 18319 Bodenklassen LBM 2"])
def test_bodenklassen_also_for_drilling_and_pipe_jacking(text):
    assert codes(lv_mit(("Arbeiten", text))) == [("NORM_BODENKLASSEN", "01.01")]


def test_bodenklassen_needs_the_atv_in_the_same_position():
    assert codes(lv_mit(("Aushub", "nach ATV DIN 18300"), ("Boden", "Bodenklasse 3"))) == []


def test_withdrawn_norm_and_replacement_in_the_same_lv():
    lv = lv_mit(("Sondierung alt", "DIN 4094-3"), ("Sondierung neu", "nach DIN EN ISO 22476-2"))
    findings = pruefe_normen(lv)
    assert [(f.regel_id, f.oz) for f in findings] == [
        ("NORM_ZURUECKGEZOGEN", "01.01"), ("NORM_DOPPELT_ALT_NEU", "01.01"),
    ]
    assert "OZ 01.02" in findings[1].begruendung and findings[1].schwere == "mittel"


def test_replacement_family_counts_as_present():
    lv = lv_mit(("Mauerwerk alt", "DIN 1053-1"), ("Mauerwerk neu", "DIN EN 1996-1-1/NA"))
    assert ("NORM_DOPPELT_ALT_NEU", "01.01") in codes(lv)


def test_unclear_and_unknown_norms_never_create_findings():
    lv = lv_mit(("Baugrund", "Untersuchung nach DIN 4020"), ("Lasten", "DIN 1055-5"), ("Sonstiges", "DIN 99999-1"))
    assert pruefe_normen(lv) == []


def test_blanket_references_are_grouped_per_section():
    lv = LV(name="Synthetic", quelle="test", positionen=[
        Position(oz="01.01", kurztext="A", langtext="Ausführung nach DIN.", titel_pfad=["Erdarbeiten"]),
        Position(oz="01.02", kurztext="B", langtext="gemäß einschlägigen Normen", titel_pfad=["Erdarbeiten"]),
        Position(oz="01.03", kurztext="C", langtext="nach DIN", titel_pfad=["Erdarbeiten"]),
        Position(oz="02.01", kurztext="D", langtext="lt. DIN", titel_pfad=["Beton"]),
    ])
    findings = pruefe_normen(lv)
    assert [(f.regel_id, f.oz, f.schwere) for f in findings] == [
        ("NORM_OHNE_REFERENZ", "01.01", "niedrig"), ("NORM_OHNE_REFERENZ", "02.01", "niedrig"),
    ]
    assert "01.01, 01.02, 01.03" in findings[0].vorschlag and "(3 items)" in findings[0].titel


def test_ids_are_unique_and_indexed_per_code_and_oz():
    findings = pruefe_normen(lv_mit(("Zwei alte Normen", "DIN 4094-1 und DIN 4094-2, nochmals DIN 4094-1")))
    assert [f.id for f in findings] == ["NORM_ZURUECKGEZOGEN:01.01", "NORM_ZURUECKGEZOGEN:01.01:2"]


def test_pruefe_status_without_lv_skips_bodenklassen():
    lv = lv_mit(("Aushub", "ATV DIN 18300 (2012-09), Bodenklasse 3"), ("X", "nach DIN"))
    findings = pruefe_status(extrahiere_normverweise(lv), lade_register())
    assert [(f.regel_id, f.oz) for f in findings] == [("NORM_AUSGABE_VERALTET", "01.01"), ("NORM_OHNE_REFERENZ", "01.02")]


ALLE_LV = lv_mit(
    ("Rammsondierung", "Sondierung gemäß DIN 4094 Teil 3."),
    ("Aushub", "ATV DIN 18300 (2012-09), Bodenklasse 3–5"),
    ("Sondierung", "DIN EN ISO 22476-2"),
    ("Beton", "Beton nach DIN 1045"),
    ("Sonstiges", "nach DIN"),
    ("Mauerwerk", "DIN 1053-1"),
    ("Abdichtung", "DIN 18195 (2000-08)"),
)


def test_every_code_is_covered_and_wording_rules_hold():
    findings = pruefe_normen(ALLE_LV)
    assert {f.regel_id for f in findings} == {
        "NORM_ZURUECKGEZOGEN", "NORM_AUSGABE_VERALTET", "NORM_BODENKLASSEN", "NORM_DOPPELT_ALT_NEU",
        "NORM_AUSGABE_UNKLAR", "NORM_OHNE_REFERENZ",
    }
    assert len({f.id for f in findings}) == len(findings)
    for f in findings:
        text = " ".join((f.titel, f.begruendung, f.vorschlag))
        assert not CLAIM_WORDS.search(text), f.id
        assert "not a standards expert opinion" in f.begruendung and f.begruendung.endswith(HINWEIS)
        assert "Source:" in f.begruendung and f.quelle == "regel" and f.euro_wirkung is None
        assert f.vorschlag.startswith(f"OZ {f.oz}") and f.vorschlag.rstrip().endswith((".", "?"))
        if f.regel_id != "NORM_OHNE_REFERENZ":
            assert re.search(r"https?://\S+ \(retrieved \d{4}-\d{2}-\d{2}\)", f.begruendung), f.id


def test_register_texts_contain_no_claim_words():
    for e in lade_register().eintraege:
        assert not CLAIM_WORDS.search(" ".join([e.hinweis, *e.kennwerte])), e.norm_id


def test_sicher_respects_the_switch_and_swallows_errors(monkeypatch, caplog):
    monkeypatch.setenv("NORMPRUEFUNG", "off")
    assert pruefe_normen_sicher(ALLE_LV) == []
    monkeypatch.delenv("NORMPRUEFUNG")
    assert pruefe_normen_sicher(ALLE_LV) == pruefe_normen(ALLE_LV)

    def kaputt(lv):
        raise RuntimeError("register broken")

    monkeypatch.setattr(normen, "pruefe_normen", kaputt)
    with caplog.at_level("ERROR", logger=normen.__name__):
        assert pruefe_normen_sicher(ALLE_LV) == []
    assert "Norm check failed" in caplog.text and "register broken" in caplog.text


def test_pruefe_normen_also_carries_n3_key_value_findings():
    lv = beton_lv("Beton XC4, C20/25", "Stahlbeton nach DIN 1045-2 (2008-08) liefern.")
    assert [(f.regel_id, f.oz) for f in pruefe_normen(lv)] == [
        ("NORM_AUSGABE_VERALTET", "02.01"), (NORM_KENNWERT_ABWEICHUNG, "02.01"),
    ]
    assert [f for f in pruefe_normen(lv) if f.regel_id == NORM_KENNWERT_ABWEICHUNG] == pruefe_kennwerte(
        lv, lade_register())

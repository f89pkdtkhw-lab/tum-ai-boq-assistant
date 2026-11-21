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
        m.setattr(main, "ergaenze_note2", lambda bericht: bericht)  # #167: Note 2 has its own test
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


def test_note_2_from_the_register_is_added_to_report_1_in_the_analysis_path(monkeypatch):
    """#167: `register_als_quellen` -> Note 2 in Report 1; findings stay unchanged; switch off = unchanged."""
    from app.modelle import Kennzahlen, Pruefbericht
    from app.pruefung.berichte import ergaenze_berichte
    from app.pruefung.normen import ergaenze_note2
    monkeypatch.delenv("NORMPRUEFUNG", raising=False)
    bericht = ergaenze_berichte(Pruefbericht(lv=NOTE2_LV, findings=[], kennzahlen=Kennzahlen(
        positionen=3, findings=0, kritisch=0)), db=None)
    mit = ergaenze_note2(bericht, register_mit(True), checked_on=STICHTAG)
    notes = mit.berichte[0].notes
    assert [(n["id"], n["step"]) for n in notes] == [("Note2:03.01", "standards"), ("Note2:03.02", "standards")]
    assert "NORM:DIN 1045-2:min_strength_class:XC4" in notes[0]["text"]
    assert "2 Note 2 standards comparison(s)" in mit.berichte[0].meldung
    assert mit.findings == bericht.findings and mit.berichte[1:] == bericht.berichte[1:]
    assert ergaenze_note2(mit, register_mit(True), checked_on=STICHTAG).berichte[0].notes == notes  # no duplicates
    unverified = ergaenze_note2(bericht, register_mit(False), checked_on=STICHTAG).berichte[0].notes
    assert unverified[0]["text"].startswith("Manual review: no verified applicable German source")
    monkeypatch.setenv("NORMPRUEFUNG", "0")
    assert ergaenze_note2(bericht, register_mit(True), checked_on=STICHTAG) is bericht


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


# ---------------------------------------------------------------------------
# B2 (issue #95): check 1 severity rules – lower, bigger, missing, extra.
# Synthetic register values only (marked "synthetic"); no dataset text.
# ---------------------------------------------------------------------------
from app.pruefung.normen import (  # noqa: E402
    NORM_EXTRA, NORM_KENNWERT_HOEHER, NORM_POSITION_FEHLT, Pflichtposition, Regelwerksvorgaben,
    pruefe_kennwerte_hoeher, pruefe_pflichtpositionen, vorgaben_aus_regelwerk,
)

SYNTH_QUELLE = {"url": "https://example.org/synthetic-regulation", "abgerufen": "2026-11-21"}
SYNTH_PFLICHT = {
    "id": "SYNTH-P1", "gewerk": "synthetic floor slab", "gewerk_merkmale": ["Bodenplatte"],
    "position": "synthetic blinding layer", "merkmale": ["Sauberkeitsschicht"],
    "fundstelle": "synthetic test value", "quelle": SYNTH_QUELLE, "faktor": 1.0, "einheit": "m²",
}
SYNTH_EXTRA = {
    "id": "SYNTH-E1", "gewerk": "synthetic floor slab", "gewerk_merkmale": ["Bodenplatte"],
    "position": "synthetic formwork cleaning", "merkmale": ["Schalung reinigen"],
    "fundstelle": "synthetic test value", "quelle": SYNTH_QUELLE,
}


def pflicht(roh: dict) -> Pflichtposition:
    return normen._pruefe_pflichtposition(roh, "test", "pflichtpositionen")


def b2_register(geprueft: bool, pflicht_roh=(SYNTH_PFLICHT,), extra_roh=(SYNTH_EXTRA,)) -> normen.Register:
    """The repository register with synthetic required/not-required items on the DIN 1045-2 entry."""
    basis = register_mit(geprueft)
    return normen.Register(stand=basis.stand, eintraege=[
        dataclasses.replace(
            e, pflichtpositionen=tuple(pflicht(p) for p in pflicht_roh),
            nicht_erforderlich=tuple(normen._pruefe_pflichtposition(x, "test", "nicht_erforderlich")
                                     for x in extra_roh),
        ) if e.norm_id == "DIN 1045-2" else e
        for e in basis.eintraege
    ])


def b2_lv(*positionen: tuple[str, str, float, str]) -> LV:
    return LV(name="Synthetic B2 LV", quelle="test", positionen=[
        Position(oz=f"05.{i:02d}", kurztext=kurz, langtext=lang, menge=menge, einheit=einheit)
        for i, (kurz, lang, menge, einheit) in enumerate(positionen, start=1)
    ])


def b2_texte(findings) -> list[str]:
    return [t for f in findings for t in (f.titel, f.begruendung, f.vorschlag)]


def test_b2_lower_checked_is_hoch_and_unchecked_is_mittel():
    lv = beton_lv("Beton XC4, C20/25")
    [geprueft] = pruefe_kennwerte(lv, register_mit(geprueft=True))
    [ungeprueft] = pruefe_kennwerte(lv, register_mit(geprueft=False))
    assert (geprueft.regel_id, geprueft.schwere) == (NORM_KENNWERT_ABWEICHUNG, "hoch")
    assert (ungeprueft.regel_id, ungeprueft.schwere) == (NORM_KENNWERT_ABWEICHUNG, "mittel")
    assert geprueft.model_copy(update={"schwere": "mittel"}) == ungeprueft.model_copy(
        update={"begruendung": geprueft.begruendung})  # only severity and the checked-by note differ


@pytest.mark.parametrize("geprueft", [True, False])
def test_b2_bigger_is_mittel_warning(geprueft):
    lv = beton_lv("Beton XC4, C35/45")
    assert pruefe_kennwerte(lv, register_mit(geprueft)) == []
    if not geprueft:  # only checked sources may make the bigger case a finding
        assert pruefe_kennwerte_hoeher(lv, register_mit(geprueft)) == []
        assert pruefe_normen(lv, register_mit(geprueft)) == []
        return
    [finding] = pruefe_kennwerte_hoeher(lv, register_mit(geprueft))
    assert (finding.id, finding.regel_id, finding.kategorie, finding.schwere, finding.quelle) == (
        f"{NORM_KENNWERT_HOEHER}:02.01", NORM_KENNWERT_HOEHER, "risiko", "mittel", "regel")
    assert "C35/45" in finding.titel and "C25/30" in finding.titel and finding.euro_wirkung is None
    assert "note the difference" in finding.begruendung and KENNWERT_URL in finding.begruendung
    assert finding.vorschlag.startswith("Bidder question")
    assert [f.regel_id for f in pruefe_normen(lv, register_mit(geprueft))] == [NORM_KENNWERT_HOEHER]


def test_b2_equal_class_gives_neither_lower_nor_bigger():
    lv = beton_lv("Beton XC4, C25/30")
    assert pruefe_kennwerte(lv, register_mit(True)) == pruefe_kennwerte_hoeher(lv, register_mit(True)) == []


def test_b2_missing_required_item_is_hoch_with_what_and_how_much():
    lv = b2_lv(("Bodenplatte C25/30", "Bodenplatte d=25 cm.", 120.0, "m2"),
               ("Bodenplatte Randbereich", "Bodenplatte Rand.", 30.0, "m²"),
               ("Wand", "Mauerwerk.", 50.0, "m²"))
    [finding] = pruefe_pflichtpositionen(lv, b2_register(geprueft=True))
    assert (finding.id, finding.regel_id, finding.oz, finding.kategorie, finding.schwere, finding.quelle) == (
        f"{NORM_POSITION_FEHLT}:05.01", NORM_POSITION_FEHLT, "05.01", "nachtrag", "hoch", "regel")
    assert "Missing: synthetic blinding layer, 150 m² (1 × 150 m² of OZ 05.01, 05.02)" in finding.begruendung
    assert "OZ 05.01, 05.02" in finding.begruendung and "https://example.org/synthetic-regulation" in finding.begruendung
    assert finding.vorschlag.startswith("OZ 05.01:") and finding.vorschlag.endswith("Please confirm.")
    assert finding.euro_wirkung is None


def test_b2_missing_with_absolute_or_no_quantity():
    lv = b2_lv(("Bodenplatte", "Beton.", 10.0, "m³"))
    absolut = {**SYNTH_PFLICHT, "faktor": None, "menge": 2, "einheit": "St"}
    absolut.pop("faktor")
    ohne = {k: v for k, v in SYNTH_PFLICHT.items() if k not in ("faktor", "einheit")}
    [a] = pruefe_pflichtpositionen(lv, b2_register(True, [absolut], []))
    [o] = pruefe_pflichtpositionen(lv, b2_register(True, [ohne], []))
    [f] = pruefe_pflichtpositionen(lv, b2_register(True, [SYNTH_PFLICHT], []))
    assert "2 St (quantity stated by the source)" in a.begruendung
    assert "quantity not stated by the source; to be determined" in o.begruendung
    assert "no work-type item is measured in m²" in f.begruendung


def test_b2_no_missing_when_item_present_or_work_type_absent():
    vorhanden = b2_lv(("Bodenplatte", "Beton.", 100.0, "m²"), ("Sauberkeitsschicht", "C8/10, 5 cm.", 100.0, "m²"))
    ohne_gewerk = b2_lv(("Wand", "Mauerwerk.", 50.0, "m²"))
    assert pruefe_pflichtpositionen(vorhanden, b2_register(True, extra_roh=())) == []
    assert pruefe_pflichtpositionen(ohne_gewerk, b2_register(True)) == []


def test_b2_extra_item_is_niedrig_notice():
    lv = b2_lv(("Bodenplatte", "Beton.", 100.0, "m²"), ("Sauberkeitsschicht", "C8/10.", 100.0, "m²"),
               ("Schalung reinigen", "Nach dem Betonieren.", 1.0, "psch"))
    [finding] = pruefe_pflichtpositionen(lv, b2_register(geprueft=True))
    assert (finding.id, finding.regel_id, finding.oz, finding.kategorie, finding.schwere) == (
        f"{NORM_EXTRA}:05.03", NORM_EXTRA, "05.03", "risiko", "niedrig")
    assert "For awareness only" in finding.begruendung and finding.vorschlag.startswith("OZ 05.03:")
    # Without the work type in the LV the same item is not flagged.
    assert pruefe_pflichtpositionen(b2_lv(("Schalung reinigen", "x", 1.0, "psch")), b2_register(True)) == []


def test_b2_unchecked_register_entry_never_produces_hoch():
    register = b2_register(geprueft=False)
    lv = b2_lv(("Bodenplatte XC4, C20/25", "Bodenplatte.", 100.0, "m²"),
               ("Fundament XC4, C35/45", "Beton.", 10.0, "m³"),
               ("Schalung reinigen", "x", 1.0, "psch"))
    findings = pruefe_normen(lv, register)
    assert {f.regel_id for f in findings} >= {NORM_KENNWERT_ABWEICHUNG, NORM_POSITION_FEHLT, NORM_EXTRA}
    assert NORM_KENNWERT_HOEHER not in {f.regel_id for f in findings}
    assert all(f.schwere != "hoch" for f in findings if f.regel_id.startswith("NORM_KENNWERT")
               or f.regel_id in (NORM_POSITION_FEHLT, NORM_EXTRA))
    assert [f.schwere for f in findings if f.regel_id == NORM_POSITION_FEHLT] == ["mittel"]
    assert "not yet checked by a person (geprueft: false)" in next(
        f.begruendung for f in findings if f.regel_id == NORM_POSITION_FEHLT)


def test_b2_all_four_cases_in_one_lv_with_checked_register():
    lv = b2_lv(("Bodenplatte XC4, C20/25", "Bodenplatte.", 100.0, "m²"),
               ("Fundament XC4, C35/45", "Beton.", 10.0, "m³"),
               ("Schalung reinigen", "x", 1.0, "psch"))
    findings = pruefe_normen(lv, b2_register(geprueft=True))
    assert [(f.regel_id, f.oz, f.schwere) for f in findings] == [
        (NORM_KENNWERT_ABWEICHUNG, "05.01", "hoch"), (NORM_POSITION_FEHLT, "05.01", "hoch"),
        (NORM_KENNWERT_HOEHER, "05.02", "mittel"), (NORM_EXTRA, "05.03", "niedrig"),
    ]
    assert len({f.id for f in findings}) == len(findings)
    for f in findings:
        assert not CLAIM_WORDS.search(" ".join((f.titel, f.begruendung, f.vorschlag))), f.id
        assert KEIN_NORMGUTACHTEN in f.begruendung and f.quelle == "regel" and f.euro_wirkung is None


def test_b2_repository_register_has_no_required_items_so_nothing_new_fires():
    register = lade_register()
    assert all(e.pflichtpositionen == () and e.nicht_erforderlich == () for e in register.eintraege)
    lv = b2_lv(("Bodenplatte", "Beton.", 100.0, "m²"), ("Schalung reinigen", "x", 1.0, "psch"))
    assert pruefe_pflichtpositionen(lv, register) == []


def test_b2_register_json_accepts_and_validates_required_items(tmp_path):
    register = lade_register(schreibe_register(tmp_path, pflichtpositionen=[SYNTH_PFLICHT],
                                               nicht_erforderlich=[SYNTH_EXTRA]))
    [eintrag] = register.eintraege
    assert eintrag.pflichtpositionen[0] == Pflichtposition(
        id="SYNTH-P1", gewerk="synthetic floor slab", gewerk_merkmale=("Bodenplatte",),
        position="synthetic blinding layer", merkmale=("Sauberkeitsschicht",), fundstelle="synthetic test value",
        quelle=SYNTH_QUELLE, menge=None, faktor=1.0, einheit="m²")
    assert eintrag.nicht_erforderlich[0].id == "SYNTH-E1"


@pytest.mark.parametrize("liste, aenderung, fehler", [
    ("pflichtpositionen", {"gewerk_merkmale": []}, "gewerk_merkmale"),
    ("pflichtpositionen", {"merkmale": [""]}, "merkmale"),
    ("pflichtpositionen", {"menge": 3}, "either 'menge' or 'faktor'"),
    ("pflichtpositionen", {"faktor": -1}, "positive"),
    ("pflichtpositionen", {"einheit": None}, "needs 'einheit'"),
    ("pflichtpositionen", {"quelle": {"url": "http://example.org", "abgerufen": "2026-11-21"}}, "https"),
    ("pflichtpositionen", {"quelle": {"url": "https://example.org"}}, "abgerufen"),
    ("pflichtpositionen", {"extra": 1}, "unknown fields"),
    ("nicht_erforderlich", {"menge": 1, "einheit": "St"}, "take no"),
])
def test_b2_register_rejects_invalid_required_items(tmp_path, liste, aenderung, fehler):
    basis = SYNTH_PFLICHT if liste == "pflichtpositionen" else SYNTH_EXTRA
    with pytest.raises(ValueError, match=fehler):
        lade_register(schreibe_register(tmp_path, **{liste: [{**basis, **aenderung}]}))


def test_b2_register_rejects_duplicate_required_item_ids(tmp_path):
    with pytest.raises(ValueError, match="duplicate ids"):
        lade_register(schreibe_register(tmp_path, pflichtpositionen=[SYNTH_PFLICHT, SYNTH_PFLICHT]))


SYNTH_REGELWERK = {
    "id": "rw-1", "dateiname": "synthetic_spec.pdf", "normverweise": [], "warnungen": [],
    "kennwerte": [
        {"norm": "DIN 1045-2", "kennwert": "minimum strength class XC4", "wert": "C30/37", "einheit": None,
         "fundstelle": "p. 2"},
        {"norm": "DIN 1045-2", "kennwert": "maximum w/c ratio XC4", "wert": "0.50", "einheit": None,
         "fundstelle": "p. 2"},
        {"norm": None, "kennwert": "maximum strength class", "bedingung": "XC1", "wert": "C50/60",
         "einheit": None, "fundstelle": "p. 3"},
    ],
    "pflichtpositionen": [{k: v for k, v in SYNTH_PFLICHT.items() if k != "quelle"}],
}


def test_b2_uploaded_regulation_values_feed_lower_and_cite_the_file():
    vorgaben = vorgaben_aus_regelwerk(SYNTH_REGELWERK)
    assert [(k.bedingung, k.value, k.fundstelle) for k in vorgaben.kennwerte] == [("XC4", "C30/37", "DIN 1045-2, p. 2")]
    lv = beton_lv("Beton XC4, C25/30")  # equal to the register value, below the uploaded document
    assert pruefe_kennwerte(lv, register_mit(False)) == []
    [finding] = pruefe_kennwerte(lv, register_mit(False), vorgaben)
    assert (finding.regel_id, finding.schwere) == (NORM_KENNWERT_ABWEICHUNG, "hoch")
    assert "uploaded regulation document synthetic_spec.pdf" in finding.begruendung
    assert "synthetic_spec.pdf" in finding.vorschlag and "C30/37" in finding.titel
    assert not CLAIM_WORDS.search(" ".join(b2_texte([finding])))
    # The bigger case uses the strictest value as well.
    [hoeher] = pruefe_kennwerte_hoeher(beton_lv("Beton XC4, C35/45"), register_mit(False), vorgaben)
    assert "minimum C30/37 listed by the uploaded regulation document synthetic_spec.pdf" in hoeher.vorschlag


def test_b2_uploaded_regulation_required_items_count_as_checked():
    vorgaben = vorgaben_aus_regelwerk(SYNTH_REGELWERK)
    lv = b2_lv(("Bodenplatte", "Beton.", 80.0, "m²"))
    [finding] = pruefe_pflichtpositionen(lv, lade_register(), vorgaben)
    assert (finding.regel_id, finding.schwere) == (NORM_POSITION_FEHLT, "hoch")
    assert "uploaded regulation document synthetic_spec.pdf (synthetic test value)" in finding.begruendung
    assert "80 m²" in finding.begruendung
    assert vorgaben_aus_regelwerk(None) is None
    assert vorgaben_aus_regelwerk({"dateiname": "x.pdf", "kennwerte": [], "pflichtpositionen": [{"id": "bad"}]}) == (
        Regelwerksvorgaben("x.pdf"))


def test_b2_switch_off_and_hook_with_uploaded_values(monkeypatch):
    vorgaben = vorgaben_aus_regelwerk(SYNTH_REGELWERK)
    lv = beton_lv("Beton XC4, C25/30")
    monkeypatch.setenv("NORMPRUEFUNG", "off")
    assert pruefe_normen_sicher(lv, vorgaben) == [] and pruefe_normen_sicher(lv) == []
    monkeypatch.delenv("NORMPRUEFUNG")
    monkeypatch.setenv("NORM_KI_RECHERCHE", "off")
    assert [f.regel_id for f in pruefe_normen_sicher(lv, vorgaben)] == [NORM_KENNWERT_ABWEICHUNG]
    assert pruefe_normen_sicher(lv) == pruefe_normen(lv)


# ---------------------------------------------------------------------------
# B4 (issue #97, epic #93): register key values as Note 2 sources and assumption notes in the report.
# ---------------------------------------------------------------------------
from app.pruefung.normen import ergaenze_annahmen, mit_register_quellen  # noqa: E402

XC4_QUELLE = "NORM:DIN 1045-2:min_strength_class:XC4"


def note2_anfrage(**extra) -> dict:
    return {"step": "standards", "lv": NOTE2_LV.model_dump(mode="json"), "checked_on": STICHTAG.isoformat(), **extra}


def nutzer_quelle(oz: str = "03.01", wert: float = 20) -> dict:
    return {"spec_id": "U1", "source_type": "user", "category": "user_requirement", "document_ref": "client spec",
            "location": "p. 3", "as_of": "2026-11-20", "scope": {"oz": [oz]}, "verified": True,
            "requirement": {"parameter": "concrete strength f_ck,cyl for exposure class XC4", "comparator": "eq",
                            "value": wert, "unit": "N/mm²"}}


def test_b4_checked_register_entry_is_a_source_of_note_2(monkeypatch):
    monkeypatch.delenv("NORMPRUEFUNG", raising=False)
    monkeypatch.setattr(normen, "lade_register", lambda path=None: register_mit(True))
    client = TestClient(main.app)
    body = client.post("/api/comparison/steps", json=note2_anfrage()).json()
    assert body["status"] == "complete" and body["errors"] == []
    notes = {n["id"]: n for n in body["notes"]}
    assert list(notes) == ["Note2:03.01", "Note2:03.02"]  # 03.03 cites no register norm
    assert XC4_QUELLE in notes["Note2:03.01"]["text"]
    assert [e["reference_id"] for e in notes["Note2:03.01"]["evidence"]] == [XC4_QUELLE]
    # With a deviating user requirement Note 2 states the deviation against the register.
    mit_nutzer = client.post("/api/comparison/steps", json=note2_anfrage(sources=[nutzer_quelle()])).json()
    note = {n["id"]: n for n in mit_nutzer["notes"]}["Note2:03.01"]
    assert note["text"].startswith("Deviation for OZ 03.01") and XC4_QUELLE in note["text"]
    assert {e["reference_id"] for e in note["evidence"]} == {XC4_QUELLE, "U1"}


def test_b4_unchecked_register_entry_is_not_used(monkeypatch):
    monkeypatch.delenv("NORMPRUEFUNG", raising=False)
    client = TestClient(main.app)
    nur_lv = client.post("/api/comparison/steps", json=note2_anfrage()).json()
    assert nur_lv["status"] == "error" and nur_lv["errors"][0]["code"] == "placeholder_unavailable"
    body = client.post("/api/comparison/steps", json=note2_anfrage(sources=[nutzer_quelle()])).json()
    [note] = body["notes"]  # repository register: DIN 1045-2 is geprueft false
    assert note["text"].startswith("Manual review: no verified applicable German source for OZ 03.01")
    assert [e["reference_id"] for e in note["evidence"]] == ["U1"] and XC4_QUELLE not in json.dumps(body)


def test_b4_note_2_hook_keeps_other_requests_unchanged(monkeypatch):
    from app.ai.step_api import StepRequest
    monkeypatch.setattr(normen, "lade_register", lambda path=None: register_mit(True))
    standards = StepRequest.model_validate(note2_anfrage(sources=[nutzer_quelle()]))
    vergleich = StepRequest.model_validate(note2_anfrage(step="comparison", sources=[nutzer_quelle()]))
    ohne_stichtag = StepRequest.model_validate({"step": "standards", "lv": NOTE2_LV.model_dump(mode="json")})
    assert mit_register_quellen(vergleich) is vergleich and mit_register_quellen(ohne_stichtag) is ohne_stichtag
    xc1 = "NORM:DIN 1045-2:min_strength_class:XC1"
    assert [s.spec_id for s in mit_register_quellen(standards).sources] == ["U1", xc1, XC4_QUELLE]
    eigene = StepRequest.model_validate(note2_anfrage(sources=[{**nutzer_quelle(), "spec_id": XC4_QUELLE}]))
    assert [s.spec_id for s in mit_register_quellen(eigene).sources] == [XC4_QUELLE, xc1]  # caller's id wins
    monkeypatch.setenv("NORMPRUEFUNG", "off")
    assert mit_register_quellen(standards) is standards


def test_b4_note_2_switch_off_gives_todays_response(monkeypatch):
    monkeypatch.setattr(normen, "lade_register", lambda path=None: register_mit(True))
    client = TestClient(main.app)
    anfragen = [note2_anfrage(), note2_anfrage(sources=[nutzer_quelle()])]
    monkeypatch.setenv("NORMPRUEFUNG", "off")
    aus = [client.post("/api/comparison/steps", json=a).content for a in anfragen]
    monkeypatch.setattr(normen, "mit_register_quellen", lambda request, register=None: request)
    assert aus == [client.post("/api/comparison/steps", json=a).content for a in anfragen]


def test_b4_note_2_hook_errors_are_logged_and_skipped(monkeypatch, caplog):
    from app.ai.step_api import StepRequest
    def kaputt(*args, **kwargs):
        raise RuntimeError("synthetic failure")
    monkeypatch.setattr(normen, "lade_register", kaputt)
    anfrage = StepRequest.model_validate(note2_anfrage())
    with caplog.at_level(logging.ERROR, logger=normen.__name__):
        assert mit_register_quellen(anfrage) is anfrage
    assert "Note 2 failed" in caplog.text


ANNAHME_LV = beton_lv("Beton XC4, C20/25", "Stahlbeton nach DIN 1045-2 liefern.")


def test_b4_assumption_note_is_visible_in_the_report(monkeypatch):
    for key in LLM_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("NORMPRUEFUNG", raising=False)
    client = TestClient(main.app)
    lv = ANNAHME_LV.model_dump(mode="json")
    heute = client.post("/api/lv/pruefen", json=lv).json()  # repository register: unchecked, no assumption
    monkeypatch.setattr(normen, "lade_register", lambda path=None: register_mit(True))
    with monkeypatch.context() as m:
        m.setattr(main, "ergaenze_annahmen", lambda bericht: bericht)
        ohne_hook = client.post("/api/lv/pruefen", json=lv).json()
    an = client.post("/api/lv/pruefen", json=lv).json()
    assert an["findings"] == ohne_hook["findings"]  # findings unchanged, only the hook differs
    assert [f["regel_id"] for f in an["findings"] if f["regel_id"] == NORM_KENNWERT_ABWEICHUNG] == [
        NORM_KENNWERT_ABWEICHUNG]
    regelwerk = an["berichte"][0]
    assert regelwerk["id"] == "regelwerk"
    [note] = [n for n in regelwerk["notes"] if n["id"] == "NormAssumption:02.01"]
    assert note["assumption"].startswith(f"{ANNAHME_PRAEFIX}: for 120 m³ (OZ 02.01) C25/30 instead of C20/25")
    assert (note["step"], note["approval_required"], note["manual_review"], note["oz"]) == (
        "standards", True, True, "02.01")
    assert ANNAHME_PRAEFIX in regelwerk["meldung"]
    assert regelwerk["zaehler"]["empfehlungen"] == ohne_hook["berichte"][0]["zaehler"]["empfehlungen"] + 1
    assert an["zusammenfassung"]["empfehlungen"] == ohne_hook["zusammenfassung"]["empfehlungen"] + 1
    assert an["zusammenfassung"]["score"] == ohne_hook["zusammenfassung"]["score"]  # never a penalty
    [zeile] = an["schlussbericht"]["positionen"]
    assert note["assumption"] in zeile["empfehlungen"]
    assert all(not n["id"].startswith("NormAssumption") for n in heute["berichte"][0]["notes"])


def test_b4_assumption_switch_off_gives_todays_report(monkeypatch):
    for key in LLM_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(normen, "lade_register", lambda path=None: register_mit(True))
    client = TestClient(main.app)
    lv = ANNAHME_LV.model_dump(mode="json")
    monkeypatch.setenv("NORMPRUEFUNG", "off")
    aus = client.post("/api/lv/pruefen", json=lv)
    monkeypatch.setattr(main, "ergaenze_annahmen", lambda bericht: bericht)
    heute = client.post("/api/lv/pruefen", json=lv)
    assert aus.status_code == heute.status_code == 200 and aus.content == heute.content


def test_b4_assumption_hook_returns_the_report_unchanged_without_notes_or_on_error(monkeypatch, caplog):
    bericht = main.pruefen(beton_lv("Beton XC4, C25/30", "Stahlbeton nach DIN 1045-2 liefern."))
    assert ergaenze_annahmen(bericht, register_mit(True)) is bericht  # no deviation → no assumption
    def kaputt(*args, **kwargs):
        raise RuntimeError("synthetic failure")
    monkeypatch.setattr(normen, "pruefe_kennwerte_sicher", kaputt)
    with caplog.at_level(logging.ERROR, logger=normen.__name__):
        assert ergaenze_annahmen(bericht, register_mit(True)) is bericht
    assert "Assumption notes for the report failed" in caplog.text


def test_b4_analyse_without_regelwerk_equals_pruefen_and_carries_the_assumption(monkeypatch):
    for key in LLM_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("NORMPRUEFUNG", raising=False)
    monkeypatch.setattr(normen, "lade_register", lambda path=None: register_mit(True))
    client = TestClient(main.app)
    lv = ANNAHME_LV.model_dump(mode="json")
    pruefen = client.post("/api/lv/pruefen", json=lv)
    analyse = client.post("/api/lv/analyse", json={"lv": lv, "regelwerk": None})
    assert pruefen.status_code == analyse.status_code == 200 and analyse.content == pruefen.content
    assert "NormAssumption:02.01" in [n["id"] for n in analyse.json()["berichte"][0]["notes"]]


def test_139_spaced_strength_class_is_normalized_for_check_1():
    lv = beton_lv("Beton C 20/25", "Expositionsklasse XC4")
    [finding] = pruefe_kennwerte(lv, register_mit(True))
    assert (finding.regel_id, finding.schwere) == (NORM_KENNWERT_ABWEICHUNG, "hoch")
    assert "C20/25" in finding.titel and "C25/30" in finding.titel


@pytest.mark.parametrize("quelle,erwartet", [("unchecked", 0), ("checked", 1), ("upload", 1)])
def test_139_bigger_spaced_class_only_from_checked_sources(quelle, erwartet):
    lv = beton_lv("Beton C 35/45", "Expositionsklasse XC4")
    register = register_mit(quelle == "checked")
    vorgaben = vorgaben_aus_regelwerk(SYNTH_REGELWERK) if quelle == "upload" else None
    findings = pruefe_kennwerte_hoeher(lv, register, vorgaben)
    assert len(findings) == erwartet
    assert all(f.schwere == "mittel" for f in findings)

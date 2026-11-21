from pathlib import Path

import pytest

from app.modelle import Finding, LV, Position
from app.risiko.scoring import bewerte
from app.pruefung.regeln import pruefe_regeln


def test_scoring_preserves_existing_evidence_without_inventing_prices():
    finding = Finding(id="f1", oz="01", kategorie="fehler", schwere="hoch", titel="Missing quantity",
                      begruendung="Menge ist null.", vorschlag="Menge anfragen.", quelle="regel", regel_id="MENGE_FEHLT")
    assert bewerte(LV(name="Test", quelle="synthetisch"), [finding]) == [finding]
    assert finding.euro_wirkung is None


def test_explicit_work_conditions_produce_evidenced_bidder_questions():
    lv = LV(name="Synthetic conditions", quelle="synthetic", positionen=[
        Position(oz="01", typ="bedarf", kurztext="Optional excavation"),
        Position(oz="02", typ="pauschal", kurztext="Site setup"),
        Position(oz="03", typ="stundenlohn", kurztext="Labour"),
        Position(oz="04", kurztext="Concrete", langtext="Supply as required"),
    ])
    findings = bewerte(lv, [])
    assert {f.oz for f in findings} == {"01", "02", "03", "04"}
    assert len(findings) == 4
    for f in findings:
        assert f.quelle == "regel"
        assert f.kategorie in {"risiko", "nachtrag"}
        assert f.oz in f.begruendung and f.oz in f.vorschlag
        assert "?" in f.vorschlag
        assert f.euro_wirkung is None
        assert "Uncertainty" in f.begruendung
        assert "no evidenced euro impact" in f.begruendung
    assert len({f.vorschlag for f in findings}) == 4


def test_synthetic_lv_keeps_every_fixed_rule_finding_unchanged():
    lv = LV.model_validate_json((Path(__file__).parents[2] / "data/beispiel_lv.json").read_text())
    original = pruefe_regeln(lv)
    assert original
    result = bewerte(lv, original)
    assert all(f in result for f in original)
    assert len({f.id for f in result}) == len(result)


def test_clean_boq_has_no_invented_domain_risks():
    lv = LV(name="Clean", quelle="synthetic", positionen=[
        Position(oz="01", kurztext="Concrete", langtext="Supply concrete", menge=2,
                 einheit="m³", ep=10, gp=20),
    ])
    assert bewerte(lv, []) == []
    assert bewerte(LV(name="Empty", quelle="synthetic"), []) == []


def test_priority_view_keeps_all_hints_and_ranks_by_uncertainty_then_euro_evidence():
    lv = LV(name="Large", quelle="synthetic", positionen=[
        Position(oz=f"{i:03}", typ="bedarf", gp=999999) for i in range(105)
    ] + [Position(oz="lump", typ="pauschal")])
    supplied = Finding(id="evidenced", oz="104", kategorie="nachtrag", schwere="hoch",
                       titel="Measured discrepancy", begruendung="Measured discrepancy evidence.",
                       vorschlag="Please confirm the measured scope?", quelle="regel",
                       regel_id="MEASURED", euro_wirkung=-50)
    before = supplied.model_dump()
    result = bewerte(lv, [supplied])
    assert len(result) == 107
    assert result[0].id == "evidenced"
    assert "evidenced euro impact -50 EUR" in result[0].begruendung
    assert result[-1].oz == "lump"
    assert sum("Priority view" in f.begruendung for f in result) == 100
    assert "Review remainder" in result[100].begruendung
    assert "rank 1/107" in result[0].begruendung
    assert all(f.euro_wirkung is None for f in result if f.id != "evidenced")
    assert supplied.model_dump() == before
    assert result == bewerte(lv, [supplied])
    assert [f.oz for f in result[1:4]] == ["000", "001", "002"]


def test_material_context_sums_only_matching_descriptions_units_and_work_types():
    lv = LV(name="Materials", quelle="synthetic", positionen=[
        Position(oz="c1", kurztext="Concrete", typ="bedarf", menge=2, einheit="m³"),
        Position(oz="c2", kurztext="Concrete", typ="bedarf", menge=3, einheit="m³"),
        Position(oz="s", kurztext="Steel", typ="bedarf", menge=50, einheit="kg"),
        Position(oz="c3", kurztext="Concrete", typ="bedarf", menge=8, einheit="kg"),
        Position(oz="grade", kurztext="Concrete C30", typ="bedarf", menge=7, einheit="m³"),
        Position(oz="firm", kurztext="Concrete", menge=100, einheit="m³"),
    ])
    result = {f.oz: f for f in bewerte(lv, [])}
    assert '"Concrete": 5 m³' in result["c1"].begruendung
    assert "c1, c2" in result["c1"].begruendung
    assert '"Steel": 50 kg' in result["s"].begruendung
    assert '"Concrete": 8 kg' in result["c3"].begruendung
    assert '"Concrete C30": 7 m³' in result["grade"].begruendung


def test_unknown_material_quantities_are_not_reported_as_complete_totals():
    lv = LV(name="Partial", quelle="synthetic", positionen=[
        Position(oz="1", kurztext="Concrete", typ="bedarf", menge=0, einheit="m³"),
        Position(oz="2", kurztext="Concrete", typ="bedarf", einheit="m³"),
        Position(oz="3", kurztext="Steel", typ="bedarf", menge=50),
    ])
    result = {f.oz: f for f in bewerte(lv, [])}
    assert "known subtotal 0 m³; 1 unknown quantity" in result["1"].begruendung
    assert "complete total unavailable" in result["2"].begruendung
    assert "unit missing; no material total" in result["3"].begruendung


def test_duplicate_oz_multiple_conditions_and_german_demand_retain_unique_evidence():
    lv = LV(name="Duplicate OZ", quelle="synthetic", positionen=[
        Position(oz="01", typ="alternativ", langtext="Liefern nach Bedarf"),
        Position(oz="01", typ="zulage", langtext="Zusätzliche Leistung bei Bedarf"),
    ])
    before = lv.model_dump()
    result = bewerte(lv, [])
    assert len(result) == 4
    assert len({f.id for f in result}) == 4
    assert all(f.oz == "01" for f in result)
    assert {f.regel_id for f in result} == {"RISK_ALTERNATIV", "RISK_ZULAGE", "RISK_AS_REQUIRED"}
    assert lv.model_dump() == before


def test_ranking_prefers_uncertainty_before_money_and_sorts_evidence_by_absolute_value():
    lv = LV(name="Ranking", quelle="synthetic")
    def hint(id_, severity, amount):
        return Finding(id=id_, oz="01", kategorie="risiko", schwere=severity,
                       titel="Supplied hint", begruendung="Supplied evidence.",
                       vorschlag="Please confirm the scope?", quelle="regel",
                       regel_id="SUPPLIED", euro_wirkung=amount)
    hints = [hint("low", "mittel", 1000), hint("unknown", "hoch", None),
             hint("small", "hoch", 10), hint("large", "hoch", -50)]
    assert [f.id for f in bewerte(lv, hints)] == ["large", "small", "unknown", "low"]
    assert bewerte(lv, hints) == bewerte(lv, list(reversed(hints)))


@pytest.mark.skip(reason="Real GAEB acceptance deferred until importer #6 lands; synthetic LV covered above.")
def test_real_gaeb_risk_acceptance_after_issue_6():
    """Replace with an offline GAEB fixture/import check when #6 is merged."""


def test_position_type_hints_are_mittel_with_short_reason_but_as_required_stays_hoch():
    lv = LV(name="T", quelle="synthetic", positionen=[
        Position(oz="01", typ="bedarf", langtext="nach Bedarf")])
    by_rule = {f.regel_id: f for f in bewerte(lv, [])}
    assert by_rule["RISK_BEDARF"].schwere == "mittel"
    assert "entitlement" not in by_rule["RISK_BEDARF"].begruendung
    assert by_rule["RISK_AS_REQUIRED"].schwere == "hoch"

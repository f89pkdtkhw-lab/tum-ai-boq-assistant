from app.modelle import Finding, LV
from app.risiko.scoring import bewerte


def test_scoring_preserves_existing_evidence_without_inventing_prices():
    finding = Finding(id="f1", oz="01", kategorie="fehler", schwere="hoch", titel="Menge fehlt",
                      begruendung="Menge ist null.", vorschlag="Menge anfragen.", quelle="regel", regel_id="MENGE_FEHLT")
    assert bewerte(LV(name="Test", quelle="synthetisch"), [finding]) == [finding]
    assert finding.euro_wirkung is None

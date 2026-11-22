"""Score and counters: offline, synthetic data only. Five selectable scoring models."""
import json
from pathlib import Path
from types import SimpleNamespace as NS

from fastapi.testclient import TestClient

from app import main
from app.modelle import Finding, LV, Position
from app.pruefung.bewertung import (
    DEFAULT_MODELL, MODELLE, ampel_von, zusammenfassen,
)


def _f(i, schwere, kategorie="fehler", quelle="regel", regel_id="R", oz="01.01"):
    return Finding(id=f"F{i}", oz=oz, kategorie=kategorie, schwere=schwere, titel="t",
                   begruendung="b", vorschlag="v", quelle=quelle, regel_id=regel_id)


def _approx(base=100.0, est=200.0):
    return NS(step="historical_adjustment", base_value=base, estimated_value=est, unit="EUR",
              assumption=None, approval_required=True)


def _lv15():
    return [_f(1, "hoch", kategorie="risiko", quelle="modell", regel_id="KI", oz="1.1.10")]


def test_no_findings_is_ten():
    z = zusammenfassen([])
    assert z.score == 10.0 and z.score_abzuege == [] and z.schaetzung_abweichung_eur is None
    assert z.bewertungsmodell == DEFAULT_MODELL == "ausgewogen"


def test_lv15_all_five_models():
    findings = _lv15()
    erwartet = {
        "streng": (6.5, "gelb", -3.5),
        "gestaffelt": (9.0, "gruen", -1.0),
        "anteil": (5.0, "gelb", -5.0),
        "fehler_klaerung": (9.5, "gruen", -0.5),
        "ausgewogen": (9.5, "gruen", -0.5),
    }
    assert set(erwartet) == set(MODELLE)
    for modell, (score, ampel, punkte) in erwartet.items():
        z = zusammenfassen(findings, n_positionen=2, modell=modell)
        assert z.score == score, modell
        assert ampel_von(z.score, modell) == ampel, modell
        assert z.score_abzuege[0].punkte == punkte, modell
        assert z.bewertungsmodell == modell
    assert zusammenfassen(findings, n_positionen=2, modell="ausgewogen").score_abzuege[0].grund == (
        "Report 1: 1 big problem (−0.5)")
    assert "Share of affected items: 50 % (−5.0)" in zusammenfassen(
        findings, n_positionen=2, modell="anteil").score_abzuege[0].grund


def test_strict_flat_report_deduction():
    z = zusammenfassen([_f(1, "hoch")], n_positionen=2, modell="streng")
    assert z.score == 6.5 and z.grosse_probleme == 1
    assert (z.score_abzuege[0].punkte, z.score_abzuege[0].bericht) == (-3.5, "regelwerk")
    assert zusammenfassen([_f(1, "kritisch")], modell="streng").score == 6.0
    assert zusammenfassen([_f(i, "hoch") for i in range(40)], modell="streng").score == 6.0


def test_warnings_deduct_when_graduated_notices_never_do():
    z = zusammenfassen([_f(1, "mittel"), _f(2, "niedrig"), _f(3, "niedrig")], modell="gestaffelt")
    assert (z.score, z.warnungen, z.hinweise, z.grosse_probleme) == (9.8, 1, 2, 0)
    assert zusammenfassen([_f(1, "mittel"), _f(2, "niedrig")], modell="streng").score == 10.0
    halb = zusammenfassen([_f(1, "mittel", kategorie="nachtrag")], modell="fehler_klaerung")
    assert halb.score == 9.9


def test_balanced_caps_and_scales_large_boqs():
    viele = [_f(i, "hoch", oz=f"01.{i}") for i in range(40)]
    assert zusammenfassen(viele, n_positionen=20, modell="ausgewogen").score == 4.0  # 40, cap 6
    # 5 high errors in 80 items: 5 * sqrt(20/80) = 2.5 → 7.5, green
    z = zusammenfassen(viele[:5], n_positionen=80, modell="ausgewogen")
    assert z.score == 7.5 and ampel_von(z.score, "ausgewogen") == "gruen"


def test_share_uses_the_fraction_of_affected_items():
    fuenf = [_f(i, "hoch", oz=f"0{i}") for i in range(5)]
    assert zusammenfassen(fuenf, n_positionen=300, modell="anteil").score == 9.8
    assert zusammenfassen(fuenf, n_positionen=5, modell="anteil").score == 4.0


def test_twelve_flagged_approximations_capped():
    z = zusammenfassen([], [_approx() for _ in range(12)])
    assert z.score == 9.0 and z.score_abzuege[0].punkte == -1.0 and z.score_abzuege[0].bericht == "vergleich"
    assert z.schaetzung_abweichung_eur == 1200.0


def test_small_approximation_not_flagged():
    z = zusammenfassen([], [_approx(100, 110)])
    assert z.score == 10.0 and z.schaetzung_abweichung_eur == 10.0


def test_recommendations_only_keep_ten():
    notes = [NS(step="what_if", base_value=None, estimated_value=None, unit=None, assumption=None,
                approval_required=True),
             NS(step="standards", base_value=None, estimated_value=None, unit=None, assumption="x",
                approval_required=True)]
    z = zusammenfassen([], notes)
    assert z.score == 10.0 and z.empfehlungen == 2


def test_floor_at_zero_with_many_reports_and_approximations(monkeypatch):
    import app.pruefung.bewertung as bw
    monkeypatch.setattr(bw, "SCORE_START", 1.0)
    z = zusammenfassen([_f(1, "kritisch")], [])
    assert z.score == 0.0


def test_unknown_model_falls_back_to_balanced():
    z = zusammenfassen(_lv15(), n_positionen=2, modell="does-not-exist")
    assert z.bewertungsmodell == "ausgewogen" and z.score == 9.5


def test_route_returns_zusammenfassung_and_keeps_fields():
    lv = LV(name="T", quelle="synthetisch", positionen=[Position(oz="01.01", kurztext="x", menge=1, einheit="m²")])
    r = TestClient(main.app).post("/api/lv/pruefen", json=lv.model_dump())
    body = r.json()
    assert r.status_code == 200 and set(body) >= {"lv", "findings", "kennzahlen", "zusammenfassung"}
    z = body["zusammenfassung"]
    assert 0 <= z["score"] <= 10 and z["schaetzung_abweichung_eur"] is None
    assert z["bewertungsmodell"] == "ausgewogen"


def test_route_honours_bewertungsmodell_query():
    lv = LV(name="T", quelle="synthetisch", positionen=[
        Position(oz="1.1.10", kurztext="x", menge=1, einheit="m²"),
        Position(oz="1.1.20", kurztext="y", menge=1, einheit="m²"),
    ])
    client = TestClient(main.app)
    bad = client.post("/api/lv/pruefen?bewertungsmodell=nope", json=lv.model_dump())
    assert bad.status_code == 422
    # The query is accepted; the exact score depends on the (mock) findings of this tiny bill.
    ok = client.post("/api/lv/pruefen?bewertungsmodell=streng", json=lv.model_dump())
    assert ok.status_code == 200
    assert ok.json()["zusammenfassung"]["bewertungsmodell"] == "streng"


def test_synthetic_boqs_show_pricing_readiness():
    client = TestClient(main.app)
    data = Path(__file__).resolve().parents[2] / "data"
    for name, ready in (("beispiel_lv.json", False), ("beispiel_lv_sauber.json", True)):
        response = client.post("/api/lv/pruefen?bewertungsmodell=streng",
                               json=json.loads((data / name).read_text(encoding="utf-8")))
        assert response.status_code == 200
        score = response.json()["zusammenfassung"]["score"]
        if ready:
            assert score >= 9
        else:
            assert score < 7

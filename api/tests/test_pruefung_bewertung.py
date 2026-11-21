"""Score and counters: offline, synthetic data only."""
import json
from pathlib import Path
from types import SimpleNamespace as NS

from fastapi.testclient import TestClient

from app import main
from app.modelle import Finding, LV, Position
from app.pruefung.bewertung import zusammenfassen


def _f(i, schwere):
    return Finding(id=f"F{i}", oz="01.01", kategorie="fehler", schwere=schwere, titel="t",
                   begruendung="b", vorschlag="v", quelle="regel", regel_id="R")


def _approx(base=100.0, est=200.0):
    return NS(step="historical_adjustment", base_value=base, estimated_value=est, unit="EUR",
              assumption=None, approval_required=True)


def test_no_findings_is_ten():
    z = zusammenfassen([])
    assert z.score == 10.0 and z.score_abzuege == [] and z.schaetzung_abweichung_eur is None


def test_one_big_problem_minus_three_and_a_half():
    z = zusammenfassen([_f(1, "hoch")])
    assert z.score == 6.5 and z.grosse_probleme == 1
    assert (z.score_abzuege[0].punkte, z.score_abzuege[0].bericht) == (-3.5, "regelwerk")


def test_critical_minus_four():
    assert zusammenfassen([_f(1, "kritisch")]).score == 6.0


def test_five_big_problems_minus_four_not_more():
    assert zusammenfassen([_f(i, "hoch") for i in range(40)]).score == 6.0


def test_warnings_and_notices_have_no_penalty():
    z = zusammenfassen([_f(1, "mittel"), _f(2, "niedrig"), _f(3, "niedrig")])
    assert (z.score, z.warnungen, z.hinweise, z.grosse_probleme) == (10.0, 1, 2, 0)


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


def test_route_returns_zusammenfassung_and_keeps_fields():
    lv = LV(name="T", quelle="synthetisch", positionen=[Position(oz="01.01", kurztext="x", menge=1, einheit="m²")])
    r = TestClient(main.app).post("/api/lv/pruefen", json=lv.model_dump())
    body = r.json()
    assert r.status_code == 200 and set(body) >= {"lv", "findings", "kennzahlen", "zusammenfassung"}
    z = body["zusammenfassung"]
    assert 0 <= z["score"] <= 10 and z["schaetzung_abweichung_eur"] is None


def test_synthetic_boqs_show_pricing_readiness():
    client = TestClient(main.app)
    data = Path(__file__).resolve().parents[2] / "data"
    for name, ready in (("beispiel_lv.json", False), ("beispiel_lv_sauber.json", True)):
        response = client.post("/api/lv/pruefen", json=json.loads((data / name).read_text(encoding="utf-8")))
        assert response.status_code == 200
        score = response.json()["zusammenfassung"]["score"]
        if ready:
            assert score >= 9
        else:
            assert score < 7

"""B5 (#98): three reports, final report and what-if list.

Synthetic history records only (invented quantities, prices and notes); no dataset content.
The D1 DB actions are faked; no database, network or model is contacted.
"""
import pytest
from fastapi.testclient import TestClient

from app import main
from app.modelle import LV, Finding, Kennzahlen, Position, Pruefbericht
from app.pruefung import berichte
from app.pruefung.berichte import ergaenze_berichte, erstelle_berichte
from app.pruefung.bewertung import zusammenfassen

client = TestClient(main.app)


def synthetic_lv(name="Synthetic bridge repair") -> LV:
    return LV(name=name, quelle="synthetic:b5", positionen=[
        Position(oz="01.001", kurztext="Concrete removal", menge=100, einheit="m3", ep=50,
                 titel_pfad=["Demolition"]),
        Position(oz="01.002", kurztext="Groundwater lowering", menge=40, einheit="h",
                 titel_pfad=["Demolition"]),
        Position(oz="01.003", kurztext="Railing coating", menge=20, einheit="m", ep=10,
                 titel_pfad=["Coating"]),
        Position(oz="01.004", kurztext="Site sign", menge=None, einheit="St", titel_pfad=["Coating"]),
    ])


def record(case_id, day, tags, concrete, railing, note=""):
    """Seven DB columns; expected/actual objects as in D1 (quantity, unit, unit price, total)."""
    expected = [{"oz": "2.10", "kurztext": "Concrete removal", "menge": concrete[0], "einheit": "m3",
                 "ep": 40, "gp": 40 * concrete[0]},
                {"oz": "2.30", "kurztext": "Railing coating", "menge": railing[0], "einheit": "m"}]
    actual = [{"oz": "2.10", "kurztext": "Concrete removal", "menge": concrete[1], "einheit": "m3"},
              {"oz": "2.30", "kurztext": "Railing coating", "menge": railing[1], "einheit": "m"}]
    return {"id": case_id, "date": f"2026-{day} 10:00:00", "description": "Synthetic case",
            "tags": tags, "expected_json": {"positionen": expected}, "actual_json": {"positionen": actual},
            "note": note}


BRIDGE = [
    record(11, "03-01", ["bridge"], (100, 140), (20, 22), "Groundwater lowering pumping hours underestimated"),
    record(12, "04-01", ["bridge"], (100, 130), (20, 22), "Railing replaced earlier than planned"),
    record(13, "05-01", ["bridge"], (100, 150), (20, 22)),
    record(14, "06-01", ["bridge", "concrete"], (100, 140), (20, 22)),
]
ROAD = [record(21, "07-01", ["road"], (50, 50), (10, 10), "Asphalt milling delayed by frost")]


class FakeDB:
    def __init__(self, records, fail=False):
        self.records, self.fail, self.calls = records, fail, []

    def _check(self, name):
        self.calls.append(name)
        if self.fail:
            raise ConnectionError("synthetic: connection refused")

    def tags(self):
        self._check("tags")
        counts = {}
        for r in self.records:
            for t in r["tags"]:
                counts[t] = counts.get(t, 0) + 1
        return [{"tag": t, "count": c} for t, c in sorted(counts.items())]

    def records_by_tag(self, tag, limit):
        self._check("by_tag")
        hits = [r for r in self.records if tag in r["tags"]]
        return sorted(hits, key=lambda r: r["date"], reverse=True)[:limit]

    def records_latest(self, limit):
        self._check("latest")
        return sorted(self.records, key=lambda r: r["date"], reverse=True)[:limit]


def finding(fid, oz, schwere, kategorie="fehler"):
    return Finding(id=fid, oz=oz, kategorie=kategorie, schwere=schwere, titel=f"Synthetic {fid}",
                   begruendung="Synthetic reason", vorschlag="Synthetic proposal", quelle="regel",
                   regel_id="SYNTH")


FINDINGS = [finding("F1", "01.001", "kritisch"), finding("F2", "01.003", "mittel", "nachtrag"),
            finding("F3", "01.002", "niedrig"), finding("F4", "LV", "hoch")]


def test_report_1_lists_all_findings_with_severity_groups():
    regelwerk = erstelle_berichte(synthetic_lv(), FINDINGS, db=None)["berichte"][0]
    assert regelwerk.id == "regelwerk" and regelwerk.status == "ok"
    assert regelwerk.finding_ids == ["F1", "F2", "F3", "F4"]
    assert (regelwerk.zaehler.grosse_probleme, regelwerk.zaehler.warnungen, regelwerk.zaehler.hinweise) == (2, 1, 1)


def test_tag_match_gives_approximation_from_the_estimate_step_and_flags_too_big():
    db = FakeDB(BRIDGE + ROAD)
    vergleich = erstelle_berichte(synthetic_lv(), [], db=db)["berichte"][1]
    # "concrete" also occurs in the LV text; the work tag shared by most cases ("bridge") selects them
    assert vergleich.status == "ok" and vergleich.tags == ["bridge", "concrete"] and vergleich.neue_tags == []
    by_oz = {n.oz: n for n in vergleich.naeherungen}
    assert set(by_oz) == {"01.001", "01.003"}  # 01.002 has no history object, 01.004 no quantity
    concrete = by_oz["01.001"]
    assert (concrete.menge, concrete.geschaetzt, concrete.abweichung) == (100, 140, 40)
    assert concrete.abweichung_prozent == 40.0 and concrete.zu_gross is True
    assert concrete.abweichung_eur == 2000.0  # (140 - 100) × EP 50 of this bill
    assert concrete.case_ids == ["14", "13", "12", "11"] and concrete.note_id == "Note3:01.001"
    railing = by_oz["01.003"]
    assert (railing.geschaetzt, railing.abweichung, railing.zu_gross) == (22, 2, False)
    assert vergleich.zaehler.zu_grosse_naeherungen == 1
    notes = {n["id"]: n for n in vergleich.notes}
    assert notes["Note3:01.001"]["step"] == "historical_adjustment"
    assert notes["Note3:01.001"]["approval_required"] is True and notes["Note3:01.001"]["case_count"] == 4
    assert "21" not in concrete.case_ids  # road case is not a similar project


def test_similar_project_problems_from_notes_and_marks():
    vergleich = erstelle_berichte(synthetic_lv(), [], db=FakeDB(BRIDGE))["berichte"][1]
    problems = {p.problem: p for p in vergleich.probleme}
    groundwater = problems["Groundwater lowering pumping hours underestimated"]
    assert groundwater.chance == "hoch" and groundwater.oz == "01.002" and groundwater.case_ids == ["11"]
    railing = problems["Railing replaced earlier than planned"]  # one keyword + shared tag
    assert railing.chance == "hoch" and railing.oz == "01.003" and railing.empfehlung.startswith("Check")


def test_no_comparable_tag_proposes_new_tags_and_no_approximation():
    db = FakeDB(ROAD)
    vergleich = erstelle_berichte(synthetic_lv(), [], db=db)["berichte"][1]
    assert vergleich.status == "ok" and vergleich.tags == []
    assert vergleich.neue_tags == ["bridge", "coating", "demolition"]
    assert vergleich.naeherungen == [] and vergleich.notes == []
    assert "by_tag" not in db.calls


def test_what_if_high_and_low_chance_branches_never_penalise():
    teile = erstelle_berichte(synthetic_lv(), [], db=FakeDB(BRIDGE + ROAD))
    was_wenn = teile["berichte"][2]
    assert was_wenn.status == "ok" and teile["was_wenn"] == was_wenn.probleme
    items = {w.problem: w for w in teile["was_wenn"]}
    high = items["Groundwater lowering pumping hours underestimated"]
    assert high.chance == "hoch" and high.oz == "01.002"
    assert "increasing" in high.empfehlung and "01.002" in high.empfehlung and "11" in high.empfehlung
    low = items["Asphalt milling delayed by frost"]
    assert low.chance == "niedrig" and low.oz is None and low.empfehlung == ""
    assert low.begruendung.startswith("For awareness only")
    assert was_wenn.zaehler.grosse_probleme == 0 and was_wenn.zaehler.warnungen == 0
    assert was_wenn.zaehler.empfehlungen == 2 and was_wenn.zaehler.hinweise == 1


def test_decrease_recommendation_from_note_direction():
    note = record(31, "08-01", ["bridge"], (1, 1), (1, 1), "Concrete removal volume overestimated")
    item = erstelle_berichte(synthetic_lv(), [], db=FakeDB([note]))["was_wenn"][0]
    assert item.chance == "hoch" and item.oz == "01.001" and "decreasing" in item.empfehlung


def test_without_history_reports_2_and_3_are_not_connected():
    teile = erstelle_berichte(synthetic_lv(), FINDINGS, db=None)
    statuses = [b.status for b in teile["berichte"]]
    assert [b.id for b in teile["berichte"]] == ["regelwerk", "vergleich", "was_wenn"]
    assert statuses == ["ok", "nicht_verbunden", "nicht_verbunden"]
    assert "not connected" in teile["berichte"][1].meldung and teile["was_wenn"] == []


def test_unreachable_history_is_not_connected_with_readable_message():
    teile = erstelle_berichte(synthetic_lv(), [], db=FakeDB(BRIDGE, fail=True))
    assert [b.status for b in teile["berichte"]] == ["ok", "nicht_verbunden", "nicht_verbunden"]
    assert "not reachable (ConnectionError)" in teile["berichte"][1].meldung
    assert "refused" not in teile["berichte"][1].meldung  # no raw exception text
    assert len(teile["schlussbericht"].positionen) == 4


def test_unreadable_records_are_skipped():
    broken = [{"id": 41, "date": "not a date", "tags": ["bridge"]}, {"date": "2026-01-01", "tags": ["bridge"]}]
    vergleich = erstelle_berichte(synthetic_lv(), [], db=FakeDB(BRIDGE + broken))["berichte"][1]
    assert vergleich.status == "ok" and len(vergleich.naeherungen) == 2


def test_final_report_keeps_every_item_and_references_every_finding():
    lv = synthetic_lv()
    lv.positionen.append(Position(oz="01.001", kurztext="Duplicate OZ", menge=1, einheit="m3"))
    schluss = erstelle_berichte(lv, FINDINGS, db=FakeDB(BRIDGE + ROAD))["schlussbericht"]
    assert [z.oz for z in schluss.positionen] == [p.oz for p in lv.positionen]
    referenced = [v.finding_id for z in schluss.positionen for v in z.probleme] + [v.finding_id for v in schluss.allgemein]
    assert sorted(referenced) == ["F1", "F2", "F3", "F4"] and [v.finding_id for v in schluss.allgemein] == ["F4"]
    # Duplicate OZ: no approximation is attributed to either row (it would be ambiguous)
    assert [z.geschaetzt for z in schluss.positionen if z.oz == "01.001"] == [None, None]
    assert [z.geschaetzt for z in schluss.positionen if z.oz == "01.003"] == [22]
    assert "bridge" in schluss.projektbeschreibung and "5 item(s) in 2 section(s)" in schluss.projektbeschreibung


def test_final_report_row_carries_estimate_why_need_to_add_problem_and_recommendation():
    schluss = erstelle_berichte(synthetic_lv(), FINDINGS, db=FakeDB(BRIDGE))["schlussbericht"]
    rows = {z.oz: z for z in schluss.positionen}
    concrete = rows["01.001"]
    assert (concrete.geschaetzt, concrete.abweichung, concrete.abweichung_eur) == (140, 40, 2000.0)
    assert "Median actual/expected ratio 1.4" in concrete.warum
    assert any("+40 m3" in n for n in concrete.nachtrag) and concrete.warnungen
    assert [v.finding_id for v in concrete.probleme] == ["F1"]
    assert rows["01.003"].nachtrag[0] == "Synthetic F2"  # Nachtrag finding
    assert rows["01.002"].empfehlungen and "increasing" in rows["01.002"].empfehlungen[0]
    assert rows["01.004"].geschaetzt is None and rows["01.004"].warum == ""
    assert any("exceed" in w for w in schluss.warnungen)


def test_failing_db_action_only_affects_its_report():
    class PartlyDown(FakeDB):
        def records_latest(self, limit):
            return [object()]  # unreadable record shape → skipped, report still ok

        def records_by_tag(self, tag, limit):
            raise TimeoutError("synthetic")

    teile = erstelle_berichte(synthetic_lv(), [], db=PartlyDown(BRIDGE))
    assert [b.status for b in teile["berichte"]] == ["ok", "nicht_verbunden", "ok"]


def test_ergaenze_berichte_leaves_existing_fields_unchanged(monkeypatch):
    lv = synthetic_lv()
    bericht = Pruefbericht(lv=lv, findings=FINDINGS, kennzahlen=Kennzahlen(positionen=4, findings=4, kritisch=1))
    monkeypatch.setattr(berichte, "erstelle_berichte", lambda *a, **k: 1 / 0)
    assert ergaenze_berichte(bericht) is bericht  # any failure: original report, no B5 fields


def test_b1_summary_uses_the_three_report_grouping():
    lv = synthetic_lv()
    bericht = Pruefbericht(lv=lv, findings=FINDINGS, kennzahlen=Kennzahlen(positionen=4, findings=4, kritisch=1),
                           zusammenfassung=zusammenfassen(FINDINGS))
    ohne = ergaenze_berichte(bericht, db=None).zusammenfassung
    assert ohne == zusammenfassen(FINDINGS)  # no history: same as B1 alone
    mit = ergaenze_berichte(bericht, db=FakeDB(BRIDGE + ROAD)).zusammenfassung
    # Report 1 (Balanced): F1 kritisch −2 + F4 hoch −1 + F2 warning (Nachtrag, half) −0.1 = −3.1;
    # Report 2: one approximation too big → −0.1
    assert mit.score == 6.8 and [a.bericht for a in mit.score_abzuege] == ["regelwerk", "vergleich"]
    # 2 approval-required approximations + 2 high-chance items in Report 2 + 2 in Report 3
    assert mit.empfehlungen == 6
    assert mit.schaetzung_abweichung_eur == 2020.0  # +2000 (concrete) + 20 (railing, EP 10)
    assert (mit.grosse_probleme, mit.warnungen, mit.hinweise) == (2, 1, 1)
    assert ergaenze_berichte(bericht.model_copy(update={"zusammenfassung": None}), db=None).zusammenfassung is None


@pytest.fixture
def no_history(monkeypatch):
    monkeypatch.setattr(berichte, "history_db", None)


def test_route_without_history_is_200_and_existing_fields_unchanged(no_history, monkeypatch):
    lv = synthetic_lv().model_dump(mode="json")
    response = client.post("/api/lv/pruefen", json=lv)
    assert response.status_code == 200, response.text
    body = response.json()
    assert [b["status"] for b in body["berichte"]] == ["ok", "nicht_verbunden", "nicht_verbunden"]
    assert body["berichte"][0]["finding_ids"] == [f["id"] for f in body["findings"]]
    assert len(body["schlussbericht"]["positionen"]) == 4 and body["was_wenn"] == []
    monkeypatch.setattr(main, "ergaenze_berichte", lambda bericht: bericht)  # report as before B5
    before = client.post("/api/lv/pruefen", json=lv).json()
    assert {k: body[k] for k in ("lv", "findings", "kennzahlen")} == {
        k: before[k] for k in ("lv", "findings", "kennzahlen")}
    assert before["berichte"] is None and before["was_wenn"] is None and before["schlussbericht"] is None


def test_route_with_injected_history(monkeypatch):
    monkeypatch.setattr(berichte, "history_db", FakeDB(BRIDGE + ROAD))
    body = client.post("/api/lv/pruefen", json=synthetic_lv().model_dump(mode="json")).json()
    assert [b["status"] for b in body["berichte"]] == ["ok", "ok", "ok"]
    assert {n["oz"] for n in body["berichte"][1]["naeherungen"]} == {"01.001", "01.003"}
    assert {w["chance"] for w in body["was_wenn"]} == {"hoch", "niedrig"}


def test_synthetic_example_lv_still_reports(no_history):
    lv = main.load_examples()[0].lv
    body = client.post("/api/lv/pruefen", json=lv.model_dump(mode="json")).json()
    assert len(body["schlussbericht"]["positionen"]) == len(lv.positionen)
    assert body["berichte"][1]["status"] == "nicht_verbunden"

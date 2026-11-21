"""Quantity-relation checks: offline, no parser, synthetic fixtures only."""
from fastapi.testclient import TestClient

from app import main
from app.modelle import LV, Position
from app.pruefung.mengen import RatioRule, pruefe_mengen

SLAB = ["Rohbau", "Bodenplatte"]


def _pos(oz, kurztext, menge, einheit="m²", titel=SLAB, typ="normal", langtext=None):
    return Position(oz=oz, kurztext=kurztext, langtext=kurztext if langtext is None else langtext,
                    menge=menge, einheit=einheit, titel_pfad=list(titel), typ=typ)


def _lv(*positionen):
    return LV(name="Test", quelle="synthetisch", positionen=list(positionen))


def _slab_layers(*mengen):
    names = ("Voranstrich Bodenplatte", "Schweißbahn Bodenplatte",
             "Dämmung Bodenplatte", "PE-Folie Bodenplatte")
    return [_pos(f"01.{i + 1:02d}", name, m) for i, (name, m) in enumerate(zip(names, mengen))]


ACCEPTANCE_LV = _lv(*_slab_layers(205, 150, 120, 130))

CHAIRS_PER_TABLE = RatioRule(
    name="Stühle je Tisch", base_terms=("tisch",), base_unit="St",
    compare_terms=("stuhl", "stühle"), compare_unit="St", minimum=4, maximum=6,
    assumption="Synthetisches, ausdrücklich konfiguriertes Beispiel; keine Baunorm",
)


def test_empty_lv_has_no_invented_findings():
    assert pruefe_mengen(LV(name="Leer", quelle="synthetisch")) == []


def test_acceptance_slab_layers_flag_outliers_with_quantities_and_threshold():
    findings = pruefe_mengen(ACCEPTANCE_LV)
    assert {f.oz for f in findings} == {"01.01", "01.03"}  # 205 m² (+46 %), 120 m² (-14 %) vs median 140
    for f in findings:
        assert f.quelle == "regel"
        assert f.regel_id == "MENGE_SCHICHTEN_ABWEICHUNG"
        assert f.euro_wirkung is None
        assert "median 140 m²" in f.begruendung
        assert "±10%" in f.begruendung and "not a standard" in f.begruendung
        for oz, menge in (("01.01", 205), ("01.02", 150), ("01.03", 120), ("01.04", 130)):
            assert f"OZ {oz}" in f.begruendung and f"{menge} m²" in f.begruendung
    oz_in_lv = {p.oz for p in ACCEPTANCE_LV.positionen}
    assert {f.oz for f in findings} <= oz_in_lv
    assert len({f.id for f in findings}) == len(findings)


def test_equal_layer_quantities_give_no_hint():
    assert pruefe_mengen(_lv(*_slab_layers(140, 140, 140, 140))) == []


def test_different_titles_or_objects_are_not_compared():
    lv = _lv(_pos("01.01", "Voranstrich Bodenplatte", 205, titel=["Haus A"]),
             _pos("02.01", "Schweißbahn Bodenplatte", 100, titel=["Haus B"]),
             _pos("01.02", "Dämmung Decke", 50, titel=["Haus A"]))
    assert pruefe_mengen(lv) == []


def test_incompatible_unknown_or_zero_quantities_are_skipped_safely():
    lv = _lv(_pos("01.01", "Voranstrich Bodenplatte", 205),
             _pos("01.02", "Schweißbahn Bodenplatte", 150, einheit="m"),
             _pos("01.03", "Dämmung Bodenplatte", None),
             _pos("01.04", "PE-Folie Bodenplatte", 0),
             _pos("01.05", "Trennlage Bodenplatte", 20, einheit=None),
             _pos("01.06", "Abdichtung Bodenplatte", 10, typ="bedarf"))
    assert pruefe_mengen(lv) == []
    # zero divisor in a ratio rule
    tables = _lv(_pos("1", "Tisch", 0, einheit="St", titel=["Saal"]),
                 _pos("2", "Stühle", 400, einheit="St", titel=["Saal"]))
    assert pruefe_mengen(tables, ratio_rules=(CHAIRS_PER_TABLE,)) == []


def test_chairs_tables_ratio_only_when_explicitly_configured():
    lv = _lv(_pos("1", "Tisch", 50, einheit="St", titel=["Saal"]),
             _pos("2", "Stühle", 400, einheit="St", titel=["Saal"]))
    assert pruefe_mengen(lv) == []  # not a default rule
    [finding] = pruefe_mengen(lv, ratio_rules=(CHAIRS_PER_TABLE,))
    assert finding.oz == "2" and finding.regel_id == "MENGE_VERHAELTNIS"
    assert "OZ 2 400 St to OZ 1 50 St yields 8 St/St" in finding.begruendung
    assert "expected 4–6" in finding.begruendung and "keine Baunorm" in finding.begruendung
    ok = _lv(_pos("1", "Tisch", 80, einheit="St", titel=["Saal"]),
             _pos("2", "Stühle", 400, einheit="St", titel=["Saal"]))
    assert pruefe_mengen(ok, ratio_rules=(CHAIRS_PER_TABLE,)) == []


def test_concrete_reinforcement_within_delimited_title_with_unit_conversion():
    title = ["Rohbau", "Bodenplatte"]
    high = _lv(_pos("03.01", "Beton C25/30 Bodenplatte", 20, einheit="m³", titel=title),
               _pos("03.02", "Bewehrung BSt 500", 5, einheit="t", titel=title))
    [finding] = pruefe_mengen(high)
    assert finding.oz == "03.02"
    assert "5000 kg" in finding.begruendung and "250 kg/m³" in finding.begruendung
    assert "not a normative limit" in finding.begruendung
    plausible = _lv(_pos("03.01", "Beton C25/30 Bodenplatte", 20, einheit="m³", titel=title),
                    _pos("03.02", "Bewehrung BSt 500", 2, einheit="t", titel=title))
    assert pruefe_mengen(plausible) == []


def test_concrete_reinforcement_not_compared_across_titles_or_when_ambiguous():
    split = _lv(_pos("03.01", "Beton Bodenplatte", 20, einheit="m³", titel=["Bodenplatte"]),
                _pos("04.01", "Bewehrung Decke", 5000, einheit="kg", titel=["Decke"]))
    assert pruefe_mengen(split) == []
    ambiguous = _lv(_pos("03.01", "Beton Bodenplatte", 20, einheit="m³", titel=["Rohbau"]),
                    _pos("03.02", "Beton Decke", 10, einheit="m³", titel=["Rohbau"]),
                    _pos("03.03", "Bewehrung", 9000, einheit="kg", titel=["Rohbau"]))
    assert pruefe_mengen(ambiguous) == []


# Synthetic layer items whose component is named only in the long text, split over trade sections.
SEALING, INSULATION = ["Rohbau", "Abdichtungsarbeiten"], ["Rohbau", "Dämmarbeiten"]


def _longtext_layers(*mengen):
    specs = (("A.01", "Voranstrich", "Kaltbitumen für Stahlbetonbodenplatte", SEALING),
             ("A.02", "Schweißbahn", "Abdichtung der Bodenplatte, vollflächig", SEALING),
             ("B.01", "Dämmung XPS", "Perimeterdämmung unter Bodenplatte", INSULATION),
             ("B.02", "PE-Folie", "Trennlage zwischen Bodenplatte und Dämmung", INSULATION))
    return [_pos(oz, kurz, m, titel=titel, langtext=lang)
            for (oz, kurz, lang, titel), m in zip(specs, mengen)]


def test_component_from_long_text_groups_layers_across_trade_sections():
    lv = _lv(*_longtext_layers(120, 120, 118, 95))
    [finding] = pruefe_mengen(lv)
    assert finding.oz == "B.02" and finding.regel_id == "MENGE_SCHICHTEN_ABWEICHUNG"
    assert finding.quelle == "regel" and finding.euro_wirkung is None
    assert "floor slab" in finding.titel and "median 119 m²" in finding.begruendung
    for oz, menge in (("A.01", 120), ("A.02", 120), ("B.01", 118), ("B.02", 95)):
        assert f"OZ {oz}" in finding.begruendung and f"{menge} m²" in finding.begruendung
    assert "Abdichtungsarbeiten" in finding.begruendung and "Dämmarbeiten" in finding.begruendung


def test_component_from_long_text_with_consistent_areas_gives_no_hint():
    assert pruefe_mengen(_lv(*_longtext_layers(120, 120, 118, 121))) == []


def test_long_text_reference_on_other_unit_is_not_grouped():
    reference = _pos("A.03", "Abdichtung Wandsockel", 30, einheit="m", titel=SEALING,
                     langtext="Abdichtung Sockel, Anschluss an Bodenplatte")
    [finding] = pruefe_mengen(_lv(*_longtext_layers(120, 120, 118, 95), reference))
    assert finding.oz == "B.02" and "A.03" not in finding.begruendung
    assert "median 119 m²" in finding.begruendung


def test_long_text_connection_reference_does_not_name_the_component():
    reference = _pos("A.03", "Abdichtung Wandsockel", 30, titel=SEALING,
                     langtext="Abdichtung Sockel, Anschluss an die Bodenplatte")
    assert pruefe_mengen(_lv(*_longtext_layers(120, 120, 118, 121), reference)) == []


def test_short_text_component_wins_and_long_text_needs_word_boundary():
    wall = _pos("A.04", "Abdichtung Kellerwand", 30, titel=SEALING,
                langtext="Abdichtung Kellerwand bis Oberkante Bodenplatte")
    smeared = [_pos(f"A.0{5 + i}", "Abdichtung Schacht", m, titel=SEALING,
                    langtext="Bitumenmasse volldeckend auftragen") for i, m in enumerate((2, 40))]
    assert pruefe_mengen(_lv(*_longtext_layers(120, 120, 118, 121), wall, *smeared)) == []


def test_http_report_shows_rule_source_and_concrete_oz():
    body = TestClient(main.app).post("/api/lv/pruefen", json=ACCEPTANCE_LV.model_dump()).json()
    hints = [f for f in body["findings"] if f["regel_id"] == "MENGE_SCHICHTEN_ABWEICHUNG"]
    assert {f["oz"] for f in hints} == {"01.01", "01.03"}
    assert all(f["quelle"] == "regel" and f["euro_wirkung"] is None for f in hints)


def _small(*mengen, titel=SLAB, names=None):
    names = names or ("Dämmung 120 mm", "Dämmung 80 mm", "Dämmung 100 mm", "Dämmung 60 mm")
    return [_pos(f"05.{i + 1:02d}", n, m, titel=titel) for i, (n, m) in enumerate(zip(names, mengen))]


def test_tiny_layer_without_component_is_flagged_against_sibling_median():
    [finding] = pruefe_mengen(_lv(*_small(1, 35, 45, 120)))
    assert finding.oz == "05.01" and finding.regel_id == "MENGE_SCHICHTEN_ABWEICHUNG"
    assert finding.titel == "Implausibly small layer area" and finding.quelle == "regel"
    assert "median 45 m²" in finding.begruendung
    assert all(f"OZ 05.0{i}" in finding.begruendung for i in (2, 3, 4))
    assert "tolerance factor 20; not a standard" in finding.begruendung


def test_small_layer_needs_factor_20_and_layer_terms():
    assert pruefe_mengen(_lv(*_small(10, 35, 45, 120))) == []
    lv = _lv(*_small(35, 45, 120), _pos("05.09", "Fundament", 1))
    assert pruefe_mengen(lv) == []


def test_small_layer_needs_three_layers_and_is_not_reported_twice():
    assert pruefe_mengen(_lv(*_small(1, 120, 130)[:2])) == []
    lv = _lv(*_slab_layers(205, 150, 120, 1))  # component named: only the component grouping reports
    findings = [f for f in pruefe_mengen(lv) if f.oz == "01.04"]
    assert len(findings) == 1 and findings[0].titel.startswith("Unusual layer area")


def _wlg(*groups, titel=SLAB):
    return [_pos(f"06.{i + 1:02d}", f"Dämmung WLG {g}", 50, titel=titel) for i, g in enumerate(groups)]


def test_minority_thermal_conductivity_group_is_flagged():
    findings = [f for f in pruefe_mengen(_lv(*_wlg("035", "035", "035", "040")))
                if f.regel_id == "BEZEICHNUNG_ABWEICHUNG"]
    [finding] = findings
    assert finding.oz == "06.04" and finding.kategorie == "risiko" and finding.schwere == "mittel"
    assert finding.quelle == "regel" and "WLG 035" in finding.begruendung
    assert all(f"OZ 06.0{i}" in finding.begruendung for i in (1, 2, 3))


def test_thermal_conductivity_group_not_flagged_without_clear_minority():
    for groups in (("035", "035", "040", "040"), ("035", "040"), ("035", "035", "040", "045")):
        assert [f for f in pruefe_mengen(_lv(*_wlg(*groups))) if f.regel_id == "BEZEICHNUNG_ABWEICHUNG"] == []
    split = _wlg("035", "035", titel=["Haus A"]) + _wlg("040", titel=["Haus B"])
    assert [f for f in pruefe_mengen(_lv(*split)) if f.regel_id == "BEZEICHNUNG_ABWEICHUNG"] == []


def test_thermal_conductivity_group_from_long_text_when_short_text_names_none():
    lv = _lv(*[_pos(f"07.0{i}", "Dämmung XPS", 50, langtext=f"Wärmedämmung WLG {g}")
               for i, g in enumerate(("032", "032", "032", "035"), start=1)])
    [finding] = [f for f in pruefe_mengen(lv) if f.regel_id == "BEZEICHNUNG_ABWEICHUNG"]
    assert finding.oz == "07.04" and "WLG 032" in finding.begruendung

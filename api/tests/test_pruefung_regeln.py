import json
from pathlib import Path

from app.modelle import LV, Position
from app.pruefung.regeln import pruefe_regeln

ROOT = Path(__file__).resolve().parents[2]


def test_empty_lv_has_no_invented_findings():
    assert pruefe_regeln(LV(name="Leer", quelle="synthetisch")) == []


def test_beispiel_lv_meldet_genau_die_fuenf_erwarteten_regelbefunde():
    lv = LV.model_validate_json((ROOT / "data/beispiel_lv.json").read_bytes())
    erwartung = json.loads((ROOT / "data/beispiel_erwartung.json").read_text())

    befunde = pruefe_regeln(lv)

    gefunden = {(f.oz, f.regel_id) for f in befunde}
    erwartet = {(f["oz"], f["regel_id"]) for f in erwartung["findings"]}
    assert gefunden == erwartet
    # each expected combination exactly once
    assert len(befunde) == len(erwartet)
    for finding in befunde:
        assert finding.quelle == "regel"
        assert finding.regel_id != "MOCK_LLM"
        assert finding.oz in {p.oz for p in lv.positionen}


def test_rechenfehler_an_01_00_0001_nennt_differenz():
    lv = LV.model_validate_json((ROOT / "data/beispiel_lv.json").read_bytes())
    befund = next(f for f in pruefe_regeln(lv) if f.regel_id == "RECHENFEHLER")
    assert befund.oz == "01.00.0001"
    assert befund.euro_wirkung == 779.0


def test_rechenfehler_sauberer_kontrollfall_bei_korrektem_gp():
    lv = LV(name="Test", quelle="synthetisch", positionen=[
        Position(oz="01", menge=10.0, einheit="m³", ep=20.0, gp=200.0, langtext="x"),
    ])
    assert pruefe_regeln(lv) == []


def test_keine_rechenbefunde_bei_fehlender_menge_oder_preis():
    lv = LV(name="Test", quelle="synthetisch", positionen=[
        Position(oz="01", menge=None, einheit="m³", ep=20.0, gp=200.0, langtext="x"),
        Position(oz="02", menge=10.0, einheit="m³", ep=None, gp=200.0, langtext="x"),
        Position(oz="03", menge=10.0, einheit="m³", ep=20.0, gp=None, langtext="x"),
    ])
    befunde = pruefe_regeln(lv)
    assert all(f.regel_id != "RECHENFEHLER" for f in befunde)
    assert {f.regel_id for f in befunde if f.oz == "01"} == {"MENGE_FEHLT"}


def test_null_menge_wird_nicht_als_menge_fehlt_gemeldet():
    lv = LV(name="Test", quelle="synthetisch", positionen=[
        Position(oz="01", menge=0.0, einheit="m³", ep=20.0, gp=0.0, langtext="x"),
    ])
    assert pruefe_regeln(lv) == []


def test_titelsumme_falsch_und_sauberer_kontrollfall():
    gemeinsame_positionen = [
        Position(oz="01", menge=10.0, einheit="m³", ep=20.0, gp=200.0, langtext="x", titel_pfad=["T"]),
        Position(oz="02", menge=5.0, einheit="m³", ep=20.0, gp=100.0, langtext="x", titel_pfad=["T"]),
    ]
    falsch = LV(name="Test", quelle="synthetisch", positionen=gemeinsame_positionen, summen={"T": 999.0})
    befund = next(f for f in pruefe_regeln(falsch) if f.regel_id == "TITELSUMME_FALSCH")
    assert befund.oz == "01"

    korrekt = LV(name="Test", quelle="synthetisch", positionen=gemeinsame_positionen, summen={"T": 300.0})
    assert all(f.regel_id != "TITELSUMME_FALSCH" for f in pruefe_regeln(korrekt))


def test_titelsumme_ohne_vollstaendige_preise_wird_nicht_erfunden():
    lv = LV(name="Test", quelle="synthetisch", positionen=[
        Position(oz="01", menge=10.0, einheit="m³", ep=20.0, gp=200.0, langtext="x", titel_pfad=["T"]),
        Position(oz="02", menge=None, einheit="m³", ep=None, gp=None, langtext="x", titel_pfad=["T"]),
    ], summen={"T": 200.0})
    assert all(f.regel_id != "TITELSUMME_FALSCH" for f in pruefe_regeln(lv))


def test_text_widerspruch_zwischen_kurztext_und_langtext():
    lv = LV(name="Test", quelle="synthetisch", positionen=[
        Position(oz="01", kurztext="Beton 10 m³ einbauen", langtext="Es werden 15 m³ Beton eingebaut."),
    ])
    befund = next(f for f in pruefe_regeln(lv) if f.regel_id == "TEXT_WIDERSPRUCH")
    assert befund.oz == "01"


def test_text_widerspruch_sauberer_kontrollfall_bei_uebereinstimmung():
    lv = LV(name="Test", quelle="synthetisch", positionen=[
        Position(oz="01", kurztext="Beton 10 m³ einbauen", langtext="Es werden 10 m³ Beton eingebaut."),
    ])
    assert all(f.regel_id != "TEXT_WIDERSPRUCH" for f in pruefe_regeln(lv))


def _text_widersprueche(kurztext: str, langtext: str) -> list:
    lv = LV(name="Test", quelle="synthetisch", positionen=[
        Position(oz="01", kurztext=kurztext, langtext=langtext),
    ])
    return [f for f in pruefe_regeln(lv) if f.regel_id == "TEXT_WIDERSPRUCH"]


def test_text_widerspruch_bei_abweichender_betonfestigkeitsklasse():
    befunde = _text_widersprueche("Beton C25/30", "Beton C30/37")
    assert len(befunde) == 1
    befund = befunde[0]
    assert befund.oz == "01"
    assert befund.quelle == "regel"
    assert "C25/30" in befund.begruendung and "C30/37" in befund.begruendung


def test_text_widerspruch_sauberer_kontrollfall_bei_wiederholter_festigkeitsklasse():
    assert _text_widersprueche("Stahlbeton C25/30", "Stahlbeton der Festigkeitsklasse C25/30 herstellen.") == []


def test_text_widerspruch_bei_abweichendem_mass():
    befunde = _text_widersprueche("Wand d = 20 cm", "Wand aus Mauerwerk, d = 24 cm, herstellen.")
    assert len(befunde) == 1
    assert "d = 20 cm" in befunde[0].begruendung and "d = 24 cm" in befunde[0].begruendung


def test_text_widerspruch_gleiches_mass_in_anderer_schreibweise():
    assert _text_widersprueche("Wand d=17,5 cm", "Wand d = 175 mm herstellen.") == []


def test_text_widerspruch_bei_abweichendem_produkttyp_und_stahlsorte():
    befunde = _text_widersprueche("Anker ABCD 3/400-B, Betonstahl BSt 500 M",
                                  "Anker ABCD 2/400-B oder gleichwertig, Betonstahl BSt 500 S liefern.")
    assert len(befunde) == 1
    begruendung = befunde[0].begruendung
    for token in ("ABCD 3/400-B", "ABCD 2/400-B", "BSt 500 M", "BSt 500 S"):
        assert token in begruendung


def test_text_widerspruch_kein_fehlalarm_bei_zusaetzlichen_angaben_im_langtext():
    assert _text_widersprueche(
        "Stahlbeton C25/30",
        "Stahlbeton C25/30, Expositionsklassen XC4, XF1, d = 24 cm, Betonstahl BSt 500 S, "
        "Unterbeton C12/15 nach Wahl.",
    ) == []


def test_text_widerspruch_unterschiedliche_expositionsgruppen_widersprechen_nicht():
    assert _text_widersprueche("Beton XC4", "Beton XF1 herstellen.") == []
    assert len(_text_widersprueche("Beton XC2", "Beton XC4 herstellen.")) == 1


def _einheit_tippfehler(einheiten: list[str]) -> list:
    lv = LV(name="Test", quelle="synthetisch", positionen=[
        Position(oz=f"{i:02d}", einheit=e, langtext="x") for i, e in enumerate(einheiten, 1)])
    return [f for f in pruefe_regeln(lv) if f.regel_id == "EINHEIT_TIPPFEHLER"]


def test_einheit_tippfehler_einheitliche_variante_ist_konvention():
    assert _einheit_tippfehler(["Stk", "Stk", "Stk"]) == []


def test_einheit_tippfehler_gemischte_schreibweisen_melden_die_variante():
    befunde = _einheit_tippfehler(["Stk", "Stk", "St"])
    assert [f.oz for f in befunde] == ["01", "02"]
    assert all(f.id == f"EINHEIT_TIPPFEHLER:{f.oz}" and f.quelle == "regel" for f in befunde)
    assert "“St” (1 item)" in befunde[0].begruendung


def test_einheit_tippfehler_qm_neben_m2():
    befunde = _einheit_tippfehler(["qm", "m²", "m²"])
    assert [f.oz for f in befunde] == ["01"]
    assert "“m²” (2 items)" in befunde[0].begruendung


def test_text_widerspruch_ignoriert_masse_in_fremder_einheit():
    lv = LV(name="Test", quelle="synthetisch", positionen=[
        Position(oz="01", einheit="m²", kurztext="Estrich 5 cm, Feldgröße bis 6 m",
                 langtext="Estrich auf 70 m² herstellen, Randstreifen 2 m")])
    assert all(f.regel_id != "TEXT_WIDERSPRUCH" for f in pruefe_regeln(lv))


def test_text_widerspruch_menge_in_positionseinheit_widerspricht():
    lv = LV(name="Test", quelle="synthetisch", positionen=[
        Position(oz="01", einheit="m³", kurztext="Beton 10 m³", langtext="Einbau von 15 m³ Beton")])
    assert len([f for f in pruefe_regeln(lv) if f.regel_id == "TEXT_WIDERSPRUCH"]) == 1


def test_einheit_tippfehler_sauberer_kontrollfall_bei_korrekter_einheit():
    lv = LV(name="Test", quelle="synthetisch", positionen=[Position(oz="01", einheit="m²", langtext="x")])
    assert all(f.regel_id != "EINHEIT_TIPPFEHLER" for f in pruefe_regeln(lv))


def test_inhalt_duplikat_bei_identischen_positionen_unter_anderer_oz():
    lv = LV(name="Test", quelle="synthetisch", positionen=[
        Position(oz="01", kurztext="Beton", langtext="x", einheit="m³", menge=5.0, ep=100.0, gp=500.0),
        Position(oz="02", kurztext="Beton", langtext="x", einheit="m³", menge=5.0, ep=100.0, gp=500.0),
    ])
    befund = next(f for f in pruefe_regeln(lv) if f.regel_id == "INHALT_DUPLIKAT")
    assert befund.oz == "02"


def test_inhalt_duplikat_sauberer_kontrollfall_bei_unterschiedlichem_inhalt():
    lv = LV(name="Test", quelle="synthetisch", positionen=[
        Position(oz="01", kurztext="Beton", langtext="x", einheit="m³", menge=5.0, ep=100.0, gp=500.0),
        Position(oz="02", kurztext="Mauerwerk", langtext="y", einheit="m²", menge=5.0, ep=50.0, gp=250.0),
    ])
    assert all(f.regel_id != "INHALT_DUPLIKAT" for f in pruefe_regeln(lv))


def test_oz_duplikat_erzeugt_genau_einen_befund_je_oz_nicht_je_position():
    lv = LV(name="Test", quelle="synthetisch", positionen=[
        Position(oz="01", langtext="x", titel_pfad=["A"]),
        Position(oz="01", langtext="x", titel_pfad=["B"]),
        Position(oz="01", langtext="x", titel_pfad=["C"]),
    ])
    duplikate = [f for f in pruefe_regeln(lv) if f.regel_id == "OZ_DUPLIKAT"]
    assert len(duplikate) == 1
    assert duplikate[0].oz == "01"


def test_alle_befunde_haben_echte_oz_stabile_id_und_regelquelle():
    lv = LV.model_validate_json((ROOT / "data/beispiel_lv.json").read_bytes())
    befunde_a = pruefe_regeln(lv)
    befunde_b = pruefe_regeln(lv)
    assert [f.id for f in befunde_a] == [f.id for f in befunde_b]
    assert len({f.id for f in befunde_a}) == len(befunde_a)
    for f in befunde_a:
        assert f.quelle == "regel"
        assert f.oz in {p.oz for p in lv.positionen}


def test_text_widerspruch_erkennt_festigkeitsklasse_mit_leerzeichen():
    befunde = _text_widersprueche("Beton C 25/30", "Beton C30/37")
    assert len(befunde) == 1
    assert "C 25/30" in befunde[0].begruendung and "C30/37" in befunde[0].begruendung  # as written
    assert len(_text_widersprueche("Beton C 25 / 30", "Beton LC 25/28")) == 1


def test_text_widerspruch_gleiche_festigkeitsklasse_mit_und_ohne_leerzeichen():
    assert _text_widersprueche("Beton C 25/30", "Beton C25/30") == []


def _fehlende_werte(quelle):
    lv = LV(name="X", quelle=quelle, positionen=[Position(oz="01", kurztext="A", langtext="B")])
    return {f.regel_id: f for f in pruefe_regeln(lv) if f.regel_id in {"MENGE_FEHLT", "EINHEIT_FEHLT"}}


def test_missing_quantity_and_unit_from_pdf_are_low_parser_gap_findings():
    befunde = _fehlende_werte("Tender.PDF")
    assert {k: f.schwere for k, f in befunde.items()} == {"MENGE_FEHLT": "niedrig", "EINHEIT_FEHLT": "niedrig"}
    assert befunde["MENGE_FEHLT"].id == "MENGE_FEHLT:01"
    assert "original" in befunde["MENGE_FEHLT"].vorschlag and "PDF" in befunde["MENGE_FEHLT"].titel


def test_missing_quantity_and_unit_from_other_sources_keep_severity():
    befunde = _fehlende_werte("tender.x83")
    assert befunde["MENGE_FEHLT"].schwere == "hoch" and befunde["EINHEIT_FEHLT"].schwere == "mittel"
    assert befunde["MENGE_FEHLT"].titel == "Missing quantity"

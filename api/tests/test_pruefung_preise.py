"""B6 (#112): price the original bill from a price list. Offline, synthetic data only."""
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main
from app.modelle import LV, Position, Preisliste, PreislistenEintrag, Pruefbericht
from app.pruefung.preise import AEHNLICHKEIT_MIN, MWST_SATZ, aehnlichkeit, kalkuliere

DATA = Path(__file__).resolve().parents[2] / "data"
client = TestClient(main.app)


def _pos(oz, kurztext, menge, einheit="m²", typ="normal", ep=None, gp=None):
    return Position(oz=oz, kurztext=kurztext, langtext=kurztext, menge=menge, einheit=einheit,
                    typ=typ, ep=ep, gp=gp)


def _e(id_, kurztext, einheit, ep, oz=None):
    return PreislistenEintrag(id=id_, oz=oz, kurztext=kurztext, einheit=einheit, ep=ep, quelle=f"synthetisch:{id_}")


PREISLISTE = Preisliste(id="pl-test", dateiname="synthetisch.csv", eintraege=[
    _e("P1", "Beliebiger Text", "m²", 12.5, oz="01.01"),
    _e("P2", "Bodenplatte Beton C25/30 herstellen", "m³", 110.0),
    _e("P3", "Mauerwerk Innenwand Kalksandstein 17,5 cm d", "m²", 48.0),
    _e("P4", "Schalung Wand", "m²", 30.0),
    _e("P5", "Wasserhaltung vorhalten", "h", 9.99),
    _e("P6", "Zulage Sichtbeton", "m²", 7.5),
])

LV_TEST = LV(name="Synthetisch", quelle="synthetisch", positionen=[
    _pos("01.01", "Oberboden abtragen", 10, ep=11.0, gp=110.0),                     # OZ match
    _pos("01.02", "bodenplatte  BETON C25/30 herstellen", 4, "m3"),                   # text match, unit variant
    _pos("01.03", "Mauerwerk Innenwand Kalksandstein 17,5 cm", 20),                    # similarity match
    _pos("01.04", "Schalung Wand", 5, "m"),                                            # unit mismatch → none
    _pos("01.05", "Schalung Wand", None),                                              # missing quantity
    _pos("01.06", "Wasserhaltung vorhalten", 3, "h", typ="bedarf"),                    # not in the sum
    _pos("01.07", "Wasserhaltung vorhalten", 1.5, "Std", typ="alternativ"),            # not in the sum
    _pos("01.08", "Zulage Sichtbeton", 2, typ="zulage"),                               # follows its quantity
])


def _nach_oz(kalkulation):
    return {p.oz: p for p in kalkulation.positionen}


def test_matching_order_and_entry_ids():
    k = _nach_oz(kalkuliere(LV_TEST, PREISLISTE))
    assert (k["01.01"].treffer, k["01.01"].preis_eintrag) == ("oz", "P1")
    assert (k["01.02"].treffer, k["01.02"].preis_eintrag, k["01.02"].aehnlichkeit) == ("text", "P2", 1.0)
    assert (k["01.03"].treffer, k["01.03"].preis_eintrag) == ("aehnlich", "P3")
    assert AEHNLICHKEIT_MIN <= k["01.03"].aehnlichkeit < 1.0
    assert k["01.08"].treffer == "text"


def test_unit_mismatch_never_matches_even_with_identical_text_or_oz():
    k = _nach_oz(kalkuliere(LV_TEST, PREISLISTE))
    assert k["01.04"].treffer == "kein_treffer"
    assert (k["01.04"].ep, k["01.04"].gp, k["01.04"].preis_eintrag, k["01.04"].aehnlichkeit) == (None, None, None, None)
    lv = LV(name="x", quelle="synthetisch", positionen=[_pos("01.01", "Beliebiger Text", 1, "m³")])
    assert kalkuliere(lv, PREISLISTE).positionen[0].treffer == "kein_treffer"


def test_similarity_below_threshold_does_not_match():
    assert aehnlichkeit("Erdarbeiten Teilfläche 1", "Erdarbeiten Teilfläche 2") < AEHNLICHKEIT_MIN
    lv = LV(name="x", quelle="synthetisch", positionen=[_pos("9", "Schalung Decke", 1)])
    assert kalkuliere(lv, PREISLISTE).positionen[0].treffer == "kein_treffer"


def test_prices_totals_and_bill_values_are_kept():
    k = _nach_oz(kalkuliere(LV_TEST, PREISLISTE))
    p = k["01.01"]
    assert (p.ep, p.gp, p.ep_lv, p.gp_lv) == (12.5, 125.0, 11.0, 110.0)
    assert (p.ep_differenz, p.gp_differenz) == (1.5, 15.0)
    assert k["01.02"].gp == 440.0 and k["01.02"].ep_lv is None and k["01.02"].gp_differenz is None


def test_missing_quantity_has_price_but_no_total_and_makes_the_sum_incomplete():
    k = kalkuliere(LV_TEST, PREISLISTE)
    p = _nach_oz(k)["01.05"]
    assert (p.treffer, p.ep, p.gp) == ("text", 30.0, None)
    assert k.ohne_menge == 1 and k.ohne_preis == 1  # 01.04 has no match
    assert k.vollstaendig is False


def test_bedarf_and_alternativ_are_priced_but_not_summed_zulage_is_summed():
    k = kalkuliere(LV_TEST, PREISLISTE)
    p = _nach_oz(k)
    assert (p["01.06"].gp, p["01.06"].in_summe) == (29.97, False)
    assert (p["01.07"].gp, p["01.07"].in_summe, p["01.07"].treffer) == (14.99, False, "text")
    assert (p["01.08"].gp, p["01.08"].in_summe) == (15.0, True)
    # 125 + 440 + 960 (20 × 48) + 15 (zulage); bedarf/alternativ and unmatched/unknown left out
    assert k.summe_netto == 1540.0


def test_gross_is_net_times_vat_rounded_to_cents():
    k = kalkuliere(LV_TEST, PREISLISTE)
    assert k.mwst_satz == MWST_SATZ == 0.19
    assert k.summe_brutto == float((Decimal(str(k.summe_netto)) * Decimal("1.19")).quantize(Decimal("0.01")))
    assert k.summe_brutto == 1832.6


def test_cents_rounding_half_up():
    lv = LV(name="x", quelle="synthetisch", positionen=[_pos("1", "Wasserhaltung vorhalten", 0.5, "h"),
                                                       _pos("2", "Wasserhaltung vorhalten", 1.005, "h")])
    k = kalkuliere(lv, PREISLISTE)
    assert [p.gp for p in k.positionen] == [5.0, 10.04]  # 4.995 → 5.00, 10.03995 → 10.04
    assert k.summe_netto == 15.04 and k.summe_brutto == 17.9 and k.vollstaendig is True


def test_oz_match_accepts_missing_unit_on_the_bill():
    lv = LV(name="x", quelle="synthetisch", positionen=[_pos("01.01.", "irgendwas", 2, None)])
    p = kalkuliere(lv, PREISLISTE).positionen[0]
    assert (p.treffer, p.gp) == ("oz", 25.0)


def test_synthetic_example_with_a_full_synthetic_price_list_prices_every_item():
    lv = LV.model_validate_json((DATA / "beispiel_lv.json").read_bytes())
    liste = Preisliste(id="pl-beispiel", eintraege=[
        _e(f"E{i}", p.kurztext, p.einheit or "m²", 10.0 + i, oz=p.oz) for i, p in enumerate(lv.positionen)])
    k = kalkuliere(lv, liste)
    assert k.ohne_preis == 0
    assert all(p.treffer == "oz" for p in k.positionen)
    # The example's only gap is its seeded missing quantity (MENGE_FEHLT).
    assert k.ohne_menge == sum(p.menge is None for p in lv.positionen) == 1
    assert k.summe_netto == float(sum(Decimal(str(p.gp)) for p in k.positionen if p.gp is not None))


def test_synthetic_example_with_d4_demo_price_list():
    """Acceptance 2: runs once D4 (#111) provides the demo CSV and its import route."""
    csv = DATA / "preisliste_beispiel.csv"
    if not csv.exists() or not any(getattr(r, "path", "") == "/api/preisliste/import" for r in main.app.routes):
        pytest.skip("D4 (#111) price list import not on this branch yet")
    antwort = client.post("/api/preisliste/import", files={"datei": (csv.name, csv.read_bytes(), "text/csv")})
    assert antwort.status_code == 200, antwort.text
    json_lv = (DATA / "beispiel_lv.json").read_text(encoding="utf-8")
    body = client.post("/api/lv/analyse", content=f'{{"lv": {json_lv}, "preisliste": {antwort.text}}}',
                       headers={"Content-Type": "application/json"}).json()
    k = body["kalkulation"]
    assert k["ohne_preis"] == 0, [p["oz"] for p in k["positionen"] if p["treffer"] == "kein_treffer"]
    assert k["vollstaendig"] == (k["ohne_menge"] == 0)


def test_analyse_route_adds_kalkulation_only_with_a_price_list():
    lv = LV_TEST.model_dump()
    ohne = client.post("/api/lv/analyse", json={"lv": lv, "regelwerk": None})
    assert ohne.status_code == 200 and "kalkulation" not in ohne.json()
    assert ohne.json() == client.post("/api/lv/pruefen", json=lv).json()

    mit = client.post("/api/lv/analyse", json={"lv": lv, "preisliste": PREISLISTE.model_dump()})
    assert mit.status_code == 200
    body = mit.json()
    assert body["kalkulation"]["summe_netto"] == 1540.0
    assert body["kalkulation"]["preisliste_id"] == "pl-test"
    assert {k: body[k] for k in ("lv", "findings", "kennzahlen")} == {k: ohne.json()[k] for k in ("lv", "findings", "kennzahlen")}
    Pruefbericht.model_validate(body)


def test_pruefen_route_is_unchanged():
    body = client.post("/api/lv/pruefen", json=LV_TEST.model_dump()).json()
    assert "kalkulation" not in body and {"lv", "findings", "kennzahlen"} <= set(body)


def test_invalid_price_list_is_rejected_with_422():
    antwort = client.post("/api/lv/analyse", json={"lv": LV_TEST.model_dump(), "preisliste": {"id": "x", "eintraege": [{"id": "a"}]}})
    assert antwort.status_code == 422

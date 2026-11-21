"""B8 (#114): new estimated bill with estimated price and diff to the original. Offline, synthetic only."""
from fastapi.testclient import TestClient

from app import main
from app.modelle import (LV, Anpassung, Finding, Kennzahlen, Position, Preisliste, PreislistenEintrag,
                         Pruefbericht, Zusammenfassung)
from app.pruefung import geschaetztes_lv as modul
from app.pruefung import preise
from app.pruefung.geschaetztes_lv import ergaenze_geschaetztes_lv, geschaetztes_lv
from app.pruefung.preise import kalkuliere

client = TestClient(main.app)
SECTION = ["Synthetic section"]


def _pos(oz, kurztext, menge, einheit="m²", typ="normal"):
    return Position(oz=oz, kurztext=kurztext, langtext=kurztext, menge=menge, einheit=einheit, typ=typ,
                    titel_pfad=SECTION)


def _e(id_, kurztext, einheit, ep):
    return PreislistenEintrag(id=id_, kurztext=kurztext, einheit=einheit, ep=ep, quelle=f"synthetic:{id_}")


PREISLISTE = Preisliste(id="pl-syn", dateiname="synthetic.csv", eintraege=[
    _e("P1", "Synthetic topsoil removal", "m²", 2.0),
    _e("P2", "Synthetic screed layer", "m²", 10.0),
    _e("P3", "Synthetic skirting strip", "m", 5.0),
    _e("P4", "Synthetic edge insulation strip", "m", 4.5),
])

LV_SYN = LV(name="Synthetic", quelle="synthetic", positionen=[
    _pos("01.01", "Synthetic topsoil removal", 100),        # unchanged: 200.00
    _pos("01.02", "Synthetic screed layer", 50),            # updated 50 → 60: 500.00 → 600.00
    _pos("01.03", "Synthetic skirting strip", 10, "m"),     # removed: 50.00 → 0
])


def _menge(oz, alt, neu, bericht="vergleich", freigabe=True):
    return Anpassung(id=f"A:menge:{oz}", oz=oz, art="menge", menge_alt=alt, menge_neu=neu,
                     grund=f"Synthetic quantity change {oz}.", bericht=bericht, freigabe_noetig=freigabe)


def _entfernen(oz, menge):
    return Anpassung(id=f"A:entfernen:{oz}", oz=oz, art="entfernen", menge_alt=menge, menge_neu=0,
                     grund=f"Synthetic duplicate {oz}.", bericht="regelwerk")


def _hinzufuegen(oz, kurztext, menge, einheit="m"):
    return Anpassung(id=f"A:hinzufuegen:{oz}", oz=oz, art="hinzufuegen", menge_neu=menge,
                     position=Position(oz=oz, kurztext=kurztext, menge=menge, einheit=einheit, titel_pfad=SECTION),
                     grund=f"Synthetic missing item {kurztext}.", bericht="regelwerk")


ANPASSUNGEN = [
    _menge("01.02", 50, 60),
    _hinzufuegen("NEU-1", "Synthetic edge insulation strip", 12),  # priced: 12 × 4.50 = 54.00
    _hinzufuegen("NEU-2", "Synthetic unknown special part", 3, "St"),  # no price-list match
    _entfernen("01.03", 10),
]


def _zeilen(g):
    return {z.oz: z for z in g.positionen}


def test_acceptance_one_adjustment_of_each_kind():
    kalkulation = kalkuliere(LV_SYN, PREISLISTE)
    assert kalkulation.summe_netto == 750.0
    g = geschaetztes_lv(LV_SYN, ANPASSUNGEN, PREISLISTE, kalkulation)
    z = _zeilen(g)

    assert len(g.positionen) == len(LV_SYN.positionen) + 2  # original + added, nothing dropped
    assert [r.oz for r in g.positionen] == ["01.01", "01.02", "01.03", "NEU-1", "NEU-2"]
    assert {oz: r.status for oz, r in z.items()} == {
        "01.01": "unchanged", "01.02": "updated", "01.03": "removed", "NEU-1": "added", "NEU-2": "added"}

    assert (z["01.01"].menge_alt, z["01.01"].menge_neu, z["01.01"].gp_alt, z["01.01"].gp_neu) == (100, 100, 200.0, 200.0)
    assert z["01.01"].anpassung_ids == [] and z["01.01"].grund == "" and not z["01.01"].freigabe_noetig

    upd = z["01.02"]
    assert (upd.menge_alt, upd.menge_neu, upd.ep, upd.gp_alt, upd.gp_neu) == (50, 60, 10.0, 500.0, 600.0)
    assert upd.anpassung_ids == ["A:menge:01.02"] and upd.freigabe_noetig  # Report 2 → approval
    assert upd.grund == "Synthetic quantity change 01.02."

    rem = z["01.03"]
    assert (rem.menge_alt, rem.menge_neu, rem.gp_alt, rem.gp_neu) == (10, 0, 50.0, 0.0)
    assert rem.anpassung_ids == ["A:entfernen:01.03"] and not rem.freigabe_noetig

    neu = z["NEU-1"]
    assert (neu.menge_alt, neu.menge_neu, neu.ep, neu.gp_alt, neu.gp_neu) == (None, 12, 4.5, None, 54.0)
    assert neu.kurztext == "Synthetic edge insulation strip" and neu.einheit == "m"

    ohne = z["NEU-2"]
    assert ohne.ep is None and ohne.gp_neu is None and ohne.menge_neu == 3

    assert g.summe_netto == 854.0          # 200 + 600 + 0 + 54; NEU-2 unpriced
    assert g.summe_brutto == 1016.26       # 854 × 1.19
    assert g.differenz_netto == 104.0      # 854 − 750
    assert g.differenz_prozent == 13.87
    assert g.vollstaendig is False and g.ohne_preis == 1
    assert g.anzahl.model_dump() == {"unchanged": 1, "updated": 1, "added": 2, "removed": 1}
    assert g.preisliste_id == "pl-syn" and g.mwst_satz == kalkulation.mwst_satz


def test_all_items_priced_gives_a_complete_sum():
    g = geschaetztes_lv(LV_SYN, ANPASSUNGEN[:2] + ANPASSUNGEN[3:], PREISLISTE)  # kalkulation priced inside
    assert g.vollstaendig is True and g.ohne_preis == 0
    assert (g.summe_netto, g.differenz_netto) == (854.0, 104.0)


def test_original_lv_and_kalkulation_stay_unchanged():
    kalkulation = kalkuliere(LV_SYN, PREISLISTE)
    lv_vorher, k_vorher = LV_SYN.model_dump(), kalkulation.model_dump()
    anpassungen_vorher = [a.model_dump() for a in ANPASSUNGEN]
    geschaetztes_lv(LV_SYN, ANPASSUNGEN, PREISLISTE, kalkulation)
    assert LV_SYN.model_dump() == lv_vorher
    assert kalkulation.model_dump() == k_vorher
    assert [a.model_dump() for a in ANPASSUNGEN] == anpassungen_vorher


def test_without_price_list_quantities_and_statuses_only():
    g = geschaetztes_lv(LV_SYN, ANPASSUNGEN)
    z = _zeilen(g)
    assert [r.status for r in g.positionen] == ["unchanged", "updated", "removed", "added", "added"]
    assert (z["01.02"].menge_alt, z["01.02"].menge_neu) == (50, 60)
    assert z["01.03"].menge_neu == 0 and z["01.03"].gp_neu == 0
    assert all(r.ep is None and r.gp_alt is None for r in g.positionen)
    assert all(r.gp_neu is None for r in g.positionen if r.status != "removed")
    assert (g.summe_netto, g.summe_brutto, g.differenz_netto, g.differenz_prozent) == (None, None, None, None)
    assert g.vollstaendig is False


def test_no_adjustments_gives_an_unchanged_copy_with_zero_difference():
    g = geschaetztes_lv(LV_SYN, [], PREISLISTE)
    assert [r.status for r in g.positionen] == ["unchanged"] * 3
    assert (g.summe_netto, g.differenz_netto, g.differenz_prozent) == (750.0, 0.0, 0.0)


def test_unknown_or_ambiguous_oz_is_ignored_and_removal_wins():
    lv = LV(name="Synthetic", quelle="synthetic", positionen=[
        *LV_SYN.positionen, _pos("02.01", "Synthetic topsoil removal", 5), _pos("02.01", "Synthetic topsoil removal", 7)])
    anpassungen = [_menge("99.99", 1, 2), _menge("02.01", 5, 9), _entfernen("02.01", 5),
                   _menge("01.03", 10, 20, bericht="regelwerk", freigabe=False), _entfernen("01.03", 10)]
    g = geschaetztes_lv(lv, anpassungen, PREISLISTE)
    assert len(g.positionen) == len(lv.positionen)
    assert [r.status for r in g.positionen] == ["unchanged", "unchanged", "removed", "unchanged", "unchanged"]
    assert g.positionen[2].anpassung_ids == ["A:entfernen:01.03"]


def test_quantity_change_to_the_same_value_stays_unchanged():
    g = geschaetztes_lv(LV_SYN, [_menge("01.02", 50, 50.0)], PREISLISTE)
    assert g.positionen[1].status == "unchanged" and g.positionen[1].anpassung_ids == []


def test_report_3_adjustment_needs_approval_even_without_the_flag():
    g = geschaetztes_lv(LV_SYN, [_menge("01.02", 50, 55, bericht="was_wenn", freigabe=False)], PREISLISTE)
    assert g.positionen[1].freigabe_noetig is True
    g = geschaetztes_lv(LV_SYN, [_menge("01.02", 50, 55, bericht="regelwerk", freigabe=False)], PREISLISTE)
    assert g.positionen[1].freigabe_noetig is False


def test_bedarf_item_is_priced_but_not_summed_on_either_side():
    lv = LV(name="Synthetic", quelle="synthetic", positionen=[
        *LV_SYN.positionen, _pos("01.04", "Synthetic screed layer", 8, typ="bedarf")])
    g = geschaetztes_lv(lv, [_menge("01.04", 8, 20)], PREISLISTE)
    zeile = g.positionen[3]
    assert zeile.status == "updated" and zeile.gp_neu == 200.0 and zeile.in_summe is False
    assert (g.summe_netto, g.differenz_netto) == (750.0, 0.0)


def _bericht(**extra):
    return Pruefbericht(lv=LV_SYN, findings=[], kennzahlen=Kennzahlen(positionen=3, findings=0, kritisch=0),
                        zusammenfassung=Zusammenfassung(score=10, schaetzung_abweichung_eur=12.0, grosse_probleme=0,
                                                        warnungen=0, hinweise=0, empfehlungen=0), **extra)


def test_ergaenze_feeds_the_difference_into_the_estimate_tile_and_keeps_given_adjustments():
    bericht = _bericht(kalkulation=kalkuliere(LV_SYN, PREISLISTE), anpassungen=ANPASSUNGEN)
    neu = ergaenze_geschaetztes_lv(bericht, PREISLISTE)
    assert neu.anpassungen == ANPASSUNGEN
    assert neu.geschaetztes_lv.differenz_netto == 104.0
    assert neu.zusammenfassung.schaetzung_abweichung_eur == 104.0
    assert bericht.zusammenfassung.schaetzung_abweichung_eur == 12.0 and bericht.geschaetztes_lv is None
    assert (neu.lv, neu.kalkulation, neu.findings) == (bericht.lv, bericht.kalkulation, bericht.findings)


def test_ergaenze_without_price_list_keeps_the_estimate_tile():
    neu = ergaenze_geschaetztes_lv(_bericht(anpassungen=ANPASSUNGEN), None)
    assert neu.geschaetztes_lv.summe_netto is None
    assert neu.zusammenfassung.schaetzung_abweichung_eur == 12.0


def test_ergaenze_returns_the_report_unchanged_on_failure(monkeypatch):
    def kaputt(*_args, **_kwargs):
        raise RuntimeError("synthetic failure")
    monkeypatch.setattr(modul, "geschaetztes_lv", kaputt)
    bericht = _bericht(anpassungen=ANPASSUNGEN)
    assert ergaenze_geschaetztes_lv(bericht, PREISLISTE) is bericht


def test_ergaenze_derives_b7_adjustments_from_the_findings():
    lv = LV(name="Synthetic", quelle="synthetic", positionen=[*LV_SYN.positionen, _pos("01.05", "Synthetic screed layer", 50)])
    dup = Finding(id="F-dup", oz="01.05", kategorie="fehler", schwere="mittel", titel="Duplicate",
                  begruendung="Synthetic.", vorschlag="Remove.", quelle="regel", regel_id="INHALT_DUPLIKAT")
    bericht = Pruefbericht(lv=lv, findings=[dup], kennzahlen=Kennzahlen(positionen=4, findings=1, kritisch=0),
                           kalkulation=kalkuliere(lv, PREISLISTE))
    neu = ergaenze_geschaetztes_lv(bericht, PREISLISTE)
    assert [a.art for a in neu.anpassungen] == ["entfernen"]
    assert [r.status for r in neu.geschaetztes_lv.positionen] == ["unchanged", "unchanged", "unchanged", "removed"]
    assert neu.geschaetztes_lv.differenz_netto == -500.0


def test_analyse_route_adds_the_estimated_bill_only_with_a_price_list():
    lv = LV_SYN.model_dump()
    ohne = client.post("/api/lv/analyse", json={"lv": lv, "regelwerk": None}).json()
    assert "geschaetztes_lv" not in ohne and ohne == client.post("/api/lv/pruefen", json=lv).json()

    antwort = client.post("/api/lv/analyse", json={"lv": lv, "preisliste": PREISLISTE.model_dump()})
    assert antwort.status_code == 200, antwort.text
    body = antwort.json()
    g = body["geschaetztes_lv"]
    assert [r["oz"] for r in g["positionen"]][:3] == [p["oz"] for p in lv["positionen"]]
    assert len(g["positionen"]) == len(lv["positionen"]) + g["anzahl"]["added"]
    assert g["differenz_netto"] == round(g["summe_netto"] - body["kalkulation"]["summe_netto"], 2)
    assert body["zusammenfassung"]["schaetzung_abweichung_eur"] == g["differenz_netto"]
    assert isinstance(body["anpassungen"], list)
    assert body["lv"] == lv and body["kalkulation"]["summe_netto"] == 750.0
    Pruefbericht.model_validate(body)


PREIS_DB = Preisliste(id=preise.PREIS_DB_ID, eintraege=[_e("D1", "Synthetic unknown special part", "St", 20.0)])


def test_added_item_without_upload_match_is_priced_from_the_price_database(monkeypatch):
    monkeypatch.setattr(preise, "preis_service", lambda: PREIS_DB)
    g = geschaetztes_lv(LV_SYN, ANPASSUNGEN, PREISLISTE)
    zeile = _zeilen(g)["NEU-2"]
    assert (zeile.ep, zeile.gp_neu) == (20.0, 60.0)
    assert g.vollstaendig is True and (g.summe_netto, g.differenz_netto) == (914.0, 164.0)


def test_unreachable_price_database_leaves_the_added_item_unpriced(monkeypatch):
    def weg():
        raise ConnectionError("synthetic outage")
    monkeypatch.setattr(preise, "preis_service", weg)
    g = geschaetztes_lv(LV_SYN, ANPASSUNGEN, PREISLISTE)
    assert _zeilen(g)["NEU-2"].ep is None and g.vollstaendig is False and g.summe_netto == 854.0


def test_analyse_route_with_only_the_price_database_adds_the_estimated_bill(monkeypatch):
    db = Preisliste(id=preise.PREIS_DB_ID, eintraege=PREISLISTE.eintraege)
    monkeypatch.setattr(preise, "preis_service", lambda: db)
    body = client.post("/api/lv/analyse", json={"lv": LV_SYN.model_dump()}).json()
    assert body["kalkulation"]["preisliste_id"] == preise.PREIS_DB_ID
    assert body["geschaetztes_lv"]["summe_netto"] == 750.0
    assert body["geschaetztes_lv"]["preisliste_id"] == preise.PREIS_DB_ID

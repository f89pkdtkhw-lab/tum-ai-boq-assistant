"""Structured adjustments (B7, issue #113): offline, synthetic fixtures only, no dataset text."""
import dataclasses

from fastapi.testclient import TestClient

from app import main
from app.ai.step_api import Note
from app.modelle import Finding, Kennzahlen, LV, Position, Pruefbericht
from app.pruefung import normen
from app.pruefung.anpassungen import FehlendePosition, anpassungen_ableiten
from app.pruefung.mengen import erwartete_schichtmengen, pruefe_mengen
from app.pruefung.normen import fehlende_positionen, pruefe_pflichtpositionen
from app.pruefung.regeln import pruefe_regeln

SLAB = ["Synthetic shell", "Bodenplatte"]
QUELLE = {"url": "https://example.org/synthetic-regulation", "abgerufen": "2026-11-21"}
PFLICHT = {
    "id": "SYNTH-P1", "gewerk": "synthetic floor slab", "gewerk_merkmale": ["Bodenplatte"],
    "position": "synthetic blinding layer", "merkmale": ["Sauberkeitsschicht"],
    "fundstelle": "synthetic test value", "quelle": QUELLE, "faktor": 1.0, "einheit": "m²",
}
EXTRA = {
    "id": "SYNTH-E1", "gewerk": "synthetic floor slab", "gewerk_merkmale": ["Bodenplatte"],
    "position": "synthetic formwork cleaning", "merkmale": ["Schalung reinigen"],
    "fundstelle": "synthetic test value", "quelle": QUELLE,
}


def _register(pflicht=(PFLICHT,), extra=(EXTRA,)) -> normen.Register:
    """The repository register with synthetic required / not-required items on one valid entry."""
    basis = normen.lade_register()
    ziel = next(e for e in basis.eintraege if e.status == "gueltig")
    return normen.Register(stand=basis.stand, eintraege=[
        dataclasses.replace(
            e, geprueft=True,
            pflichtpositionen=tuple(normen._pruefe_pflichtposition(p, "test", "pflichtpositionen") for p in pflicht),
            nicht_erforderlich=tuple(normen._pruefe_pflichtposition(x, "test", "nicht_erforderlich") for x in extra),
        ) if e is ziel else e
        for e in basis.eintraege
    ])


def _pos(oz, kurztext, menge, einheit="m²", titel=SLAB, langtext=None, typ="normal"):
    return Position(oz=oz, kurztext=kurztext, langtext=kurztext if langtext is None else langtext,
                    menge=menge, einheit=einheit, titel_pfad=list(titel), typ=typ)


def _lv(*positionen):
    return LV(name="Synthetic B7 LV", quelle="test", positionen=list(positionen))


ACCEPTANCE_LV = _lv(
    _pos("01.01", "Voranstrich Bodenplatte", 205),       # +39 % vs median 147.5 m² → quantity finding
    _pos("01.02", "Schweißbahn Bodenplatte", 145),
    _pos("01.03", "Dämmung Bodenplatte", 140),
    _pos("01.04", "PE-Folie Bodenplatte", 150),
    _pos("01.05", "Randschalung Bodenplatte", 40, einheit="m"),
    _pos("01.06", "Randschalung Bodenplatte", 40, einheit="m"),  # duplicate of 01.05 → removal
    _pos("01.07", "Schalung reinigen Bodenplatte", 1, einheit="St"),  # NORM_EXTRA notice
)


def _findings(lv=ACCEPTANCE_LV, register=None):
    register = register or _register()
    return pruefe_regeln(lv) + pruefe_mengen(lv) + pruefe_pflichtpositionen(lv, register)


def _ableiten(lv=ACCEPTANCE_LV, **kwargs):
    register = _register()
    return anpassungen_ableiten(lv, _findings(lv, register), fehlende=fehlende_positionen(lv, register), **kwargs)


def _note(step, oz, base, estimated, unit="m²", id_=None):
    return Note(id=id_ or f"{'Note3' if step == 'historical_adjustment' else 'Note4'}:{oz}", step=step, oz=oz,
                source="rule", placeholder=False, text="Synthetic note.", base_value=base,
                estimated_value=estimated, unit=unit, case_ids=["SYN-1"], case_count=1)


def test_acceptance_quantity_missing_item_and_duplicate_give_three_adjustments():
    findings = _findings()
    regeln = {f.regel_id for f in findings}
    assert {"MENGE_SCHICHTEN_ABWEICHUNG", "NORM_POSITION_FEHLT", "INHALT_DUPLIKAT", "NORM_EXTRA"} <= regeln

    menge, neu, weg = _ableiten()  # exactly three adjustments, in this order
    assert (menge.art, menge.oz, menge.menge_alt, menge.menge_neu) == ("menge", "01.01", 205, 147.5)
    assert menge.finding_id == "MENGE_SCHICHTEN_ABWEICHUNG:01.01" and menge.bericht == "regelwerk"
    assert menge.freigabe_noetig is True and "not a standard" in menge.grund

    assert (neu.art, neu.oz, neu.menge_alt, neu.menge_neu) == ("hinzufuegen", "NEU-1", None, 640)
    assert neu.finding_id == "NORM_POSITION_FEHLT:01.01" and neu.bericht == "regelwerk"
    assert (neu.position.oz, neu.position.kurztext, neu.position.einheit, neu.position.menge,
            neu.position.titel_pfad) == ("NEU-1", "synthetic blinding layer", "m²", 640, SLAB)

    assert (weg.art, weg.oz, weg.menge_alt, weg.menge_neu) == ("entfernen", "01.06", 40, 0)
    assert weg.finding_id == "INHALT_DUPLIKAT:01.06" and "OZ 01.05 is kept" in weg.grund

    ids = {f.id for f in findings}
    assert all(a.finding_id in ids for a in (menge, neu, weg))
    assert len({a.id for a in (menge, neu, weg)}) == 3


def test_norm_extra_never_removes_an_item():
    lv = _lv(_pos("02.01", "Bodenplatte C25/30", 100), _pos("02.02", "Schalung reinigen Bodenplatte", 1, "St"),
             _pos("02.03", "Sauberkeitsschicht Bodenplatte", 100))
    register = _register()
    findings = pruefe_pflichtpositionen(lv, register)
    assert [f.regel_id for f in findings] == ["NORM_EXTRA"]
    assert anpassungen_ableiten(lv, findings, fehlende=fehlende_positionen(lv, register)) == []


def test_text_only_findings_give_no_adjustment():
    text_only = Finding(id="TEXT_WIDERSPRUCH:01.02", oz="01.02", kategorie="fehler", schwere="mittel",
                        titel="Short description contradicts detailed description", begruendung="Synthetic.",
                        vorschlag="Align the texts.", quelle="regel", regel_id="TEXT_WIDERSPRUCH")
    modell = text_only.model_copy(update={"id": "LLM:01.03", "oz": "01.03", "quelle": "modell", "regel_id": "LLM"})
    assert anpassungen_ableiten(ACCEPTANCE_LV, [text_only, modell]) == []


def test_missing_item_without_quantity_stays_a_hint():
    ohne = {k: v for k, v in PFLICHT.items() if k not in ("faktor", "einheit")}
    register = _register(pflicht=(ohne,), extra=())
    lv = _lv(_pos("03.01", "Bodenplatte", 100))
    findings = pruefe_pflichtpositionen(lv, register)
    assert [f.regel_id for f in findings] == ["NORM_POSITION_FEHLT"]
    assert fehlende_positionen(lv, register) == {}
    assert anpassungen_ableiten(lv, findings, fehlende=fehlende_positionen(lv, register)) == []


def test_structured_missing_item_must_match_the_finding():
    lv = _lv(_pos("03.01", "Bodenplatte", 100))
    [finding] = pruefe_pflichtpositionen(lv, _register(extra=()))
    falsch = {finding.id: FehlendePosition(kurztext="other item", einheit="m²", menge=5)}
    richtig = {finding.id: FehlendePosition(kurztext="synthetic blinding layer", einheit="m²", menge=5)}
    assert anpassungen_ableiten(lv, [finding], fehlende=falsch) == []
    [a] = anpassungen_ableiten(lv, [finding], fehlende=richtig)
    assert (a.art, a.menge_neu, a.position.titel_pfad) == ("hinzufuegen", 5, [])


def test_duplicate_in_another_section_or_type_is_not_removed():
    lv = _lv(_pos("04.01", "Randschalung", 40, "m", titel=["House A"]),
             _pos("04.02", "Randschalung", 40, "m", titel=["House B"]))
    findings = pruefe_regeln(lv)
    assert "INHALT_DUPLIKAT" in {f.regel_id for f in findings}
    assert anpassungen_ableiten(lv, findings) == []


def test_ambiguous_oz_is_never_adjusted():
    lv = _lv(_pos("05.01", "Voranstrich Bodenplatte", 205), _pos("05.01", "Voranstrich Bodenplatte", 205,
                                                                   titel=["Other"]),
             _pos("05.02", "Schweißbahn Bodenplatte", 145), _pos("05.03", "Dämmung Bodenplatte", 140))
    assert anpassungen_ableiten(lv, pruefe_regeln(lv) + pruefe_mengen(lv)) == []


def test_report_2_too_big_approximation_changes_quantity_with_approval():
    lv = _lv(_pos("06.01", "Synthetic paving", 100), _pos("06.02", "Synthetic kerb", 50, "m"))
    notes = [_note("historical_adjustment", "06.01", 100, 140),           # +40 % → too big
             _note("historical_adjustment", "06.02", 50, 55, unit="m"),   # +10 % → not too big
             _note("historical_adjustment", "06.02", 8, 20, unit="h", id_="Note3:06.02:h")]  # hours, not quantity
    [a] = anpassungen_ableiten(lv, [], notes=notes)
    assert (a.art, a.oz, a.menge_alt, a.menge_neu, a.bericht, a.finding_id, a.freigabe_noetig) == (
        "menge", "06.01", 100, 140, "vergleich", "Note3:06.01", True)


def test_report_3_only_high_chance_recommendation_changes_quantity():
    lv = _lv(_pos("07.01", "Synthetic paving", 100), _pos("07.02", "Synthetic kerb", 50, "m"))
    notes = [_note("what_if", "07.01", 100, 110), _note("what_if", "07.02", 50, 60, unit="m")]
    was_wenn = [{"oz": "07.01", "problem": "synthetic", "chance": "hoch", "empfehlung": "Increase.",
                 "case_ids": ["SYN-1"]},
                {"oz": "07.02", "problem": "synthetic", "chance": "niedrig", "empfehlung": "", "case_ids": []}]
    [a] = anpassungen_ableiten(lv, [], notes=notes, was_wenn=was_wenn)
    assert (a.oz, a.menge_neu, a.bericht, a.finding_id, a.freigabe_noetig) == ("07.01", 110, "was_wenn",
                                                                               "Note4:07.01", True)
    assert anpassungen_ableiten(lv, [], notes=notes) == []  # no what-if list → no chance → no change


def test_one_quantity_change_per_item_and_none_for_removed_items():
    notes = [_note("historical_adjustment", "01.01", 205, 300), _note("what_if", "01.06", 40, 60, unit="m")]
    was_wenn = [{"oz": "01.06", "chance": "hoch"}]
    adjustments = _ableiten(notes=notes, was_wenn=was_wenn)
    assert [(a.art, a.oz, a.bericht) for a in adjustments] == [
        ("menge", "01.01", "regelwerk"), ("hinzufuegen", "NEU-1", "regelwerk"), ("entfernen", "01.06", "regelwerk")]


def test_no_adjustment_invents_a_price():
    adjustments = _ableiten(notes=[_note("historical_adjustment", "01.02", 145, 300)])
    for a in adjustments:
        daten = a.model_dump()
        assert not {"ep", "gp"} & daten.keys()
        if a.position is not None:
            assert a.position.ep is None and a.position.gp is None


def test_existing_findings_are_unchanged():
    findings = _findings()
    vorher = [f.model_copy(deep=True) for f in findings]
    _ableiten()
    assert findings == vorher
    assert set(erwartete_schichtmengen(ACCEPTANCE_LV)) == {
        f.id for f in pruefe_mengen(ACCEPTANCE_LV) if f.regel_id == "MENGE_SCHICHTEN_ABWEICHUNG"}


def test_report_field_is_optional_and_absent_by_default():
    bericht = Pruefbericht(lv=ACCEPTANCE_LV, findings=[], kennzahlen=Kennzahlen(positionen=7, findings=0, kritisch=0))
    assert "anpassungen" not in bericht.model_dump()
    mit = bericht.model_copy(update={"anpassungen": _ableiten()})
    assert [a["art"] for a in Pruefbericht.model_validate(mit.model_dump())
            .model_dump()["anpassungen"]] == ["menge", "hinzufuegen", "entfernen"]
    antwort = TestClient(main.app).post("/api/lv/pruefen", json=ACCEPTANCE_LV.model_dump())
    assert antwort.status_code == 200 and "anpassungen" not in antwort.json()

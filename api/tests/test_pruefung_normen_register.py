"""Norm check (issue #92): withdrawn DIN 18195 parts in the curated register.

Synthetic fixtures only; no dataset text. Offline, no model calls.
"""
from app.modelle import LV, Position
from app.pruefung import normen
from app.pruefung.normen import lade_register, pruefe_normen

ERSATZ = ["DIN 18531", "DIN 18532", "DIN 18533", "DIN 18534", "DIN 18535"]
TEILE = [f"DIN 18195-{n}" for n in range(1, 11)]


def lv_mit(*texte: tuple[str, str]) -> LV:
    return LV(name="Synthetic register LV", quelle="test", positionen=[
        Position(oz=f"01.{i:02d}", kurztext=kurz, langtext=lang, menge=1, einheit="m²")
        for i, (kurz, lang) in enumerate(texte, start=1)
    ])


def ohne_neue_teile(register: normen.Register) -> normen.Register:
    """The register as it was before #92: the same entries minus the new DIN 18195 part entries."""
    eintraege = [e for e in register.eintraege if e.norm_id not in TEILE]
    return normen.Register(stand=register.stand, eintraege=eintraege)


def test_withdrawn_part_18195_4_yields_exactly_one_finding_naming_the_replacements():
    lv = lv_mit(("Abdichtung", "Bodenplatte abdichten nach DIN 18195-4, Schichtenfolge gemäß Plan."))
    findings = [f for f in pruefe_normen(lv) if f.regel_id == "NORM_ZURUECKGEZOGEN"]
    assert len(findings) == 1
    f = findings[0]
    assert f.oz == "01.01" and f.kategorie == "risiko" and f.schwere == "hoch"
    assert "DIN 18195-4" in f.titel
    for ersatz in ERSATZ:
        assert ersatz in f.vorschlag
    assert f.vorschlag.startswith("OZ 01.01:") and f.vorschlag.endswith("Please confirm.")


def test_bare_family_reference_gets_no_new_finding_and_matches_the_old_register():
    lv = lv_mit(("Abdichtung", "Begriffe nach DIN 18195 beachten."))
    register = lade_register()
    mit_neu = [(f.regel_id, f.oz, f.titel) for f in pruefe_normen(lv, register)]
    mit_alt = [(f.regel_id, f.oz, f.titel) for f in pruefe_normen(lv, ohne_neue_teile(register))]
    assert mit_neu == mit_alt
    assert not any(f.regel_id == "NORM_ZURUECKGEZOGEN" for f in pruefe_normen(lv, register))


def test_register_validates_and_part_entries_are_withdrawn_with_replacements():
    register = lade_register()
    for teil in TEILE:
        eintrag = register.suche(teil, "DIN 18195")
        assert eintrag is not None and eintrag.status == "zurueckgezogen"
        assert eintrag.aktuelle_ausgabe is None and eintrag.kalkulationsrelevant is True
        assert eintrag.gewerke == ["Abdichtung"] and eintrag.geprueft is False
        assert eintrag.ersetzt_durch == ERSATZ
        assert eintrag.quelle["url"].startswith("https://") and eintrag.quelle["abgerufen"]
    assert register.suche("DIN 18195-4", "DIN 18195").status == "zurueckgezogen"
    family = register.suche("DIN 18195", "DIN 18195")
    assert family.status == "teilweise_ersetzt" and family.aktuelle_ausgabe == "2025-12"

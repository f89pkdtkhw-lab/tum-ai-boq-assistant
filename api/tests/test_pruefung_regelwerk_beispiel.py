"""Demo regulation document (issue #141): data/regelwerk_beispiel.md feeds check 1 in the U1 upload scene.

Synthetic only: the document and the 2-item LV below are invented for the demo; offline, no key required.
"""
from pathlib import Path

from fastapi.testclient import TestClient

from app import main
from app.modelle import LV, Position, Regelwerk
from app.pruefung.regelwerk import importiere_regelwerk

ROOT = Path(__file__).resolve().parents[2]
DATEI = ROOT / "data" / "regelwerk_beispiel.md"
client = TestClient(main.app)


def regelwerk() -> Regelwerk:
    return importiere_regelwerk("regelwerk_beispiel.md", DATEI.read_bytes())


def mini_lv() -> dict:
    positionen = [
        Position(oz="1", kurztext="Beton C25/30, Expositionsklasse XF1", menge=10, einheit="m3", ep=150, gp=1500),
        Position(oz="2", kurztext="Beton C25/30, Expositionsklasse XC1", menge=5, einheit="m3", ep=150, gp=750),
    ]
    return LV(name="Synthetic demo LV", quelle="test", positionen=positionen).model_dump()


def test_demo_document_yields_the_key_values_without_warnings():
    rw = regelwerk()
    assert rw.warnungen == []
    klassen = {k.bedingung: k.wert for k in rw.kennwerte if k.kennwert == "min_strength_class"}
    assert klassen == {"XF1": "C30/37", "XC1": "C20/25"}
    betondeckung = [k for k in rw.kennwerte if k.kennwert == "Betondeckung c_nom"]
    assert [(k.wert, k.einheit) for k in betondeckung] == [("40", "mm")]


def test_demo_document_first_line_marks_it_as_synthetic():
    erste_zeile = DATEI.read_text(encoding="utf-8").splitlines()[0]
    assert erste_zeile == "Synthetic demo document, not a real standard or client document."


def test_analyse_with_demo_document_gives_both_check_one_findings():
    antwort = client.post("/api/lv/analyse", json={"lv": mini_lv(), "regelwerk": regelwerk().model_dump()})
    assert antwort.status_code == 200, antwort.text
    findings = antwort.json()["findings"]

    abweichung = [f for f in findings if f["regel_id"] == "NORM_KENNWERT_ABWEICHUNG"]
    hoeher = [f for f in findings if f["regel_id"] == "NORM_KENNWERT_HOEHER"]
    assert [(f["oz"], f["schwere"]) for f in abweichung] == [("1", "hoch")]
    assert [(f["oz"], f["schwere"]) for f in hoeher] == [("2", "mittel")]
    # Each finding cites the demo document and the line of its key value (XF1 on line 5, XC1 on line 6).
    assert "regelwerk_beispiel.md, line 5" in abweichung[0]["begruendung"]
    assert "regelwerk_beispiel.md, line 6" in hoeher[0]["begruendung"]

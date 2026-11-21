"""Regulation document import and analysis route (B3, issue #96).

Synthetic regulation texts and LVs only (no dataset content); offline, model mock, no key required.
"""
import importlib.util
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main
from app.modelle import LV, Position, Regelwerk
from app.pruefung import normen
from app.pruefung.regelwerk import importiere_regelwerk

ROOT = Path(__file__).resolve().parents[2]
LLM_KEYS = ("LLM_PROVIDER", "LLM_MODEL", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "AZURE_OPENAI_API_KEY",
            "GEMINI_API_KEY", "OPENAI_BASE_URL", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT")

_spec = importlib.util.spec_from_file_location("pdf_synthetic", Path(__file__).parent / "fixtures/pdf/synthetic.py")
synthetic = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(synthetic)

client = TestClient(main.app)

# Invented regulation text: every value below is synthetic and only exercises the extractor.
REGELWERK_TEXT = """Synthetische Baubeschreibung - Anforderungen Tragwerk (Testtext)

1. Beton nach DIN EN 206 und DIN 1045-2 (2008-08).
Für Bauteile der Expositionsklasse XC4 ist mindestens die Druckfestigkeitsklasse C30/37 zu verwenden.

2. Betondeckung: c_nom mindestens 40 mm.
3. Wärmedämmung nach DIN 4108-2, Wärmeleitfähigkeit höchstens 0,035 W/(mK).
Allgemein gilt: Ausführung nach DIN.
"""


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in LLM_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("NORMPRUEFUNG", raising=False)


def beispiel() -> dict:
    return json.loads((ROOT / "data" / "beispiel_lv.json").read_text(encoding="utf-8"))


def lv_mit_beton(klasse: str = "C25/30", exposition: str = "XC4") -> dict:
    lv = beispiel()
    lv["positionen"].append(Position(
        oz="99.01", kurztext=f"Stahlbeton Bodenplatte {klasse}, {exposition}",
        langtext="Synthetic item: liefern und einbauen.", menge=40, einheit="m3", ep=150, gp=6000,
    ).model_dump())
    return lv


def hochladen(dateiname: str, inhalt: bytes):
    return client.post("/api/regelwerk/import", files={"datei": (dateiname, inhalt)})


def regelwerk_json() -> dict:
    antwort = hochladen("anforderungen.txt", REGELWERK_TEXT.encode("utf-8"))
    assert antwort.status_code == 200, antwort.text
    return antwort.json()


# --- import: references, key values, warnings ------------------------------------------------------

def test_txt_import_extracts_references_and_key_values():
    body = regelwerk_json()
    Regelwerk.model_validate(body)
    assert body["dateiname"] == "anforderungen.txt"
    assert body["id"].startswith("rw-")
    assert [n["norm_id"] for n in body["normverweise"]] == ["DIN EN 206", "DIN 1045-2", "DIN 4108-2"]
    din1045 = body["normverweise"][1]
    assert din1045["ausgabe"] == "2008-08" and din1045["fundstelle"] == "anforderungen.txt, line 3"
    kennwerte = {(k["kennwert"], k["bedingung"]): k for k in body["kennwerte"]}
    beton = kennwerte[("min_strength_class", "XC4")]
    assert beton == {"norm": "DIN 1045-2", "kennwert": "min_strength_class", "wert": "C30/37", "einheit": None,
                     "fundstelle": "anforderungen.txt, line 4", "bedingung": "XC4", "vergleich": "min"}
    deckung = kennwerte[("Betondeckung c_nom", None)]
    assert (deckung["wert"], deckung["einheit"], deckung["vergleich"]) == ("40", "mm", "min")
    waerme = kennwerte[("Wärmeleitfähigkeit", None)]
    assert (waerme["norm"], waerme["wert"], waerme["einheit"], waerme["vergleich"]) == (
        "DIN 4108-2", "0.035", "W/(mK)", "max")
    assert len(body["kennwerte"]) == 3
    assert body["warnungen"] == []


def test_markdown_import_and_several_exposure_classes_per_line():
    text = ("# Synthetische Vorgaben\n\n"
            "| Klasse | Mindestfestigkeit |\n"
            "Nach DIN 1045-2 gilt: XC1 C16/20, XF1 mindestens C25/30\n")
    regelwerk = importiere_regelwerk("vorgaben.md", text.encode("utf-8"))
    paare = [(k.bedingung, k.wert, k.fundstelle) for k in regelwerk.kennwerte]
    assert paare == [("XC1", "C16/20", "vorgaben.md, line 4"), ("XF1", "C25/30", "vorgaben.md, line 4")]
    assert all(k.norm == "DIN 1045-2" for k in regelwerk.kennwerte)


def test_strength_class_without_minimum_wording_is_not_a_key_value():
    regelwerk = importiere_regelwerk("info.txt", "Beispiel nach DIN 1045-2: XC4 und C20/25 im Bestand.".encode())
    assert regelwerk.kennwerte == []
    assert any("No key values" in w for w in regelwerk.warnungen)


def test_text_without_references_or_values_gives_warnings():
    regelwerk = importiere_regelwerk("leer.txt", b"Allgemeine Hinweise ohne Normbezug.")
    assert regelwerk.normverweise == [] and regelwerk.kennwerte == []
    assert len(regelwerk.warnungen) == 2


def test_non_utf8_text_is_read_with_a_warning():
    regelwerk = importiere_regelwerk("alt.txt", "Wärmeleitfähigkeit höchstens 0,04 W/(mK)".encode("cp1252"))
    assert regelwerk.kennwerte[0].kennwert == "Wärmeleitfähigkeit"
    assert any("Windows-1252" in w for w in regelwerk.warnungen)


def test_pdf_import_reads_text_with_page_and_line():
    seite = synthetic.Page()
    seite.text(50, 60, "Synthetische Vorgaben nach DIN 1045-2")
    seite.text(50, 80, "Expositionsklasse XC4: mindestens C30/37")
    antwort = hochladen("vorgaben.pdf", synthetic.build([seite]))
    assert antwort.status_code == 200, antwort.text
    body = antwort.json()
    assert [n["norm_id"] for n in body["normverweise"]] == ["DIN 1045-2"]
    assert body["kennwerte"][0]["wert"] == "C30/37"
    assert body["kennwerte"][0]["fundstelle"] == "vorgaben.pdf, page 1, line 2"


# --- import: errors like /api/lv/import --------------------------------------------------------------

@pytest.mark.parametrize("dateiname, inhalt, status", [
    ("leer.txt", b"", 422),
    ("leer.pdf", b"", 422),
    ("nur_leerzeichen.md", b" \n\n ", 422),
    ("vorgaben.docx", b"secret-document-text", 422),
    ("ohne_endung", b"secret-document-text", 422),
    ("kaputt.pdf", b"%PDF-1.4 secret-document-text", 422),
    ("binaer.txt", b"secret-document-text\x00\x01", 422),
    ("gross.txt", b"x" * (10 * 1024 * 1024 + 1), 413),
])
def test_import_errors(dateiname, inhalt, status):
    antwort = hochladen(dateiname, inhalt)
    assert antwort.status_code == status
    assert isinstance(antwort.json()["detail"], str)
    assert "secret-document-text" not in antwort.text


def test_scanned_pdf_without_text_is_rejected():
    antwort = hochladen("scan.pdf", synthetic.scanned_only())
    assert antwort.status_code == 422
    assert "no extractable text" in antwort.json()["detail"]


# --- /api/lv/analyse ---------------------------------------------------------------------------------

def test_analyse_without_regulation_equals_pruefen():
    lv = beispiel()
    erwartet = client.post("/api/lv/pruefen", json=lv)
    assert erwartet.status_code == 200
    for body in ({"lv": lv, "regelwerk": None}, {"lv": lv}):
        antwort = client.post("/api/lv/analyse", json=body)
        assert antwort.status_code == 200, antwort.text
        assert antwort.json() == erwartet.json()


def test_analyse_with_higher_required_class_adds_the_lower_finding_citing_the_file():
    lv = lv_mit_beton("C25/30", "XC4")
    vorher = client.post("/api/lv/pruefen", json=lv).json()
    assert not any(f["oz"] == "99.01" and f["regel_id"] == "NORM_KENNWERT_ABWEICHUNG" for f in vorher["findings"])

    antwort = client.post("/api/lv/analyse", json={"lv": lv, "regelwerk": regelwerk_json()})
    assert antwort.status_code == 200, antwort.text
    body = antwort.json()
    neu = [f for f in body["findings"] if f["oz"] == "99.01" and f["regel_id"] == "NORM_KENNWERT_ABWEICHUNG"]
    assert len(neu) == 1
    finding = neu[0]
    assert (finding["oz"], finding["schwere"], finding["quelle"], finding["regel_id"]) == (
        "99.01", "hoch", "regel", "NORM_KENNWERT_ABWEICHUNG")
    assert "uploaded regulation document anforderungen.txt" in finding["begruendung"]
    assert "line 4" in finding["begruendung"]
    assert "C30/37" in finding["begruendung"] and "C25/30" in finding["titel"]
    assert finding["euro_wirkung"] is None
    for wort in ("violation", "breach", "non-compliant"):
        assert wort not in json.dumps(finding).lower()
    assert body["findings"][:len(vorher["findings"])] == vorher["findings"]
    assert body["kennzahlen"]["findings"] == len(body["findings"]) == len(vorher["findings"]) + 1
    assert body["lv"] == vorher["lv"]
    # B1 summary counts the upload finding as one more big problem.
    assert body["zusammenfassung"]["grosse_probleme"] == vorher["zusammenfassung"]["grosse_probleme"] + 1


def test_equal_class_gives_no_upload_finding():
    lv = lv_mit_beton("C30/37", "XC4")
    antwort = client.post("/api/lv/analyse", json={"lv": lv, "regelwerk": regelwerk_json()})
    assert not any(f["oz"] == "99.01" and f["regel_id"].startswith("NORM_KENNWERT") for f in antwort.json()["findings"])


def test_higher_class_than_upload_is_a_warning():
    lv = lv_mit_beton("C35/45", "XC4")
    antwort = client.post("/api/lv/analyse", json={"lv": lv, "regelwerk": regelwerk_json()})
    treffer = [f for f in antwort.json()["findings"] if f["oz"] == "99.01" and f["regel_id"] == "NORM_KENNWERT_HOEHER"]
    assert len(treffer) == 1 and treffer[0]["schwere"] == "mittel"
    assert "anforderungen.txt" in treffer[0]["begruendung"]


def test_other_exposure_class_gives_no_upload_finding():
    lv = lv_mit_beton("C20/25", "XC1")
    mit = client.post("/api/lv/analyse", json={"lv": lv, "regelwerk": regelwerk_json()}).json()
    assert mit == client.post("/api/lv/pruefen", json=lv).json()


def test_norm_check_switched_off_ignores_the_upload(monkeypatch):
    monkeypatch.setenv("NORMPRUEFUNG", "off")
    lv = lv_mit_beton("C25/30", "XC4")
    antwort = client.post("/api/lv/analyse", json={"lv": lv, "regelwerk": regelwerk_json()})
    assert antwort.status_code == 200
    assert antwort.json() == client.post("/api/lv/pruefen", json=lv).json()


def test_regulation_maps_to_b2_vorgaben():
    vorgaben = normen.vorgaben_aus_regelwerk(Regelwerk.model_validate(regelwerk_json()))
    assert vorgaben.dateiname == "anforderungen.txt"
    assert [(k.bedingung, k.value) for k in vorgaben.kennwerte] == [("XC4", "C30/37")]


def test_analyse_rejects_an_invalid_regulation():
    assert client.post("/api/lv/analyse", json={"lv": beispiel(), "regelwerk": {"id": "x"}}).status_code == 422

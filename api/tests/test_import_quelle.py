"""#170: every imported item carries its location in the original (PDF page/line/box, Excel sheet/row, GAEB path).

Synthetic fixtures only; the field is optional and additive, so JSON payloads without it stay byte-identical.
"""
import importlib.util
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from fastapi.testclient import TestClient

from app.lv.importer import importiere
from app.main import app
from app.modelle import LV, Position

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pdf_synthetic = _load("pdf_synthetic_quelle", FIXTURES / "pdf/synthetic.py")
excel_synthetic = _load("excel_synthetic_quelle", FIXTURES / "excel/synthetic.py")


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    for key in ("LLM_PROVIDER", "LLM_MODEL", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "AZURE_OPENAI_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "mock")


def test_pdf_items_carry_page_line_and_box_of_their_oz_line():
    lv = importiere("mixed.pdf", pdf_synthetic.mixed_boq())
    orte = {p.oz: p.quelle for p in lv.positionen}
    assert {oz: q.seite for oz, q in orte.items()} == {"1...1": 1, "1...2": 1, "1...3": 1, "2...1": 1, "2...2": 2}
    for quelle in orte.values():
        x0, top, x1, bottom = quelle.bbox
        assert quelle.zeile >= 1 and x0 < x1 and top < bottom
        assert quelle.seite_groesse == (pdf_synthetic.WIDTH, pdf_synthetic.HEIGHT)
    # Reading order: later items on the same page sit on later lines and lower on the page.
    erste = [orte[oz] for oz in ("1...1", "1...2", "1...3", "2...1")]
    assert [q.zeile for q in erste] == sorted(q.zeile for q in erste)
    assert [q.bbox[1] for q in erste] == sorted(q.bbox[1] for q in erste)
    # The box of 1...2 surrounds its embedded sketch, which sits inside the item's text.
    sketch = pdf_synthetic.SKETCH_BBOX
    assert orte["1...2"].bbox[1] <= sketch[1] and orte["1...2"].bbox[3] >= sketch[3]


def test_excel_items_carry_sheet_and_the_row_that_holds_their_oz():
    from app.lv.excel import lese_blaetter
    inhalt = excel_synthetic.beispiel_lv()
    lv = importiere("angebot.xlsx", inhalt)
    zeilen = {(blatt.name, nummer): zellen for blatt in lese_blaetter(inhalt) for nummer, zellen in blatt.zeilen}
    assert lv.positionen
    for position in lv.positionen:
        assert position.quelle.blatt and position.quelle.zeile
        assert position.oz in zeilen[(position.quelle.blatt, position.quelle.zeile)]


def test_excel_model_path_also_carries_the_location():
    """With a key the model reads the sheet (stubbed here, no network); the location still comes from the sheet row."""
    from app.ai import llm
    from app.lv import excel
    gerufen = []

    def modell(prompt, system="", max_tokens=1024):
        gerufen.append(prompt)
        return llm.Answer(json.dumps(excel.mock_antwort(bloecke.pop(0))), "fake", "fake", 0)

    inhalt = excel_synthetic.beispiel_lv()
    bloecke = [block for blatt in excel.lese_blaetter(inhalt) for block in excel._bloecke(blatt)]
    lv = excel.importiere("angebot.xlsx", inhalt, client=modell)
    assert gerufen and all(p.quelle.blatt and p.quelle.zeile for p in lv.positionen)
    assert [p.quelle for p in lv.positionen] == [p.quelle for p in importiere("angebot.xlsx", inhalt).positionen]


def test_gaeb_xml_items_carry_the_element_path_of_their_item():
    inhalt = (FIXTURES / "gaeb/offer.x84").read_bytes()
    lv = importiere("offer.x84", inhalt)
    root = ET.fromstring(inhalt)
    for position in lv.positionen:
        pfad = position.quelle.pfad
        assert pfad.startswith("/GAEB[1]/") and pfad.endswith("]") and "/Item[" in pfad
        element = root
        for schritt in pfad.split("/")[2:]:
            tag, nummer = schritt[:-1].split("[")
            element = [c for c in element if c.tag.rsplit("}", 1)[-1] == tag][int(nummer) - 1]
        assert position.oz.endswith(element.attrib["RNoPart"] + element.attrib.get("RNoIndex", ""))


def test_gaeb_90_items_carry_their_record_line():
    def record(kind, fields):
        line = list(" " * 80)
        line[:2] = kind
        for start, text in fields:
            line[start:start + len(text)] = text
        return "".join(line)
    raw = "\r\n".join([
        record("00", [(10, "83"), (62, "1122PPPPI"), (72, "90")]),
        record("21", [(2, "01010001 "), (11, "NN"), (23, "00000002000"), (34, "m2")]),
        record("25", [(2, "Synthetic wall")]),
        record("99", []),
    ]).encode("cp850")
    lv = importiere("offer.d83", raw)
    assert lv.positionen[0].quelle.model_dump() == {"zeile": 2}


def test_json_without_location_stays_unchanged_and_with_location_round_trips():
    ohne = Position(oz="01.01").model_dump()
    assert "quelle" not in ohne and "quelle" not in json.loads(Position(oz="01.01").model_dump_json())
    beispiel = json.loads((Path(__file__).resolve().parents[2] / "data/beispiel_lv.json").read_text(encoding="utf-8"))
    assert LV.model_validate(beispiel).model_dump(mode="json") == beispiel
    mit = {"oz": "1", "quelle": {"seite": 2, "zeile": 7, "bbox": [1, 2, 3, 4], "seite_groesse": [595, 842]}}
    assert Position.model_validate(mit).model_dump(mode="json")["quelle"] == {
        "seite": 2, "zeile": 7, "bbox": [1.0, 2.0, 3.0, 4.0], "seite_groesse": [595.0, 842.0]}
    with pytest.raises(ValueError):
        Position.model_validate({"oz": "1", "quelle": {"seite": 0}})
    with pytest.raises(ValueError):
        Position.model_validate({"oz": "1", "quelle": {"unbekannt": 1}})


def test_import_route_returns_locations_and_review_accepts_them():
    client = TestClient(app)
    antwort = client.post("/api/lv/import", files={"datei": ("mixed.pdf", pdf_synthetic.mixed_boq())})
    assert antwort.status_code == 200
    lv = antwort.json()
    assert all(p["quelle"]["seite"] >= 1 for p in lv["positionen"])
    bericht = client.post("/api/lv/pruefen", json=lv)
    assert bericht.status_code == 200
    assert bericht.json()["lv"]["positionen"][0]["quelle"] == lv["positionen"][0]["quelle"]

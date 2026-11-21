"""Excel import acceptance (#9): the model reads the sheet (no fixed layout); mock mode stays offline."""
import importlib.util
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.ai import llm
from app.lv import excel
from app.lv.importer import importiere
from app.main import app
from app.modelle import LV

_spec = importlib.util.spec_from_file_location("excel_synthetic", Path(__file__).parent / "fixtures/excel/synthetic.py")
synthetic = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(synthetic)

LLM_KEYS = ("LLM_PROVIDER", "LLM_MODEL", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "AZURE_OPENAI_API_KEY",
            "GEMINI_API_KEY")


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    for key in LLM_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "mock")


class FakeModel:
    """Stands in for llm.complete: records prompts, answers from a function of the prompt."""

    def __init__(self, answer):
        self.answer = answer
        self.prompts = []

    def __call__(self, prompt, system="", max_tokens=1024):
        self.prompts.append(prompt)
        result = self.answer(prompt)
        return llm.Answer(result if isinstance(result, str) else json.dumps(result), "fake", "fake", 0)


# ---------- acceptance in mock/offline mode ----------

def test_acceptance_sheet_imports_three_items_with_original_oz_and_no_invented_numbers():
    lv = importiere("angebot.xlsx", synthetic.beispiel_lv())
    assert [p.oz for p in lv.positionen] == ["01.01", "01.02", "01.02"]  # duplicate OZ preserved
    erste, zweite, dritte = lv.positionen
    assert (erste.menge, erste.einheit, erste.ep, erste.gp, erste.typ) == (1, "psch", 1500, 1500, "pauschal")
    assert (zweite.menge, zweite.ep, zweite.gp) == (2, 12.5, 25.0)  # comma decimals, 2 × 12,50 = 25,00 kept
    assert zweite.kurztext == "Mauerwerk KS 17,5 cm" and zweite.langtext == "Kalksandstein, Mörtelgruppe IIa"
    assert zweite.titel_pfad == ["02 Rohbau", "02.1 Mauerwerk"]
    assert (dritte.menge, dritte.ep, dritte.gp, dritte.typ) == (3.5, None, None, "bedarf")  # unknown price = null
    assert dritte.langtext == "Wie vor, jedoch 24 cm"  # inline string
    assert lv.name == "angebot" and lv.quelle == "angebot.xlsx"


def test_committed_example_file_is_the_synthetic_builder_output():
    datei = Path(__file__).parent / "fixtures/excel/lv_synthetisch.xlsx"
    assert datei.read_bytes() == synthetic.beispiel_lv()


def test_other_column_order_and_headers_need_no_fixed_layout():
    lv = importiere("anders.xlsx", synthetic.anderes_layout())
    assert [(p.oz, p.menge, p.einheit, p.ep, p.gp) for p in lv.positionen] == [
        ("01.0010", 120, "m2", 8.4, 1008.0), ("01.0020", 45.5, "m3", None, None), ("02.0010", 18, "m", 35, 630)]
    assert lv.positionen[0].titel_pfad == ["01 Erdarbeiten"]
    assert lv.positionen[2].titel_pfad == ["02 Entwässerung"]
    assert "99.99" not in [p.oz for p in lv.positionen]  # hidden sheet skipped


def test_formula_without_cached_result_reads_as_empty_and_cached_result_as_value():
    blatt = excel.lese_blaetter(synthetic.beispiel_lv())[0]
    zeilen = dict(blatt.zeilen)
    assert zeilen[6][6] == ""  # =D6*F6, no cached value: never evaluated
    assert zeilen[7][6] == "1525"  # =SUM(...) with cached value
    assert 4 not in zeilen  # empty row removed


def test_missing_oz_column_returns_understandable_error_via_api():
    response = TestClient(app).post("/api/lv/import", files={"datei": ("ohne_oz.xlsx", synthetic.ohne_oz())})
    assert response.status_code == 422
    assert "OZ" in response.json()["detail"] and "no BoQ items" in response.json()["detail"]


@pytest.mark.parametrize("inhalt", [b"abc", b"PK\x03\x04broken"])
def test_not_an_xlsx_returns_understandable_error(inhalt):
    with pytest.raises(ValueError, match="Invalid Excel file"):
        importiere("kaputt.xlsx", inhalt)


def test_xml_with_doctype_is_rejected():
    inhalt = synthetic.xlsx({"LV": [["OZ", "Kurztext"], ["01", "x"]]})
    import io, zipfile
    quelle = zipfile.ZipFile(io.BytesIO(inhalt))
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as ziel:
        for name in quelle.namelist():
            daten = quelle.read(name)
            if name == "xl/sharedStrings.xml":
                daten = daten.replace(b"?>", b'?><!DOCTYPE sst [<!ENTITY x "y">]>', 1)
            ziel.writestr(name, daten)
    with pytest.raises(ValueError, match="DTD"):
        importiere("dtd.xlsx", puffer.getvalue())


def test_api_import_then_pruefen_stays_contract_compliant():
    client = TestClient(app)
    response = client.post("/api/lv/import", files={"datei": ("angebot.xlsx", synthetic.beispiel_lv())})
    assert response.status_code == 200
    lv = LV.model_validate(response.json())
    assert len(lv.positionen) == 3
    bericht = client.post("/api/lv/pruefen", json=response.json())
    assert bericht.status_code == 200
    assert bericht.json()["lv"]["positionen"][1]["gp"] == 25.0


def test_mock_mode_makes_no_model_call(monkeypatch):
    def verboten(*args, **kwargs):
        raise AssertionError("mock mode must not call the model")
    monkeypatch.setattr(llm, "complete", verboten)
    assert len(importiere("angebot.xlsx", synthetic.beispiel_lv()).positionen) == 3


# ---------- model path: prompt, validation, chunking, errors ----------

def test_model_gets_the_sheet_as_csv_and_its_answer_becomes_positions():
    modell = FakeModel(lambda prompt: {"positionen": [
        {"zeile": 3, "oz": "01.01", "kurztext": "Baustelleneinrichtung", "menge": "1", "einheit": "psch",
         "ep": 1500, "gp": "1500", "typ": "pauschal", "titel_pfad": ["01 Baustelle"]},
        {"zeile": 5, "oz": "01.02", "kurztext": "Mauerwerk KS 17,5 cm", "menge": 2, "einheit": "m2",
         "ep": "12,50", "gp": "25,00"},
        {"zeile": 6, "oz": "01.02", "kurztext": "Mauerwerk KS 24 cm", "menge": "3,5", "einheit": "m2",
         "ep": None, "gp": None, "typ": "bedarf"},
    ], "fehler": None})
    lv = excel.importiere("angebot.xlsx", synthetic.beispiel_lv(), client=modell)
    assert len(modell.prompts) == 1
    assert '5;01.02;Mauerwerk KS 17,5 cm;Kalksandstein, Mörtelgruppe IIa;2;m2;12,50;25,00' in modell.prompts[0]
    assert [(p.oz, p.menge, p.ep, p.gp, p.typ) for p in lv.positionen] == [
        ("01.01", 1, 1500, 1500, "pauschal"), ("01.02", 2, 12.5, 25, "normal"), ("01.02", 3.5, None, None, "bedarf")]


def test_invented_items_and_numbers_from_the_model_are_dropped_or_nulled():
    modell = FakeModel(lambda prompt: "```json\n" + json.dumps({"positionen": [
        {"zeile": 5, "oz": "01.02", "menge": 2, "ep": "12,50", "gp": 25},
        # invented quantity, computed GP (3.5 × 12.5) and zero for the unknown price:
        {"zeile": 6, "oz": "01.02", "menge": 7, "ep": 0, "gp": 43.75, "typ": "geheim"},
        {"zeile": 3, "oz": "09.99", "kurztext": "erfunden", "menge": 1},  # OZ not in the sheet
    ]}) + "\n```")
    lv = excel.importiere("angebot.xlsx", synthetic.beispiel_lv(), client=modell)
    assert [p.oz for p in lv.positionen] == ["01.02", "01.02"]
    zweite = lv.positionen[1]
    assert (zweite.menge, zweite.ep, zweite.gp, zweite.typ) == (None, None, None, "normal")


def test_wrong_row_number_is_corrected_by_oz_and_duplicates_use_separate_rows():
    modell = FakeModel(lambda prompt: {"positionen": [
        {"zeile": 99, "oz": "01.02", "menge": 2}, {"oz": "01.02", "menge": "3,5"}]})
    lv = excel.importiere("angebot.xlsx", synthetic.beispiel_lv(), client=modell)
    assert [(p.oz, p.menge) for p in lv.positionen] == [("01.02", 2), ("01.02", 3.5)]


def test_large_sheet_is_sent_in_bounded_blocks_with_repeated_header():
    modell = FakeModel(lambda prompt: {"positionen": [
        {"zeile": int(zeile.split(";")[0]), "oz": zeile.split(";")[1], "menge": zeile.split(";")[3]}
        for zeile in prompt.split("Rows:\n", 1)[1].splitlines() if zeile and not zeile.split(";")[1] == "OZ"]})
    lv = excel.importiere("gross.xlsx", synthetic.gross(130), client=modell)
    assert len(modell.prompts) == 4  # 131 rows / 40 per block
    assert all(len(p) < excel.MAX_ZEICHEN_BLOCK + 2000 for p in modell.prompts)
    assert all("Context" in p and "OZ;Kurztext;Menge" in p for p in modell.prompts[1:])
    assert [p.oz for p in lv.positionen] == [f"01.{i:04d}" for i in range(1, 131)]
    assert lv.positionen[-1].menge == 130


def test_model_without_items_reports_its_reason():
    modell = FakeModel(lambda prompt: {"positionen": [], "fehler": "no item numbers in this block"})
    with pytest.raises(ValueError, match="no BoQ items: no item numbers in this block"):
        excel.importiere("ohne_oz.xlsx", synthetic.ohne_oz(), client=modell)


def test_unreadable_model_answer_is_an_import_error_not_silent_data_loss():
    with pytest.raises(ValueError, match="no readable item list"):
        excel.importiere("angebot.xlsx", synthetic.beispiel_lv(), client=FakeModel(lambda prompt: "Sorry, no."))


def test_model_failure_becomes_understandable_import_error_via_api(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")  # selected provider without a key
    response = TestClient(app).post("/api/lv/import", files={"datei": ("angebot.xlsx", synthetic.beispiel_lv())})
    assert response.status_code == 422
    assert "Excel import via the model failed" in response.json()["detail"]
    assert "ANTHROPIC_API_KEY" in response.json()["detail"]


@pytest.mark.parametrize(("text", "zahl"), [
    ("12,50", 12.5), ("1.234,56", 1234.56), ("1,234.56", 1234.56), ("12.5", 12.5), ("25,00 €", 25.0),
    ("1.008,00", 1008.0), (3, 3.0), ("", None), ("psch", None), (None, None), (True, None)])
def test_number_parsing(text, zahl):
    assert excel.zahl(text) == zahl

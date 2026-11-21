"""#192: AI vision fallback for PDF parser gaps; every value from the model is checked against the page text."""
import importlib.util
import io
import json
import re
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.ai import llm, sprache
from app.lv import pdf, pdf_vision
from app.lv.importer import importiere
from app.main import app

_spec = importlib.util.spec_from_file_location("pdf_synthetic", Path(__file__).parent / "fixtures/pdf/synthetic.py")
synthetic = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(synthetic)


def _menge(page, top, menge, einheit):
    page.text(135, top, f"{menge} {einheit}")
    page.text(431, top, "________")
    page.text(501, top, "____________")


def lv_mit_luecke(seiten=1) -> bytes:
    """Per page: one item the parser reads fully, one whose quantity is only printed in its text (a gap)."""
    pages = []
    for nummer in range(1, seiten + 1):
        page = synthetic.Page()
        page.text(57, 100, f"0{nummer}", bold=True)
        page.text(135, 100, "Rohbau", bold=True)
        page.text(57, 130, f"0{nummer}.0010", bold=True)
        page.text(135, 130, "Mauerwerk 24 cm", bold=True)
        page.text(135, 150, "Kalksandstein liefern und mauern.")
        _menge(page, 175, "12,000", "m2")
        page.text(57, 210, f"0{nummer}.0020", bold=True)
        page.text(135, 210, "Risse schliessen", bold=True)
        page.text(135, 230, "Menge nach Aufmass: 5 Stueck")
        page.text(57, 260, f"0{nummer}.0030", bold=True)
        page.text(135, 260, "Fugen versiegeln", bold=True)
        _menge(page, 285, "40,000", "m")
        pages.append(page)
    return synthetic.build(pages)


def lv_ohne_oz_spalte() -> bytes:
    """Items numbered "Pos. 10": the text parser finds no OZ column and recognizes nothing."""
    page = synthetic.Page()
    page.text(57, 100, "Leistungsverzeichnis Beispiel", bold=True, size=14)
    page.text(57, 140, "Pos. 10 Mauerwerk 24 cm")
    page.text(300, 140, "12,000 m2")
    page.text(57, 170, "Pos. 20 Putz innen")
    page.text(300, 170, "85,500 m2")
    return synthetic.build([page])


@pytest.fixture
def claude(monkeypatch):
    """Claude with a fake key; the provider call is replaced and records prompt, system and images."""
    monkeypatch.setattr(llm, "RUNTIME", {})
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-synthetic-test-key")
    monkeypatch.setattr(httpx, "post", lambda *_, **__: (_ for _ in ()).throw(AssertionError("no real HTTP call")))
    aufrufe, antworten = [], {}

    def fake(prompt, system, chosen, max_tokens, json_mode=False, timeout=None, effort=None, bilder=None):
        aufrufe.append({"prompt": prompt, "system": system, "bilder": bilder})
        seite = int(re.search(r"Image 1 is page (\d+)", prompt).group(1))
        antwort = antworten.get(seite, [])
        if isinstance(antwort, Exception):
            raise antwort
        return json.dumps({"positionen": antwort})
    monkeypatch.setattr(llm, "_anthropic", fake)
    return aufrufe, antworten


def _pos(lv, oz):
    return next(p for p in lv.positionen if p.oz == oz)


def test_gap_is_filled_from_the_page_image_and_marked_as_ai(claude):
    aufrufe, antworten = claude
    antworten[1] = [
        {"oz": "01.0020", "kurztext": "Risse schliessen", "menge": 5, "einheit": "Stueck", "typ": "normal"},
        {"oz": "01.0010", "kurztext": "Mauerwerk 24 cm", "menge": 99, "einheit": "m3"},  # parser values win
        {"oz": "09.9999", "kurztext": "Erfundene Position", "menge": 1, "einheit": "St"},  # not printed
    ]
    vorher = pdf.importiere("lv.pdf", lv_mit_luecke())
    assert _pos(vorher, "01.0020").menge is None  # precondition: the parser leaves a gap

    lv = importiere("lv.pdf", lv_mit_luecke())

    gefuellt = _pos(lv, "01.0020")
    assert (gefuellt.menge, gefuellt.einheit, gefuellt.quelle.ki) == (5.0, "Stueck", True)
    assert gefuellt.quelle.seite == 1
    unveraendert = _pos(lv, "01.0010")
    assert (unveraendert.menge, unveraendert.einheit, unveraendert.quelle.ki) == (12.0, "m2", None)
    assert [p.oz for p in lv.positionen] == [p.oz for p in vorher.positionen]
    assert len(aufrufe) == 1
    assert all(Image.open(io.BytesIO(b)).format == "JPEG" for b in aufrufe[0]["bilder"])


def test_numbers_and_units_that_are_not_printed_are_dropped(claude):
    _, antworten = claude
    antworten[1] = [{"oz": "01.0020", "kurztext": "Risse schliessen", "menge": 7, "einheit": "kg"}]
    lv = importiere("lv.pdf", lv_mit_luecke())
    p = _pos(lv, "01.0020")
    assert (p.menge, p.einheit) == (None, None)
    assert p.quelle.ki is None  # nothing was accepted, so the item is not marked


def test_pdf_without_recognized_items_is_read_entirely_by_the_ai(claude):
    _, antworten = claude
    antworten[1] = [
        {"oz": "10", "kurztext": "Mauerwerk 24 cm", "menge": 12, "einheit": "m2"},
        {"oz": "20", "kurztext": "Putz innen", "menge": 85.5, "einheit": "m2"},
        {"oz": "77", "kurztext": "Erfunden", "menge": 3, "einheit": "St"},
    ]
    with pytest.raises(ValueError, match="No BoQ positions"):
        pdf.importiere("lv.pdf", lv_ohne_oz_spalte())

    antwort = TestClient(app).post("/api/lv/import", files={"datei": ("lv.pdf", lv_ohne_oz_spalte())})

    assert antwort.status_code == 200
    daten = antwort.json()
    assert [(p["oz"], p["menge"], p["einheit"]) for p in daten["positionen"]] == [("10", 12.0, "m2"), ("20", 85.5, "m2")]
    assert all(p["quelle"]["ki"] is True and p["quelle"]["seite"] == 1 for p in daten["positionen"])


def test_mock_mode_makes_no_call_and_keeps_parser_result_and_errors():
    lv = importiere("lv.pdf", lv_mit_luecke())
    assert lv == pdf.importiere("lv.pdf", lv_mit_luecke())
    assert '"ki"' not in lv.model_dump_json()  # parser-only payloads stay byte-identical
    antwort = TestClient(app).post("/api/lv/import", files={"datei": ("lv.pdf", lv_ohne_oz_spalte())})
    assert antwort.status_code == 422
    assert "No BoQ positions" in antwort.json()["detail"]


@pytest.mark.parametrize("schalter", ["off", "aus"])
def test_switch_off_makes_no_call(claude, monkeypatch, schalter):
    aufrufe, _ = claude
    monkeypatch.setenv("PDF_VISION", schalter)
    importiere("lv.pdf", lv_mit_luecke())
    assert aufrufe == []


def test_other_providers_make_no_image_call(monkeypatch):
    monkeypatch.setattr(llm, "RUNTIME", {})
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic")
    monkeypatch.setattr(llm, "_gemini", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no call")))
    assert _pos(importiere("lv.pdf", lv_mit_luecke()), "01.0020").menge is None


def test_model_error_keeps_the_parser_result(claude):
    _, antworten = claude
    antworten[1] = llm.LLMError("anthropic returned HTTP 529.")
    lv = importiere("lv.pdf", lv_mit_luecke())
    assert lv == pdf.importiere("lv.pdf", lv_mit_luecke())


def test_page_limit_brakes_the_cost(claude, monkeypatch):
    aufrufe, _ = claude
    monkeypatch.setenv("PDF_VISION_MAX_SEITEN", "1")
    importiere("lv.pdf", lv_mit_luecke(seiten=3))
    assert len(aufrufe) == 1
    assert len(aufrufe[0]["bilder"]) == 2  # the gap page plus the following page


def test_extraction_is_never_translated_even_when_the_ui_is_german(claude):
    aufrufe, _ = claude
    token = sprache.setze("de")
    try:
        importiere("lv.pdf", lv_mit_luecke())
    finally:
        sprache.zuruecksetzen(token)
    assert aufrufe[0]["system"] == pdf_vision.SYSTEM


def test_complete_with_images_is_claude_only(monkeypatch):
    monkeypatch.setattr(llm, "RUNTIME", {})
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic")
    with pytest.raises(llm.LLMError, match="needs Claude"):
        llm.complete("p", bilder=[b"jpeg"])

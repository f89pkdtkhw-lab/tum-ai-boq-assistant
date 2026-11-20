"""PDF import acceptance (#10): text via word coordinates, textless regions as ordered JPEG crops."""
import importlib.util
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.lv.importer import importiere
from app.lv.pdf import import_with_blocks
from app.main import app

_spec = importlib.util.spec_from_file_location("pdf_synthetic", Path(__file__).parent / "fixtures/pdf/synthetic.py")
synthetic = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(synthetic)

# Test case from the case brief; it stays in this private repository and is read in place.
ROHBAU = Path(__file__).resolve().parents[2] / "data/testfaelle/rohbau_efh/lv_rohbau_efh.pdf"


@pytest.fixture(scope="module")
def mixed():
    return import_with_blocks("mixed.pdf", synthetic.mixed_boq())


def test_text_blocks_and_jpeg_crops_form_one_list_in_exact_reading_order(mixed):
    assert [(b.page, b.kind, b.role, b.oz) for b in mixed.blocks] == [
        (1, "text", "oz", "1"), (1, "text", "title", "1"),
        (1, "text", "note", None), (1, "text", "note", None),
        (1, "text", "oz", "1...1"), (1, "text", "short_text", "1...1"), (1, "text", "long_text", "1...1"),
        (1, "text", "quantity", "1...1"),
        (1, "text", "oz", "1...2"), (1, "text", "short_text", "1...2"), (1, "text", "long_text", "1...2"),
        (1, "image", "image", "1...2"),
        (1, "text", "long_text", "1...2"), (1, "text", "quantity", "1...2"),
        (1, "text", "oz", "1...3"), (1, "text", "short_text", "1...3"), (1, "text", "quantity", "1...3"),
        (1, "text", "total", None),
        (1, "text", "oz", "2"), (1, "text", "title", "2"),
        (1, "text", "oz", "2...1"), (1, "text", "short_text", "2...1"), (1, "text", "marker", "2...1"),
        (1, "text", "long_text", "2...1"),
        (1, "image", "image", "2...1"),
        (1, "text", "long_text", "2...1"),
        (2, "text", "long_text", "2...1"), (2, "text", "quantity", "2...1"),
        (2, "text", "oz", "2...2"), (2, "text", "short_text", "2...2"), (2, "text", "long_text", "2...2"),
        (2, "text", "quantity", "2...2"),
        (2, "text", "total", None), (2, "text", "total", None), (2, "text", "total", None), (2, "text", "total", None),
        (3, "image", "image", None),
    ]
    assert [b.index for b in mixed.blocks] == list(range(len(mixed.blocks)))
    keys = [(b.page, b.bbox[1]) for b in mixed.blocks]
    assert keys == sorted(keys), "blocks must run page by page, top to bottom"
    texts = [b.text for b in mixed.blocks if b.oz == "1...2" and b.kind == "text"]
    assert texts[2:4] == ["Fundament herstellen wie skizziert:", "Maße vor Ort prüfen."]


def test_each_jpeg_crop_keeps_page_bbox_index_and_owning_position(mixed):
    sketch, handwriting, scan = mixed.images
    expected = [(sketch, 1, synthetic.SKETCH_BBOX, "embedded_image", "1...2"),
                (handwriting, 1, synthetic.HANDWRITING_BBOX, "drawing", "2...1"),
                (scan, 3, (0, 0, synthetic.WIDTH, synthetic.HEIGHT), "page", None)]
    for block, page, bbox, source, oz in expected:
        assert (block.page, block.source, block.oz, block.text) == (page, source, oz, "")
        assert block.bbox == pytest.approx(bbox, abs=1.5)
        assert mixed.blocks[block.index] is block
        assert block.jpeg[:3] == b"\xff\xd8\xff"
        image = Image.open(io.BytesIO(block.jpeg))
        assert image.format == "JPEG"
        width, height = block.bbox[2] - block.bbox[0], block.bbox[3] - block.bbox[1]
        assert image.width / image.height == pytest.approx(width / height, rel=0.05)
    # Neighbours prove the crop sits exactly where it was on the page.
    before, after = mixed.blocks[sketch.index - 1], mixed.blocks[sketch.index + 1]
    assert before.bbox[3] <= sketch.bbox[1] and sketch.bbox[3] <= after.bbox[1]
    # The repeated header logo is decoration, not content.
    assert not any(b.bbox[1] < 60 for b in mixed.images if b.page != 3)


def test_positions_keep_original_oz_and_missing_values_faithfully(mixed):
    positions = {p.oz: p for p in mixed.lv.positionen}
    assert list(positions) == ["1...1", "1...2", "1...3", "2...1", "2...2"]
    first = positions["1...1"]
    assert (first.kurztext, first.langtext, first.menge, first.einheit, first.typ) == (
        "Oberboden abtragen", "Oberboden abtragen und seitlich lagern.\nDicke bis 20 cm.", 120, "m²", "normal")
    assert first.titel_pfad == ["1 Erdarbeiten"]
    sketch = positions["1...2"]
    assert (sketch.menge, sketch.einheit) == (7, None)
    assert sketch.langtext == "Fundament herstellen wie skizziert:\n\nMaße vor Ort prüfen."
    empty = positions["1...3"]
    assert (empty.kurztext, empty.langtext, empty.menge, empty.einheit) == ("Prüfprotokoll Erdung", "", None, None)
    stairs = positions["2...1"]
    assert (stairs.menge, stairs.einheit, stairs.typ, stairs.titel_pfad) == (10, "m²", "bedarf", ["2 Betonarbeiten"])
    assert stairs.langtext.endswith("Sichtbetonklasse SB 2.\nAusführung nach Merkblatt.")
    assert (positions["2...2"].menge, positions["2...2"].einheit) == (3350.5, "m³")
    assert all(p.ep is None and p.gp is None for p in positions.values())
    assert mixed.lv.summen == {}


def test_headers_footers_carry_overs_and_summaries_create_no_positions(mixed):
    text = "\n".join(b.text for b in mixed.blocks)
    for header in ("Ingenieurbüro Beispiel", "2026 Beispielprojekt", "Seite:", "Übertrag", "Menge/Einheit"):
        assert header not in text
    for position in mixed.lv.positionen:
        assert "Übertrag" not in position.langtext and "Seite" not in position.langtext
    totals = [b.text for b in mixed.blocks if b.role == "total"]
    assert totals[-2:] == ["1 Erdarbeiten ____________", "2 Betonarbeiten ____________"]
    assert importiere("mixed.pdf", synthetic.mixed_boq()) == mixed.lv


def test_scanned_pdf_is_rejected_understandably_without_ocr():
    with pytest.raises(ValueError, match="no extractable text.*OCR is not supported"):
        importiere("scan.pdf", synthetic.scanned_only())
    response = TestClient(app).post("/api/lv/import", files={"datei": ("scan.pdf", synthetic.scanned_only())})
    assert response.status_code == 422
    assert "OCR is not supported" in response.json()["detail"]


def test_unreadable_encrypted_and_position_free_pdfs_raise_safe_errors():
    with pytest.raises(ValueError, match="not a readable PDF"):
        importiere("broken.pdf", b"%PDF-1.4 this is not a PDF")
    from pypdf import PdfReader, PdfWriter
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(synthetic.mixed_boq())))
    writer.encrypt("secret", algorithm="RC4-128")
    encrypted = io.BytesIO()
    writer.write(encrypted)
    with pytest.raises(ValueError, match="password-protected"):
        importiere("locked.pdf", encrypted.getvalue())
    with pytest.raises(ValueError, match="No BoQ positions"):
        importiere("letter.pdf", synthetic.letter_without_positions())


def test_imported_pdf_runs_through_the_existing_review_route():
    client = TestClient(app)
    imported = client.post("/api/lv/import", files={"datei": ("mixed.pdf", synthetic.mixed_boq())})
    assert imported.status_code == 200
    report = client.post("/api/lv/pruefen", json=imported.json())
    assert report.status_code == 200
    body = report.json()
    assert body["kennzahlen"]["positionen"] == 5
    flagged = {f["oz"] for f in body["findings"] if f["quelle"] == "regel"}
    assert {"1...2", "1...3"} <= flagged


@pytest.mark.skipif(not ROHBAU.exists(), reason="private test case data/testfaelle/rohbau_efh is not available")
def test_structural_works_test_case_imports_as_reviewable_boq():
    result = import_with_blocks(ROHBAU.name, ROHBAU.read_bytes())
    lv = result.lv
    positions = {p.oz: p for p in lv.positionen}
    titles = list(dict.fromkeys(p.titel_pfad[0].split()[0] for p in lv.positionen))
    assert titles == [str(n) for n in range(1, 10)]
    assert all(len(p.titel_pfad) == 1 for p in lv.positionen)
    assert len(positions) == len(lv.positionen) == 100  # manual cross-check recorded in issue #10
    counts = {t: sum(p.titel_pfad[0].split()[0] == t for p in lv.positionen) for t in titles}
    assert counts == {"1": 5, "2": 6, "3": 6, "4": 6, "5": 16, "6": 45, "7": 7, "8": 6, "9": 3}
    assert (positions["8...3"].menge, positions["8...3"].einheit) == (7, None)
    nine_one = positions["9...1"]
    assert (nine_one.menge, nine_one.einheit, nine_one.langtext) == (None, None, "")
    assert nine_one.kurztext
    assert (positions["9...3"].menge, positions["9...3"].einheit) == (None, None)
    for oz in ("6...39", "6...40"):
        assert positions[oz].kurztext and positions[oz].langtext and positions[oz].menge
    assert {p.typ for p in lv.positionen if p.oz.startswith("7...")} == {"stundenlohn"}
    assert positions["5...3"].typ == positions["6...22"].typ == "bedarf"
    assert positions["1...1"].typ == "pauschal"
    for position in lv.positionen:
        assert "Übertrag" not in position.kurztext + position.langtext
    assert result.images == [] and result.warnings == []
    report = TestClient(app).post("/api/lv/pruefen", json=lv.model_dump())
    assert report.status_code == 200
    body = report.json()
    assert body["kennzahlen"]["positionen"] == 100
    flagged = {f["oz"] for f in body["findings"]}
    assert {"8...3", "9...1", "9...3"} <= flagged

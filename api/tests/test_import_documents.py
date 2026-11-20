"""Typed document classification, source preservation and file export acceptance."""
import base64
import json
from pathlib import Path
import pytest
from app.lv.documents import parse_document, export_documents

FIXTURES = Path(__file__).parent / "fixtures/gaeb"


@pytest.mark.parametrize("name,text,kind", [
    ("terms.txt", "Contract\nClient: Example\nDeadline: 2026-12-01\nPayment within 30 days", "contract"),
    ("work.txt", "Bill of quantities\nItem 1: walls, quantity 2 m2", "boq"),
    ("rates.txt", "Price list\nHourly wage: 28.50 EUR/h", "price_list"),
    ("rules.txt", "Regulatory requirements\nCountry: Germany\nCompany: Example\nDIN 1234", "regulatory"),
    ("notes.txt", "Some miscellaneous notes", "unknown"),
])
def test_classification_is_exclusive_and_evidenced(name, text, kind):
    doc = parse_document(name, text.encode())
    assert doc.detected_type == kind
    assert doc.evidence
    assert all(e.value.sources[0].file == name for e in doc.evidence)
    assert base64.b64decode(doc.raw.content) == text.encode()
    assert "\n".join(v.value for v in doc.text) == text


def test_export_preserves_exact_prices_sources_and_unknown_content(tmp_path):
    raw = (FIXTURES / "offer.x84").read_bytes()
    doc = parse_document("offer.x84", raw)
    assert doc.detected_type == "boq"
    p, = doc.positions
    assert p.quantity.value == "2.000"
    assert p.unit_price.value == "12.50"
    assert p.unit_price.original == "12.50"
    assert p.unit_price.sources[0].path.endswith("/Item[1]/UP[1]")
    index = export_documents([doc], tmp_path)
    entry, = index["documents"]
    assert entry["detected_type"] == "boq"
    assert entry["counts"]["positions"] == 1
    saved = json.loads((tmp_path / entry["output_file"]).read_text())
    assert base64.b64decode(saved["raw"]["content"]) == raw
    assert saved["positions"][0]["unit_price"]["value"] == "12.50"
    assert json.loads((tmp_path / "index.json").read_text()) == index


def test_docx_extracts_contract_fields_with_paragraph_sources():
    from io import BytesIO
    from zipfile import ZipFile
    stream = BytesIO()
    xml = '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>' + ''.join(
        '<w:p><w:r><w:t>' + text + '</w:t></w:r></w:p>' for text in
        ["Contract", "Client: Synthetic Ltd", "Deadline: 2026-12-01", "Payment: 30 days", "Work must meet drawings"]
    ) + '</w:body></w:document>'
    with ZipFile(stream, "w") as archive:
        archive.writestr("word/document.xml", xml)
        archive.writestr("custom/unused.xml", "Preserve this too")
    doc = parse_document("terms.docx", stream.getvalue())
    assert doc.detected_type == "contract"
    assert doc.deadlines[0].value == "Deadline: 2026-12-01"
    assert doc.payment_terms[0].value == "Payment: 30 days"
    assert doc.parties[0].value == "Client: Synthetic Ltd"
    assert doc.requirements[0].value == "Work must meet drawings"
    assert doc.deadlines[0].sources[0].path == "word/document.xml//w:p[3]"
    assert base64.b64decode(doc.raw.content) == stream.getvalue()


def test_pdf_text_has_page_sources_and_no_invented_rows():
    from io import BytesIO
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=200)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
    content = DecodedStreamObject()
    content.set_data(b"BT /F1 12 Tf 10 100 Td (Price list) Tj 0 -20 Td (Hourly wage: 28.50 EUR/h) Tj ET")
    page[NameObject("/Contents")] = content
    stream = BytesIO()
    writer.write(stream)
    doc = parse_document("rates.pdf", stream.getvalue())
    assert doc.detected_type == "price_list"
    assert "28.50" in doc.text[0].value
    assert doc.text[0].sources[0].page == 1
    assert doc.rates == []
    assert any("text only" in warning for warning in doc.warnings)


def test_unknown_invalid_and_ambiguous_documents_preserve_bytes():
    for name, raw in [("broken.pdf", b"not PDF"), ("broken.docx", b"not ZIP"),
                      ("broken.x83", b"not XML"), ("data.bin", b"\xff\x00"),
                      ("mixed.txt", b"Contract and price list")]:
        doc = parse_document(name, raw)
        assert doc.detected_type == "unknown"
        assert doc.evidence
        assert base64.b64decode(doc.raw.content) == raw


def test_gaeb_phase_classification_does_not_drop_awarded_items_or_offer_prices():
    xml = (FIXTURES / "offer.x84").read_bytes()
    contract = parse_document("award.x86", xml.replace(b"<DP>84", b"<DP>86"))
    assert contract.detected_type == "contract"
    assert len(contract.positions) == 1
    assert contract.positions[0].unit_price.value == "12.50"
    prices = parse_document("prices.x84", b'<GAEB><Award><DP>84</DP><BoQ><BoQBody><Itemlist><Item RNoPart="1"><UP>0</UP></Item></Itemlist></BoQBody></BoQ></Award></GAEB>')
    assert prices.detected_type == "price_list"
    assert prices.rates[0].unit_price.value == "0"


def test_export_distinguishes_same_named_sources_and_refuses_overwrite(tmp_path):
    docs = [parse_document("../same.txt", b"Contract"), parse_document("../same.txt", b"Price list")]
    index = export_documents(docs, tmp_path)
    assert len({e["output_file"] for e in index["documents"]}) == 2
    assert (tmp_path / index["documents"][0]["output_file"]).parent.name == "contract"
    with pytest.raises(ValueError, match="already exists"):
        export_documents(docs, tmp_path)


def test_all_partner_inputs_classify_and_export_in_place(tmp_path):
    dataset = Path(__file__).resolve().parents[2] / "data/datensatz"
    paths = sorted(path for path in dataset.iterdir() if path.is_file())
    assert len(paths) == 44
    docs = [parse_document(path.name, path.read_bytes()) for path in paths]
    index = export_documents(docs, tmp_path)
    assert len(index["documents"]) == 44
    for entry, path in zip(index["documents"], paths):
        assert entry["detected_type"] in ("contract", "boq", "price_list", "regulatory", "unknown")
        saved = json.loads((tmp_path / entry["output_file"]).read_text())
        assert saved["evidence"]
        assert base64.b64decode(saved["raw"]["content"]) == path.read_bytes(), "Input bytes must survive"


def test_export_numeric_schema_rejects_nonfinite_and_unlocated_values():
    from pydantic import ValidationError
    from app.lv.schemas import DecimalValue, Source
    for value in ("NaN", "Infinity", "garbage"):
        with pytest.raises(ValidationError):
            DecimalValue(value=value, original=value, sources=[Source(file="test", line=1)])
    with pytest.raises(ValidationError):
        Source(file="test")

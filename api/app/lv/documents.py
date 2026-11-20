"""Classify locally and export source-preserving documents to a caller directory."""
import base64
import hashlib
import io
import json
import re
from pathlib import Path
from zipfile import BadZipFile, ZipFile
from xml.etree import ElementTree as ET
from .gaeb import parse_gaeb
from .schemas import (DOCUMENT_SCHEMAS, Document, Evidence, ParsedDocument, RawContent,
                      Source, TextValue)

GAEB_EXTENSIONS = {".x83", ".x84", ".x86", ".d83", ".d84", ".d86"}
PATTERNS = {
    "contract": r"\b(contract|vertrag|vertragsbedingungen|bauvertrag|payment terms|zahlungsbedingungen|ausführungsfristen)\b",
    "boq": r"\b(bill of quantities|leistungsverzeichnis|boq|lv)\b",
    "price_list": r"\b(price list|preisliste|lohnkosten|lohntarif|wage|salary|stundenlöhne|stundensätze|hourly rates)\b",
    "regulatory": r"\b(regulatory requirements|regulations|vorschriften|normen|regelwerk|technical standard|technische bestimmungen)\b",
}


def text_value(filename, text, *, path=None, page=None, line=None):
    return TextValue(value=text, original=text, sources=[Source(file=filename, path=path, page=page, line=line)])


def extract_text(filename, content):
    """Minimal text only: PDF pages and DOCX paragraphs, never OCR or table mapping."""
    suffix = Path(filename).suffix.lower()
    blocks, warnings = [], []
    if suffix == ".pdf":
        from pypdf import PdfReader
        try:
            reader = PdfReader(io.BytesIO(content))
            if reader.is_encrypted:
                return [], ["Encrypted PDF: extraction unavailable; original bytes retained."]
            for number, page in enumerate(reader.pages, 1):
                try:
                    text = page.extract_text() or ""
                    blocks.append(text_value(filename, text, page=number))
                except Exception:
                    warnings.append(f"PDF page {number}: text extraction failed; original bytes retained.")
            if not any(b.value.strip() for b in blocks):
                warnings.append("No extractable PDF text; OCR is outside this importer.")
            warnings.append("PDF text only; tables and BoQ positions are not mapped (issue #10).")
        except Exception:
            warnings.append("Invalid or unreadable PDF; original bytes retained.")
    elif suffix == ".docx":
        try:
            with ZipFile(io.BytesIO(content)) as archive:
                members = sorted(n for n in archive.namelist() if n.startswith("word/") and
                                 re.fullmatch(r"word/(document|header\d*|footer\d*|footnotes|endnotes|comments)\.xml", n))
                for name in members:
                    payload = archive.read(name)
                    if b"<!DOCTYPE" in payload or b"<!ENTITY" in payload:
                        raise ValueError("Unsupported XML declaration")
                    root = ET.fromstring(payload)
                    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                    for index, paragraph in enumerate(root.findall(".//w:p", ns), 1):
                        parts = []
                        for node in paragraph.iter():
                            tag = node.tag.rsplit("}", 1)[-1]
                            if tag == "t":
                                parts.append(node.text or "")
                            elif tag in ("br", "cr"):
                                parts.append("\n")
                            elif tag == "tab":
                                parts.append("\t")
                        blocks.append(text_value(filename, "".join(parts), path=f"{name}//w:p[{index}]"))
            warnings.append("DOCX text only; tables are read as paragraphs, images remain in raw bytes.")
        except (BadZipFile, ET.ParseError, KeyError, ValueError):
            warnings.append("Invalid or unreadable DOCX; original bytes retained.")
    elif suffix in (".txt", ".csv"):
        try:
            text = content.decode("utf-8-sig")
            blocks = [text_value(filename, line, line=i) for i, line in enumerate(text.splitlines(), 1)]
        except UnicodeDecodeError:
            warnings.append("Text is not UTF-8; original bytes retained.")
    else:
        warnings.append("Unsupported text extraction format; original bytes retained. Excel parsing remains issue #9.")
    return blocks, warnings


def classify(filename, blocks):
    filename_value = text_value(filename, Path(filename).name, path="filename")
    scores = {kind: 0 for kind in PATTERNS}
    evidence = {kind: [] for kind in PATTERNS}
    for block_number, block in enumerate([filename_value, *blocks]):
        text = block.value.replace("_", " ")
        for kind, pattern in PATTERNS.items():
            if re.search(pattern, text, re.I):
                scores[kind] += 8 if block_number == 0 else 3 if block_number == 1 else 1
                evidence[kind].append(Evidence(rule="Filename keyword" if block_number == 0 else "Text keyword", value=block))
    top = max(scores.values())
    winners = [kind for kind, score in scores.items() if score == top]
    if top == 0 or len(winners) != 1:
        return "unknown", [Evidence(rule="No unambiguous document-type evidence", value=filename_value)]
    winner = winners[0]
    return winner, evidence[winner]


def matching_lines(blocks, pattern):
    result = []
    for block in blocks:
        for line in block.value.splitlines():
            if re.search(pattern, line, re.I):
                result.append(TextValue(value=line, original=line, sources=block.sources))
    return result


def parse_document(filename: str, content: bytes) -> ParsedDocument:
    """Every input gets one type. Unreadable input is unknown with safe warnings."""
    common = dict(source_file=filename, sha256=hashlib.sha256(content).hexdigest(),
                  raw=RawContent(content=base64.b64encode(content).decode("ascii")))
    if Path(filename).suffix.lower() in GAEB_EXTENSIONS:
        try:
            boq = parse_gaeb(filename, content)
        except ValueError as exc:
            return DOCUMENT_SCHEMAS["unknown"](**common, evidence=[Evidence(
                rule="GAEB parsing failed", value=text_value(filename, Path(filename).name, path="filename"))], warnings=[str(exc)])
        phase = boq.phase.value if boq.phase else ""
        kind = "contract" if phase == "86" else "price_list" if phase == "84" and not any(
            p.short_text or p.detailed_text for p in boq.positions) else "boq"
        fields = boq.model_dump(exclude={"detected_type", "positions", "section_totals"})
        if kind == "price_list":
            return DOCUMENT_SCHEMAS[kind](**fields, rates=boq.positions)
        return DOCUMENT_SCHEMAS[kind](**fields, positions=boq.positions, section_totals=boq.section_totals)
    blocks, warnings = extract_text(filename, content)
    kind, evidence = classify(filename, blocks)
    fields = dict(**common, text=blocks, warnings=warnings, evidence=evidence)
    if kind == "contract":
        fields.update(requirements=matching_lines(blocks, r"\b(must|shall|required|muss|anforderung|pflicht)\b"),
                      deadlines=matching_lines(blocks, r"\b(deadline|frist|termin|fertigstellung)\b"),
                      payment_terms=matching_lines(blocks, r"\b(payment|zahlung|vergütung|eur|€)\b"),
                      parties=matching_lines(blocks, r"\b(client|contractor|auftraggeber|auftragnehmer|party|parties)\b"))
    elif kind == "regulatory":
        fields.update(requirements=matching_lines(blocks, r"\b(DIN|EN|ISO|VOB|must|shall|muss|vorschrift|anforderung)\b"),
                      companies=matching_lines(blocks, r"\b(company|companies|firma|unternehmen|gmbh|ag)\b"),
                      countries=matching_lines(blocks, r"\b(country|germany|deutschland|austria|österreich|schweiz)\b"))
    if kind in ("boq", "price_list"):
        fields["warnings"] = warnings + ["Unstructured text retained; positions and rates are not inferred from prose."]
    return DOCUMENT_SCHEMAS[kind](**fields)


def export_documents(documents: list[ParsedDocument], output_directory: str | Path) -> dict:
    """Create a new export batch. Never silently replace an existing index or document."""
    root = Path(output_directory)
    root.mkdir(parents=True, exist_ok=True)
    if (root / "index.json").exists():
        raise ValueError("Export index already exists. Choose a new output directory.")
    entries = []
    for number, document in enumerate(documents, 1):
        kind = document.detected_type
        # Names never use source path components and remain distinct for duplicate basenames.
        relative = Path(kind) / f"{number:04d}-{document.sha256[:16]}.json"
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8") as file:
            file.write(document.model_dump_json(indent=2))
        fields = document.model_dump()
        counts = {name: len(value) for name, value in fields.items() if isinstance(value, (list, dict))
                  and name not in ("evidence", "warnings")}
        entries.append(dict(source_file=document.source_file, detected_type=kind, schema_version=document.schema_version,
                            sha256=document.sha256, counts=counts, output_file=relative.as_posix()))
    index = {"schema_version": "1.0", "documents": entries}
    with (root / "index.json").open("x", encoding="utf-8") as file:
        json.dump(index, file, ensure_ascii=False, indent=2)
    return index

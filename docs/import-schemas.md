# Typed document import schemas (version 1.0)

`api/app/lv/schemas.py` defines five independent Pydantic models. They are a local document-storage boundary, separate from the unchanged `LV` / `Position` HTTP contract in `modelle.py`. The existing `POST /api/lv/import` and `importiere(filename, bytes)` return `LV` with JSON numbers and unknown values as `null`.

## Use and export

Install the API requirements from the repository root:

```sh
.venv/bin/python -m pip install -r api/requirements.txt
```

From `api/`, parse documents and export a batch into a new caller-selected directory:

```python
from pathlib import Path
from app.lv.documents import parse_document, export_documents
from app.lv.schemas import DOCUMENT_SCHEMAS

sources = [Path("/local/input/tender.x83"), Path("/local/input/terms.pdf")]
documents = [parse_document(str(source), source.read_bytes()) for source in sources]
index = export_documents(documents, Path("../import-output/batch-001"))
# Each independently usable JSON Schema can be obtained without any partner input:
contract_schema = DOCUMENT_SCHEMAS["contract"].model_json_schema()
```

`import-output/` is gitignored. Other output locations are the caller's responsibility; tests use temporary directories. Exports contain confidential source bytes and must remain local/private. Export does not mutate source files, send requests, invoke models, or write to history storage. History ingestion can consume these files in a later integration.

Each document is saved as `<detected_type>/<batch ordinal>-<source hash prefix>.json`. Source filenames are metadata, never output path components. Repeated names and identical inputs in one batch produce separate files. Existing files/indexes are refused rather than overwritten; use a new directory per batch. A failed batch can leave partial files, so retry in a fresh directory.

`index.json` contains `schema_version` and `documents`. Each entry records `source_file`, `detected_type`, `schema_version`, `sha256`, `output_file` (relative to the output directory) and counts for typed collections, including positions/rates/text. The index represents the supplied batch, not every file previously present in that directory.

## Common fields and provenance

Every document contains:

| Field | Meaning |
| --- | --- |
| `schema_version` | Literal `1.0`; version of this export contract. |
| `source_file`, `sha256` | Caller-supplied source name/path and SHA-256 of the complete original bytes. |
| `detected_type` | Exactly one of the five types below. |
| `evidence` | Rule name plus a traced value used to classify the file. Unknown inputs also give a reason. |
| `phase`, `title` | Traced GAEB phase/title when supplied, otherwise null. |
| `text` | Traced text blocks where extraction is available. |
| `raw` | `encoding: "base64"`, `content`: **all original bytes**, and a description. This includes every unsupported/unmapped field, image, attribute, record, XML extension, attachment and original formatting; decoding reproduces the source exactly. |
| `warnings` | Extraction limits/failures, without confidential contents. |

`TextValue` is `{value, original, sources}`. `value` is the readable rendering; `original` retains the input text before normalization. `sources` contains at least one `{file, path, page, line}`; unused locator fields are null. XML locators use one-based, namespace-local element paths with sibling indexes, e.g. `/GAEB[1]/Award[1]/BoQ[1]/BoQBody[1]/Itemlist[1]/Item[1]/UP[1]`. Attributes append `/@RNoPart`. PDF pages and GAEB 90 lines are one-based. GAEB 90 `path` gives inclusive one-based columns. DOCX paths give the ZIP member and the one-based paragraph in document order; table cells are paragraphs too. Selected lines from PDF pages retain their page locator.

`DecimalValue` has the same shape, with a finite, decimal-safe **string** in `value`, such as `"12.50"`. `original` preserves comma/dot notation, precision and fixed-column spacing. GAEB 90 quantities use three implied decimal places; unit prices combine the cent field and optional tenth-cent digit; totals use two places. Missing/blank values are null, known zero remains `"0"` or its supplied precision. No GP is calculated. The compatibility `LV` adapter converts these values to finite floats; use the typed document export for exact decimal arithmetic and audit.

Item records contain traced `oz`, `short_text`, `detailed_text`, `quantity`, `unit`, `unit_price`, `total_price` and `title_path`, plus the compatibility `kind`. OZ combines original section/item fragments using the supplied breakdown widths, including an item index; it never renumbers or deduplicates. OZ sources include every contributing fragment. `title_path` uses section number plus label. The compatibility kind defaults to `normal`; explicit lump-sum/provisional XML flags and legacy normal/alternative/provisional markers are mapped where understood. Other semantic markers remain in raw content. Neither kind nor type classification is a domain finding or a verification of legal applicability.

## Per-type schemas

| Type / Pydantic model | Additional fields | Decision evidence |
| --- | --- | --- |
| `boq` / `BoQDocument` | `positions`, `section_totals` | Structured GAEB BoQ, phase 83 tender or phase 84 with item descriptions; otherwise text/filename keywords. |
| `contract` / `ContractDocument` | `requirements`, `deadlines`, `payment_terms`, `parties`, `positions`, `section_totals` | Phase 86 award, or contract/payment/deadline vocabulary. Awarded items and prices remain attached to the contract. |
| `price_list` / `PriceListDocument` | `rates` (item records, including original OZ, quantities if supplied and prices) | Phase 84 with prices/identifiers but no item descriptions, or price/wage/salary vocabulary. An offer with item descriptions remains a BoQ. |
| `regulatory` / `RegulatoryDocument` | `requirements`, `companies`, `countries` | Regulatory/standards vocabulary; selected lines retain source locators. |
| `unknown` / `UnknownDocument` | Common fields only | Missing/ambiguous evidence, unsupported content or parsing failure. Raw content is still preserved. |

Contract/regulatory text fields are evidenced **whole lines**, not inferred entities, dates, currencies, legal duties or verified standards. Missing fields stay empty; text is always retained in full extracted blocks and original bytes. Regulatory extraction never sets the person-only verification required by the specification contract.

Classification is deterministic and heuristic: recognized GAEB structure/phase takes priority; otherwise explicit type vocabulary in filenames and extracted text is scored. Filename matches weigh 8, the first text block 3, and later blocks 1. Equal top scores or no evidence give `unknown`. Mixed documents still get one primary type; raw bytes and all extracted text retain their other content. Consumers should review the evidence rather than treating classification as certainty.

## Coverage and limits

- XML X83/X84: namespaces, recursive sections, breakdown widths, original item indexes, quantities/units, readable markup and umlauts, explicit UP/IT, explicit section totals. Missing prices remain null. Invalid XML, roots, numbers and DTD/entity declarations produce safe `ValueError` through the LV importer (HTTP 422). Document parsing instead retains invalid inputs as `unknown` with warnings.
- XML X86 and legacy D83/D84/D86: available through `parse_document` / `parse_gaeb`. Legacy parsing covers the dataset's 80-column GAEB 90 records, quantity/unit/price fields, normal/alternative/provisional markers, short/detailed text and section labels. Optional contract texts, subdescription structure, custom records and legacy section totals remain in raw content; no unsupported values are invented. This is not complete GAEB 90 validation or GAEB 2000 support.
- PDFs: local `pypdf` text extraction per page for classification and selected contract/regulatory lines. No OCR, layout reconstruction, PDF table mapping, quantity or price inference; full PDF BoQ import remains #10. Encrypted/scanned/unreadable files have visible warnings and preserved bytes.
- DOCX: standard-library ZIP/XML extraction of paragraphs in document/header/footer/footnote/endnote/comment parts, including text inside tables. No image OCR, relationship resolution or table semantics. Other parts remain in raw content.
- Excel: no structured parsing here; #9 retains ownership. Unsupported formats get an `unknown` result unless filename evidence identifies a type, with raw bytes and extraction warnings.

Tests read all 44 confidential partner inputs in place and export only to temporary directories. Every GAEB file has an expected item count; original XML acceptance also runs through upload and review. Synthetic fixtures test exact prices, source locators, markup, missing/zero/duplicate values, malformed input, classification, DOCX/PDF extraction and export collisions. Partner source files are never copied to fixtures or changed.

Format references used for interpretation: [GAEB DA XML technical documentation](https://www.gaeb.de/wp-content/uploads/2023/09/Fachdokumentation_GAEB-DA-XML_3.3_2023-01.pdf) and the format implementer's [Free GAEB Book, sections 1.4–1.6](https://www.bvbs.de/wp-content/uploads/2018/07/Das-Freie-GAEB-Buch.pdf). These explain structure/record semantics; they are not evidence of standards compliance for imported work.

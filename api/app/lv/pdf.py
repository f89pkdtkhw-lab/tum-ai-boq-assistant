"""Text PDF import: BoQ positions from word coordinates, textless regions as ordered JPEG crops.

Two entry points:

* ``importiere(dateiname, inhalt) -> LV`` is the shared importer contract (see ``importer.py``).
* ``import_with_blocks(dateiname, inhalt) -> PdfImport`` returns the same LV plus the complete
  content of the PDF as one ordered list of ``Block`` objects for later processing steps.

Reading model
-------------
Text is read with pdfplumber from word coordinates, never with OCR. Words are grouped into lines.
The OZ column is the most common left edge of lines that start with a multi-level OZ such as
``8...3``, ``01.0010`` or ``2.1.10``. A quantity line is ``<quantity> [<unit>] <price fields>``
whose price fields (``____``, ``....``, ``*NEP*`` or numbers) reach into the right part of the page.
Repeated lines in the header and footer bands (same text on many pages, digits ignored) and carry-over
lines (``Übertrag``) are removed and never become positions. ``Summe ...`` lines and summary pages
close the current entry and never become positions.

An OZ entry is a position when it has a quantity line (an empty one such as ``___ ____`` counts:
the position then has no quantity and no unit), or when it is a leaf at the deepest OZ level.
Otherwise it is a section title and forms ``titel_pfad`` as ``"<OZ> <title>"``. Quantities, units and
texts are kept as printed: a missing unit stays ``None``, a missing quantity stays ``None``.

Textless regions
----------------
Embedded images, vector drawings (curves, for example digital handwriting) and ink or stamp
annotations that contain no extractable text are not read. They are cut out of the rendered page as
JPEG (``Block.kind == "image"``) with page, bounding box and index, at exactly their place in the
reading order (page, then top to bottom, then left to right). A page without any text is one such
region. Images that repeat in the header or footer band (logos) are skipped.

Scanned PDFs: a PDF in which no page has extractable text is rejected with a ``ValueError``
explaining that OCR is not supported. A PDF with only some scanned pages is imported: the scanned
pages become full-page image blocks.
"""
from __future__ import annotations

import io
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from ..modelle import LV, Position

Bbox = tuple[float, float, float, float]

HEADER_BAND = 0.22        # share of page height at the top that may hold repeated headers
FOOTER_BAND = 0.12        # share of page height at the bottom that may hold repeated footers
PRICE_X_SHARE = 0.6       # price fields of a quantity line start right of this share of page width
LINE_TOLERANCE = 3.0      # points; words whose tops differ less belong to one line
OZ_COLUMN_TOLERANCE = 6.0
CROP_RESOLUTION = 150     # dpi of JPEG crops
JPEG_QUALITY = 85
MIN_REGION_SIDE = 10.0    # points; smaller drawings are decoration, not content
REGION_GAP = 6.0          # points; drawings closer than this form one region
MAX_TEXT_CHARS_IN_REGION = 3
MAX_IMAGE_BLOCKS = 500
MAX_DRAWINGS_PER_PAGE = 400   # beyond this (plans, CAD exports) a page's drawings form one region

OZ_PATTERN = re.compile(r"^\d{1,9}(?:\.{1,3}\d{1,9})*\.?$")
QUANTITY_PATTERN = re.compile(r"^(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d+)?$")
UNIT_PATTERN = re.compile(r"^[A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß²³/.]{0,5}$|^m[²³23]$")
PLACEHOLDER_PATTERN = re.compile(r"^(?:_{2,}|\.{3,}|\*NEP\*)$", re.I)
TOTAL_PATTERN = re.compile(r"^(summe|gesamtsumme|zwischensumme|titelsumme|endsumme|gesamtbetrag|zusammenstellung|zusammenfassung)\b", re.I)
CARRY_PATTERN = re.compile(r"^(übertrag|uebertrag)\b", re.I)
PAGE_NUMBER_PATTERN = re.compile(r"\bseite\b\s*:?\s*\d+", re.I)
NOTE_PATTERN = re.compile(r"^(hinweis|vorbemerkung|vorbemerkungen)\b", re.I)
MARKERS = {"bedarf": "bedarf", "bedarfsposition": "bedarf", "eventual": "bedarf", "eventualposition": "bedarf",
           "alternativ": "alternativ", "alternativposition": "alternativ", "wahlposition": "alternativ",
           "grundposition": None}
LUMP_SUM_UNITS = {"psch", "psch.", "pauschal", "pausch", "pausch.", "pschl", "pschl."}


@dataclass(frozen=True)
class Block:
    """One piece of PDF content in reading order.

    ``bbox`` is ``(x0, top, x1, bottom)`` in PDF points with the origin at the top left of the page,
    as pdfplumber reports it. ``index`` is the 0-based position in ``PdfImport.blocks``.
    ``kind`` is ``"text"`` or ``"image"``. Text roles: ``text`` (free text such as preliminary
    remarks), ``note`` (``Hinweis`` blocks and text under a section title), ``oz`` (the printed OZ),
    ``title``, ``short_text``, ``long_text``, ``marker`` (for example ``Bedarf``), ``quantity``
    (quantity, unit and price fields) and ``total`` (``Summe`` and summary lines). Image blocks have role ``image``, the JPEG bytes in
    ``jpeg`` and the detection source in ``source`` (``embedded_image``, ``drawing``, ``annotation``
    or ``page``). ``oz`` is the OZ of the position or section title the block belongs to, if any.
    """
    index: int
    page: int
    bbox: Bbox
    kind: Literal["text", "image"]
    role: str
    text: str = ""
    oz: str | None = None
    jpeg: bytes | None = field(default=None, repr=False)
    source: str = ""


@dataclass(frozen=True)
class PdfImport:
    """Result of ``import_with_blocks``: the LV plus every content block in reading order."""
    lv: LV
    blocks: list[Block]
    warnings: list[str]

    @property
    def images(self) -> list[Block]:
        return [b for b in self.blocks if b.kind == "image"]


@dataclass
class _Word:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    font: str
    size: float


@dataclass
class _Line:
    page: int
    words: list[_Word]
    page_width: float
    page_height: float

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    @property
    def x0(self) -> float:
        return self.words[0].x0

    @property
    def top(self) -> float:
        return min(w.top for w in self.words)

    @property
    def bottom(self) -> float:
        return max(w.bottom for w in self.words)

    @property
    def bbox(self) -> Bbox:
        return (min(w.x0 for w in self.words), self.top, max(w.x1 for w in self.words), self.bottom)

    @property
    def size(self) -> float:
        return max(w.size for w in self.words)


@dataclass
class _Region:
    page: int
    bbox: Bbox
    source: str
    jpeg: bytes = b""

    @property
    def top(self) -> float:
        return self.bbox[1]

    @property
    def x0(self) -> float:
        return self.bbox[0]


@dataclass
class _Entry:
    """An OZ entry (position or title) or a note, collected before classification."""
    kind: Literal["oz", "note"]
    oz: str | None = None
    head: list[_Word] = field(default_factory=list)   # words after the OZ on the OZ line
    head_line: _Line | None = None
    lines: list[_Line] = field(default_factory=list)  # text lines before the quantity line
    quantity: float | None = None
    unit: str | None = None
    unit_price: float | None = None
    total_price: float | None = None
    has_quantity_line: bool = False
    markers: set[str] = field(default_factory=set)
    role: str = ""                                    # "position", "title" or "text" after classification
    short_lines: set[int] = field(default_factory=set)  # ids of lines that form the short text


def importiere(dateiname: str, inhalt: bytes) -> LV:
    """Import a text PDF as LV; unreadable, scanned or position-free PDFs raise a safe ValueError."""
    return import_with_blocks(dateiname, inhalt).lv


def import_with_blocks(dateiname: str, inhalt: bytes) -> PdfImport:
    """Import a text PDF and return the LV plus all text blocks and JPEG crops in reading order."""
    import pdfplumber
    try:
        pdf = pdfplumber.open(io.BytesIO(inhalt))
    except Exception as exc:
        raise ValueError(_open_error(exc)) from None
    with pdf:
        try:
            pages = list(pdf.pages)
            page_lines, page_regions = [], []
            for number, page in enumerate(pages, 1):
                lines, regions = _read_page(number, page)
                page.close()  # drop pdfplumber's per-page layout cache; large BoQs stay flat in memory
                page_lines.append(lines)
                page_regions.append(regions)
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(_open_error(exc)) from None
        if not pages:
            raise ValueError("The PDF has no pages.")
        if not any(page_lines):
            raise ValueError("The PDF contains no extractable text; it is probably scanned or image-only. "
                             "OCR is not supported. Please upload a text PDF, GAEB or Excel file.")
        warnings: list[str] = []
        body = _remove_headers_and_footers(page_lines)
        regions = _filter_regions(page_regions, pages)
        _render_regions(pages, regions, warnings)
    items = sorted([*(l for ls in body for l in ls), *(r for rs in regions for r in rs)],
                   key=lambda item: (item.page, round(item.top, 1), item.x0))
    oz_column = _oz_column([l for ls in body for l in ls])
    if oz_column is None:
        raise ValueError("No BoQ positions with an OZ were recognized in the PDF. "
                         "Please check that it is a text BoQ, or upload GAEB or Excel.")
    events = _segment(items, oz_column)
    entries = list({id(e): e for _, _, e in events if e is not None and e.kind == "oz"}.values())
    _classify(entries, warnings)
    lv = _build_lv(dateiname, entries, body, warnings)
    if not lv.positionen:
        raise ValueError("No BoQ positions were recognized in the PDF. "
                         "Please check that it is a text BoQ, or upload GAEB or Excel.")
    blocks = _build_blocks(events)
    return PdfImport(lv=lv, blocks=blocks, warnings=warnings)


def _open_error(exc: Exception) -> str:
    chain, current = [], exc
    while current is not None and len(chain) < 5:
        chain.append(f"{type(current).__name__} {current}".lower())
        current = current.__cause__ or current.__context__
    if any("password" in text or "encrypt" in text for text in chain):
        return "The PDF is password-protected or encrypted. Please upload an unprotected PDF."
    return "The file is not a readable PDF. Please check the file or upload GAEB or Excel."


def _read_page(number: int, page) -> tuple[list[_Line], list[_Region]]:
    width, height = float(page.width), float(page.height)
    words = page.dedupe_chars().extract_words(extra_attrs=["fontname", "size"])
    parsed = sorted((_Word(text=w["text"], x0=float(w["x0"]), x1=float(w["x1"]), top=float(w["top"]),
                           bottom=float(w["bottom"]), font=str(w["fontname"]), size=float(w["size"]))
                     for w in words if w["text"].strip()), key=lambda w: (w.top, w.x0))
    lines: list[_Line] = []
    for word in parsed:
        if lines and abs(word.top - lines[-1].top) <= LINE_TOLERANCE:
            lines[-1].words.append(word)
        else:
            lines.append(_Line(page=number, words=[word], page_width=width, page_height=height))
    for line in lines:
        line.words.sort(key=lambda w: w.x0)
    regions = [_Region(number, _clip(_bbox(o), page), "embedded_image") for o in page.images]
    regions += [_Region(number, _clip(_curve_bbox(o), page), "drawing") for o in page.curves]
    for annot in page.annots or []:
        subtype = str((annot.get("data") or {}).get("Subtype", "")).strip("/'\" ").lower()
        if subtype.endswith(("ink", "stamp")):
            regions.append(_Region(number, _clip(_bbox(annot), page), "annotation"))
    regions = [r for r in regions if r.bbox[2] > r.bbox[0] and r.bbox[3] > r.bbox[1]]
    if len(regions) > MAX_DRAWINGS_PER_PAGE:
        regions = [_Region(number, (min(r.bbox[0] for r in regions), min(r.bbox[1] for r in regions),
                                    max(r.bbox[2] for r in regions), max(r.bbox[3] for r in regions)), "drawing")]
    regions = _merge_regions(regions)
    chars = page.chars
    textless = []
    for region in regions:
        x0, top, x1, bottom = region.bbox
        if x1 - x0 < MIN_REGION_SIDE or bottom - top < MIN_REGION_SIDE:
            continue
        inside = sum(1 for c in chars if x0 <= (c["x0"] + c["x1"]) / 2 <= x1 and top <= (c["top"] + c["bottom"]) / 2 <= bottom)
        if inside <= MAX_TEXT_CHARS_IN_REGION:
            textless.append(region)
    if not lines:  # a page without any text (scan, drawing) is one textless region
        drawn = textless or page.images or page.curves or page.rects or page.lines or page.annots
        textless = [_Region(number, _clip(tuple(float(v) for v in page.bbox), page), "page")] if drawn else []
    return lines, textless


def _bbox(obj) -> Bbox:
    return (float(obj["x0"]), float(obj["top"]), float(obj["x1"]), float(obj["bottom"]))


def _curve_bbox(curve) -> Bbox:
    """pdfminer bounds curves by their end points only; include control points and stroke width."""
    points = [pt for segment in curve.get("path") or [] for pt in segment[1:]]
    if not points:
        return _bbox(curve)
    pad = float(curve.get("linewidth") or 0) / 2
    xs, ys = [float(x) for x, _ in points], [float(y) for _, y in points]
    return (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)


def _clip(bbox: Bbox, page) -> Bbox:
    px0, ptop, px1, pbottom = (float(v) for v in page.bbox)
    x0, top, x1, bottom = bbox
    return (max(x0, px0), max(top, ptop), min(x1, px1), min(bottom, pbottom))


def _merge_regions(regions: list[_Region]) -> list[_Region]:
    """Union regions whose boxes, grown by REGION_GAP, touch; images win as source label."""
    merged = list(regions)
    changed = True
    while changed:
        changed = False
        result: list[_Region] = []
        for region in merged:
            for other in result:
                if _touch(region.bbox, other.bbox, REGION_GAP):
                    other.bbox = (min(other.bbox[0], region.bbox[0]), min(other.bbox[1], region.bbox[1]),
                                  max(other.bbox[2], region.bbox[2]), max(other.bbox[3], region.bbox[3]))
                    if region.source == "embedded_image":
                        other.source = region.source
                    changed = True
                    break
            else:
                result.append(_Region(region.page, region.bbox, region.source))
        merged = result
    return merged


def _touch(a: Bbox, b: Bbox, gap: float) -> bool:
    return a[0] - gap <= b[2] and b[0] - gap <= a[2] and a[1] - gap <= b[3] and b[1] - gap <= a[3]


def _in_band(top: float, bottom: float, height: float) -> bool:
    return bottom <= height * HEADER_BAND or top >= height * (1 - FOOTER_BAND)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\d+", "#", text)).strip().lower()


def _repeat_threshold(page_count: int) -> int:
    return max(2, math.ceil(page_count * 0.3))


def _remove_headers_and_footers(page_lines: list[list[_Line]]) -> list[list[_Line]]:
    """Drop repeated band lines, page numbers in the bands and carry-over lines anywhere."""
    threshold = _repeat_threshold(len(page_lines))
    seen: dict[str, list[tuple[int, float]]] = {}
    for lines in page_lines:
        for line in lines:
            if _in_band(line.top, line.bottom, line.page_height):
                seen.setdefault(_normalize(line.text), []).append((line.page, line.top))
    body = []
    for lines in page_lines:
        kept = []
        for line in lines:
            if CARRY_PATTERN.match(line.text):
                continue
            if _in_band(line.top, line.bottom, line.page_height):
                if PAGE_NUMBER_PATTERN.search(line.text):
                    continue
                pages = {p for p, top in seen.get(_normalize(line.text), []) if abs(top - line.top) <= LINE_TOLERANCE}
                if len(pages) >= threshold:
                    continue
            kept.append(line)
        body.append(kept)
    return body


def _filter_regions(page_regions: list[list[_Region]], pages) -> list[list[_Region]]:
    """Skip images that repeat at the same place in the header or footer band (logos)."""
    threshold = _repeat_threshold(len(page_regions))
    band = [(r.page, r.bbox) for rs in page_regions for r in rs
            if _in_band(r.bbox[1], r.bbox[3], float(pages[r.page - 1].height))]
    result = []
    for regions in page_regions:
        kept = []
        for region in regions:
            height = float(pages[region.page - 1].height)
            if _in_band(region.bbox[1], region.bbox[3], height):
                same = {p for p, b in band if all(abs(u - v) <= LINE_TOLERANCE for u, v in zip(b, region.bbox))}
                if len(same) >= threshold:
                    continue
            kept.append(region)
        result.append(kept)
    return result


def _render_regions(pages, regions: list[list[_Region]], warnings: list[str]) -> None:
    count = 0
    for page_regions in regions:
        if not page_regions:
            continue
        number = page_regions[0].page
        if count >= MAX_IMAGE_BLOCKS:
            warnings.append(f"Page {number}: more than {MAX_IMAGE_BLOCKS} textless regions; further regions are not exported.")
            page_regions.clear()
            continue
        page = pages[number - 1]
        rendered = page.to_image(resolution=CROP_RESOLUTION).original
        scale = CROP_RESOLUTION / 72
        px0, ptop = float(page.bbox[0]), float(page.bbox[1])
        kept = []
        for region in page_regions:
            if count >= MAX_IMAGE_BLOCKS:
                warnings.append(f"Page {number}: more than {MAX_IMAGE_BLOCKS} textless regions; further regions are not exported.")
                break
            x0, top, x1, bottom = region.bbox
            box = (max(0, int((x0 - px0) * scale)), max(0, int((top - ptop) * scale)),
                   min(rendered.width, math.ceil((x1 - px0) * scale)), min(rendered.height, math.ceil((bottom - ptop) * scale)))
            if box[2] <= box[0] or box[3] <= box[1]:
                continue
            buffer = io.BytesIO()
            rendered.crop(box).convert("RGB").save(buffer, format="JPEG", quality=JPEG_QUALITY)
            region.jpeg = buffer.getvalue()
            kept.append(region)
            count += 1
        page_regions[:] = kept
        if kept:
            warnings.append(f"Page {number}: {len(kept)} region(s) without extractable text exported as JPEG "
                            "image blocks (not read, no OCR).")


def _oz_column(lines: list[_Line]) -> float | None:
    starts = Counter(round(l.x0) for l in lines if OZ_PATTERN.match(l.words[0].text) and "." in l.words[0].text.strip("."))
    if not starts:
        return None
    column, _ = max(starts.items(), key=lambda kv: (kv[1], -kv[0]))
    return float(column)


def _is_price_word(word: _Word) -> bool:
    return bool(PLACEHOLDER_PATTERN.match(word.text) or re.fullmatch(r"-?\d{1,3}(?:\.\d{3})*,\d{2,}|-?\d+,\d{2,}", word.text))


def _quantity_line(words: list[_Word], width: float) -> dict | None:
    """Parse ``<quantity> [<unit>] <price fields>`` or an empty ``___ ____`` quantity line."""
    if not words or not any(_is_price_word(w) and w.x0 >= width * PRICE_X_SHARE for w in words):
        return None
    if all(PLACEHOLDER_PATTERN.match(w.text) for w in words):
        return {"quantity": None, "unit": None, "prices": [], "nep": any(w.text.upper() == "*NEP*" for w in words)}
    if not QUANTITY_PATTERN.match(words[0].text):
        return None
    rest = words[1:]
    unit_words = []
    while rest and not _is_price_word(rest[0]):
        unit_words.append(rest.pop(0))
    if len(unit_words) > 2 or any(len(w.text) > 10 for w in unit_words):
        return None
    if not all(_is_price_word(w) for w in rest):
        return None
    prices = [_number(w.text) for w in rest if not PLACEHOLDER_PATTERN.match(w.text)]
    return {"quantity": _number(words[0].text), "unit": " ".join(w.text for w in unit_words) or None,
            "prices": prices, "nep": any(w.text.upper() == "*NEP*" for w in rest)}


def _number(text: str) -> float:
    value = float(text.replace(".", "").replace(",", "."))
    if not math.isfinite(value):
        raise ValueError("A number in the PDF is outside the supported range.")
    return value


def _segment(items: list, oz_column: float) -> list[tuple[str, object, _Entry | None]]:
    """Walk lines and regions in reading order; return events (part, item, entry)."""
    events: list[tuple[str, object, _Entry | None]] = []
    current: _Entry | None = None
    line_event: dict[int, int] = {}
    seen_oz: set[str] = set()

    def close():
        """BoQs printed without price fields: the last bare ``<quantity> <unit>`` line of a position
        is its quantity line; text after it is free text, as after any other quantity line."""
        if current is None or current.kind != "oz" or current.has_quantity_line or not current.lines:
            return
        for index in range(len(current.lines) - 1, -1, -1):
            line = current.lines[index]
            words = line.words
            if (len(words) == 2 and QUANTITY_PATTERN.match(words[0].text) and UNIT_PATTERN.match(words[1].text)) or \
                    (len(words) == 1 and QUANTITY_PATTERN.match(words[0].text) and "," in words[0].text):
                _apply_quantity(current, {"quantity": _number(words[0].text),
                                          "unit": words[1].text if len(words) == 2 else None, "prices": [], "nep": False})
                events[line_event[id(line)]] = ("quantity", line, current)
                for after in current.lines[index + 1:]:
                    events[line_event[id(after)]] = ("text", after, None)
                del current.lines[index:]
                return

    for item in items:
        if isinstance(item, _Region):
            events.append(("image", item, current))
            continue
        line: _Line = item
        first = line.words[0]
        at_oz_column = abs(line.x0 - oz_column) <= OZ_COLUMN_TOLERANCE
        if current is not None and current.kind == "oz" and not current.has_quantity_line:
            quantity = _quantity_line(line.words, line.page_width)
            if quantity is not None and not (at_oz_column and OZ_PATTERN.match(first.text)):
                _apply_quantity(current, quantity)
                events.append(("quantity", line, current))
                current = None
                continue
        if at_oz_column and OZ_PATTERN.match(first.text):
            rest = line.words[1:]
            quantity = _quantity_line(rest, line.page_width) if rest else None
            priced = quantity is None and any(_is_price_word(w) and w.x0 >= line.page_width * PRICE_X_SHARE for w in rest)
            if priced and (first.text in seen_oz or "." not in first.text.strip(".")):
                close()
                events.append(("total", line, None))  # summary line such as "1 Earthworks ____"
                current = None
                continue
            close()
            seen_oz.add(first.text)
            current = _Entry(kind="oz", oz=first.text, head_line=line)
            if quantity is not None:
                _apply_quantity(current, quantity)
            else:
                current.head = [w for w in rest if not (priced and _is_price_word(w))]
            events.append(("head", line, current))
            continue
        if TOTAL_PATTERN.match(line.text):
            close()
            events.append(("total", line, None))
            current = None
            continue
        if at_oz_column and current is not None and current.kind == "oz" and line.text.strip().lower() in MARKERS:
            kind = MARKERS[line.text.strip().lower()]
            if kind:
                current.markers.add(kind)
            events.append(("marker", line, current))
            continue
        if at_oz_column and NOTE_PATTERN.match(line.text):
            close()
            current = _Entry(kind="note")
            events.append(("note", line, current))
            continue
        if current is not None and not current.has_quantity_line:
            current.lines.append(line)
            line_event[id(line)] = len(events)
            events.append(("line", line, current))
        else:
            events.append(("text", line, current if current is not None and current.kind == "note" else None))
    close()
    return events


def _apply_quantity(entry: _Entry, quantity: dict) -> None:
    entry.has_quantity_line = True
    entry.quantity, entry.unit = quantity["quantity"], quantity["unit"]
    if len(quantity["prices"]) == 2:
        entry.unit_price, entry.total_price = quantity["prices"]
    if quantity["nep"]:
        entry.markers.add("bedarf")


def _segments(oz: str) -> list[str]:
    return [s for s in re.split(r"\D+", oz) if s]


def _shape(oz: str | None) -> tuple[str, ...]:
    """Separator pattern of an OZ: ``8...3`` -> ``("...",)``, ``01.0010`` -> ``(".",)``."""
    return tuple(re.findall(r"\D+", (oz or "").rstrip(".")))


def _classify(entries: list[_Entry], warnings: list[str]) -> None:
    """Position if it has a quantity line, or if its OZ has the shape of positions that do;
    title if it is the ancestor of the next OZ entry; otherwise plain text (dates, numbered remarks)."""
    shapes = {_shape(e.oz) for e in entries if e.has_quantity_line}
    if not shapes:
        depth = max((len(_segments(e.oz)) for e in entries), default=0)
        shapes = {_shape(e.oz) for e in entries if len(_segments(e.oz)) == depth}
    for index, entry in enumerate(entries):
        following = entries[index + 1] if index + 1 < len(entries) else None
        parent_of_next = following is not None and _is_ancestor(entry.oz, following.oz)
        if entry.has_quantity_line or (_shape(entry.oz) in shapes and not parent_of_next):
            entry.role = "position"
            if not entry.has_quantity_line:
                warnings.append(f"OZ {entry.oz}: no quantity line found; quantity and unit stay empty.")
        elif parent_of_next:
            entry.role = "title"
        else:
            entry.role = "text"
        entry.short_lines = _short_lines(entry)


def _is_ancestor(parent: str | None, child: str | None) -> bool:
    a, b = _segments(parent or ""), _segments(child or "")
    return len(a) < len(b) and b[:len(a)] == a


def _short_lines(entry: _Entry) -> set[int]:
    """Short text: rest of the OZ line plus directly following lines in the same font and size."""
    lines = entry.lines
    if entry.head:
        reference, previous, chosen = entry.head[0], entry.head_line, set()
        for line in lines:
            if line.page != previous.page or line.words[0].font != reference.font or abs(line.size - reference.size) > 0.3:
                break
            if line.top - previous.top > 1.5 * max(previous.size, line.size):
                break
            chosen.add(id(line))
            previous = line
        return chosen
    if entry.role != "position" or not lines:
        return set()
    chosen, previous = {id(lines[0])}, lines[0]
    for line in lines[1:]:
        if line.page != previous.page or line.top - previous.top > 1.5 * max(previous.size, line.size):
            break
        chosen.add(id(line))
        previous = line
    return chosen


def _join_long(lines: list[_Line]) -> str:
    parts, previous = [], None
    for line in lines:
        if previous is not None:
            gap = line.top - previous.top
            parts.append("\n\n" if line.page == previous.page and gap > 1.5 * max(previous.size, line.size) else "\n")
        parts.append(line.text)
        previous = line
    return "".join(parts)


def _build_lv(dateiname: str, entries: list[_Entry], body: list[list[_Line]], warnings: list[str]) -> LV:
    titles: list[_Entry] = []
    positions, seen = [], Counter()
    for entry in entries:
        if entry.role == "text":
            continue
        if entry.role == "title":
            while titles and not _is_ancestor(titles[-1].oz, entry.oz):
                titles.pop()
            titles.append(entry)
            continue
        while titles and not _is_ancestor(titles[-1].oz, entry.oz):
            titles.pop()
        short = [w.text for w in entry.head] + [l.text for l in entry.lines if id(l) in entry.short_lines]
        long_lines = [l for l in entry.lines if id(l) not in entry.short_lines]
        path = [_title_text(t) for t in titles]
        kurztext = " ".join(short).strip()
        unit = entry.unit
        typ = "normal"
        if "bedarf" in entry.markers:
            typ = "bedarf"
        elif "alternativ" in entry.markers:
            typ = "alternativ"
        elif unit and unit.lower() in LUMP_SUM_UNITS:
            typ = "pauschal"
        elif any(re.search(r"stundenlohn|regie", p, re.I) for p in path):
            typ = "stundenlohn"
        elif re.match(r"zulage\b", kurztext, re.I):
            typ = "zulage"
        seen[entry.oz] += 1
        positions.append(Position(oz=entry.oz, kurztext=kurztext, langtext=_join_long(long_lines),
                                  menge=entry.quantity, einheit=unit, ep=entry.unit_price, gp=entry.total_price,
                                  typ=typ, titel_pfad=path))
    duplicates = sorted(oz for oz, count in seen.items() if count > 1)
    if duplicates:
        warnings.append("Duplicate OZ in the PDF: " + ", ".join(duplicates) + ".")
    # Name: the clearly largest line on the first text page (a cover title), else the file name.
    sizes = Counter(round(l.size) for ls in body for l in ls)
    body_size = sizes.most_common(1)[0][0] if sizes else 0
    first_page = next((ls for ls in body if ls), [])
    name_line = max(first_page, key=lambda l: l.size, default=None)
    name = name_line.text.strip() if name_line is not None and name_line.size >= body_size + 2 else ""
    return LV(name=name or Path(dateiname).stem or "PDF BoQ", quelle=dateiname or "upload.pdf",
              positionen=positions, summen={})


def _title_text(entry: _Entry) -> str:
    parts = [entry.oz or ""] + [w.text for w in entry.head] + [l.text for l in entry.lines if id(l) in entry.short_lines]
    return " ".join(p for p in parts if p).strip()


def _build_blocks(events: list[tuple[str, object, _Entry | None]]) -> list[Block]:
    """Merge consecutive lines with the same entry and role into paragraph blocks; keep images in place."""
    blocks: list[Block] = []
    pending: dict | None = None

    def emit(kind, role, page, bbox, text="", oz=None, jpeg=None, source=""):
        blocks.append(Block(index=len(blocks), page=page, bbox=bbox, kind=kind, role=role, text=text, oz=oz,
                            jpeg=jpeg, source=source))

    def flush():
        nonlocal pending
        if pending is not None:
            lines = pending["lines"]
            bbox = (min(l.bbox[0] for l in lines), min(l.top for l in lines),
                    max(l.bbox[2] for l in lines), max(l.bottom for l in lines))
            separator = " " if pending["role"] in ("short_text", "title") else "\n"
            emit("text", pending["role"], lines[0].page, bbox, separator.join(l.text for l in lines), pending["oz"])
            pending = None

    def add(role, line, entry, oz, mergeable=True):
        nonlocal pending
        last = pending["lines"][-1] if pending is not None else None
        if (mergeable and pending is not None and pending["role"] == role and pending["entry"] is entry
                and last.page == line.page and line.top - last.top <= 1.5 * max(last.size, line.size)):
            pending["lines"].append(line)
            return
        flush()
        pending = {"role": role, "oz": oz, "entry": entry, "lines": [line]}
        if not mergeable:
            flush()

    for part, item, entry in events:
        if entry is not None and entry.role == "text":
            entry, part = None, ("text" if part in ("head", "line") else part)
        oz = entry.oz if entry is not None and entry.kind == "oz" else None
        if part == "image":
            flush()
            emit("image", "image", item.page, item.bbox, oz=oz, jpeg=item.jpeg, source=item.source)
        elif part == "head":
            words = item.words
            add("oz", _Line(item.page, words[:1], item.page_width, item.page_height), entry, oz, mergeable=False)
            if entry.head:
                role = "title" if entry.role == "title" else "short_text"
                add(role, _Line(item.page, entry.head, item.page_width, item.page_height), entry, oz)
            elif len(words) > 1:
                add("quantity", _Line(item.page, words[1:], item.page_width, item.page_height), entry, oz, mergeable=False)
        elif part in ("quantity", "total", "marker"):
            add(part, item, entry, oz, mergeable=False)
        else:
            add(_role(part, item, entry), item, entry, oz)
    flush()
    return blocks


def _role(part: str, line: _Line, entry: _Entry | None) -> str:
    if part == "note" or (entry is not None and entry.kind == "note"):
        return "note"
    if part == "line" and entry is not None:
        if entry.role == "title":
            return "title" if id(line) in entry.short_lines else "note"
        return "short_text" if id(line) in entry.short_lines else "long_text"
    return "text"

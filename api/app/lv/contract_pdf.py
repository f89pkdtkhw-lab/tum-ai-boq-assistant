import json
import re
import sys
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any
import pymupdf as fitz


# Support 2 to 4 decimal places (German LVs frequently use 3 or 4 decimals for unit prices)
NUM_RE = re.compile(r"^\d{1,3}(?:\.\d{3})*,\d{2,4}$")
# Support both 3-level (1.1.5) and 4-level (5.2.1.1) position numbers
POS_RE = re.compile(r"^(\d+(?:\.\d+){2,3})$")
SEC_RE = re.compile(r"^(\d+(?:\.\d+)?)$")
UNIT_RE = re.compile(
    r"^(m2|m²|m3|m³|m|St|Stück|Stk|psch|Pausch|h|Std|d|Tag|Wo|MWo|StWo|mWo|m2d|m2Wo|m3d|kg|t|l|lfm|Paar|Satz|VE|Mon|md)$",
    re.IGNORECASE,
)


def parse_german_float(val_str: str) -> Optional[float]:
    """Converts a German formatted number '1.234,56' -> 1234.56."""
    if not val_str:
        return None
    cleaned = re.sub(r"[^\d,.-]", "", val_str.strip())
    if not cleaned:
        return None
    cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def detect_vector_checkboxes(page: fitz.Page) -> List[Tuple[fitz.Rect, bool]]:
    """Detects checkboxes drawn as vector squares + diagonal X-lines in PDF drawings."""
    widget_boxes: List[Tuple[fitz.Rect, bool]] = []
    try:
        for widget in page.widgets():
            if widget.field_type == fitz.PDF_WIDGET_TYPE_CHECKBOX:
                is_checked = bool(widget.field_value) and str(widget.field_value).lower() not in (
                    "off", "false", "0", "no"
                )
                widget_boxes.append((widget.rect, is_checked))
    except Exception:
        pass

    try:
        drawings = page.get_drawings()
    except Exception:
        return widget_boxes

    boxes: List[fitz.Rect] = []
    diagonals: List[Tuple[fitz.Point, fitz.Point]] = []

    for d in drawings:
        rect = d.get("rect")
        if rect and 7.0 <= rect.width <= 16.0 and 7.0 <= rect.height <= 16.0:
            if abs(rect.width - rect.height) <= 2.5:
                boxes.append(rect)

        for item in d.get("items", []):
            if item[0] == "l":
                p1, p2 = item[1], item[2]
                if abs(p1.x - p2.x) > 4.0 and abs(p1.y - p2.y) > 4.0:
                    diagonals.append((p1, p2))

    unique_boxes: List[fitz.Rect] = []
    for b in boxes:
        if not any(abs(b.x0 - ub.x0) < 2 and abs(b.y0 - ub.y0) < 2 for ub in unique_boxes):
            unique_boxes.append(b)

    for b in unique_boxes:
        expanded = fitz.Rect(b.x0 - 1.5, b.y0 - 1.5, b.x1 + 1.5, b.y1 + 1.5)
        diag_hits = sum(
            1 for p1, p2 in diagonals if expanded.contains(p1) and expanded.contains(p2)
        )
        widget_boxes.append((b, diag_hits >= 1))

    return widget_boxes


def extract_contract_lines_with_geometry(
    page: fitz.Page, y_tolerance: float = 3.5
) -> List[Dict[str, Any]]:
    """
    Reconstructs visual lines on contract pages along with their X-indentation (x0)
    and checkbox state ('checked', 'unchecked', or None).
    """
    checkboxes = detect_vector_checkboxes(page)
    words = page.get_text("words")
    if not words:
        return []

    words_sorted = sorted(words, key=lambda w: (round(w[1], 1), w[0]))
    grouped: List[List[Tuple]] = []

    for w in words_sorted:
        if not grouped:
            grouped.append([w])
            continue
        avg_y = sum(item[1] for item in grouped[-1]) / len(grouped[-1])
        if abs(w[1] - avg_y) <= y_tolerance:
            grouped[-1].append(w)
        else:
            grouped.append([w])

    rendered: List[Dict[str, Any]] = []
    for line_words in grouped:
        line_words.sort(key=lambda w: w[0])
        line_y0 = line_words[0][1]
        line_x0 = line_words[0][0]

        cb_state: Optional[str] = None
        for cb_rect, is_checked in checkboxes:
            if abs(cb_rect.y0 - line_y0) < 8.0 and cb_rect.x0 <= line_x0 + 12.0:
                cb_state = "checked" if is_checked else "unchecked"
                break

        raw_text = " ".join(w[4] for w in line_words).strip()
        if not raw_text:
            continue

        prefix = "[☑] " if cb_state == "checked" else ("[☐] " if cb_state == "unchecked" else "")
        rendered.append(
            {
                "text": (prefix + raw_text).strip(),
                "raw_text": raw_text,
                "x0": line_x0,
                "cb_state": cb_state,
            }
        )

    return rendered


def check_is_vertrag(first_page_lines: List[Dict[str, Any]]) -> bool:
    """Checks whether the first page indicates a contract document."""
    joined = " ".join(item["raw_text"] for item in first_page_lines).lower()
    return any(kw in joined for kw in ("vertrag", "vertragsbedingungen", "angebotsschreiben"))


def extract_vergabenummer(pages_lines: List[List[Dict[str, Any]]]) -> Optional[str]:
    """Extracts Vergabenummer from the first few pages."""
    joined = "\n".join(item["raw_text"] for page in pages_lines for item in page)
    match = re.search(r"Vergabenummer\s*\n?\s*\[?([A-Z0-9_-]+)\]?", joined, re.IGNORECASE)
    if match:
        return match.group(1).strip("[]")
    return None


def parse_contract_requirements(pages_lines: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """
    Parses contract clauses and checkbox options prior to the Leistungsverzeichnis.
    Keeps all checked [☑] options under the same prompt until a new non-checkbox
    prompt/header appears (so nested [☑] after an intermediate [☐] stay grouped).
    """
    requirements: List[Dict[str, Any]] = []
    prompt_buffer: List[str] = []
    checked_options: List[str] = []
    active_cb_state: Optional[str] = None
    min_cb_x0: Optional[float] = None
    active_cb_x0: float = 0.0

    def flush_group():
        nonlocal prompt_buffer, checked_options, active_cb_state, min_cb_x0
        if checked_options:
            requirements.append(
                {
                    "prompt": "\n".join(prompt_buffer).strip(),
                    "selected_options": checked_options.copy(),
                }
            )
        prompt_buffer = []
        checked_options = []
        active_cb_state = None
        min_cb_x0 = None

    for page_lines in pages_lines:
        joined_page = " ".join(item["raw_text"] for item in page_lines)
        if "Pos-Nr." in joined_page and "Einheitspreis" in joined_page:
            flush_group()
            break

        for item in page_lines:
            text = item["text"]
            raw = item["raw_text"]
            x0 = item["x0"]
            cb_state = item["cb_state"]

            if (
                raw.startswith(("© VHB", "VHB Bayern"))
                or re.match(r"^\d+\s+von\s+\d+$", raw)
            ):
                continue

            is_sec_header = (
                cb_state is None
                and re.match(r"^(\d+(?:\.\d+)?)\s+([A-ZÄÖÜ].{3,})$", raw) is not None
            )
            if is_sec_header:
                flush_group()
                prompt_buffer = [raw]
                continue

            if cb_state == "checked":
                active_cb_state = "checked"
                active_cb_x0 = x0
                if min_cb_x0 is None or x0 < min_cb_x0:
                    min_cb_x0 = x0
                checked_options.append(text)
                continue

            if cb_state == "unchecked":
                active_cb_state = "unchecked"
                active_cb_x0 = x0
                if min_cb_x0 is None or x0 < min_cb_x0:
                    min_cb_x0 = x0
                continue

            if active_cb_state is not None:
                indent_threshold = (min_cb_x0 if min_cb_x0 is not None else active_cb_x0) - 3.0
                if x0 >= indent_threshold:
                    if active_cb_state == "checked" and checked_options:
                        checked_options[-1] += "\n" + raw
                    continue
                else:
                    flush_group()

            prompt_buffer.append(raw)

    flush_group()
    return requirements


def detect_lv_column_layout(rows: List[List[Tuple]], page_width: float) -> Dict[str, float]:
    """
    Determines X-centers and boundaries for Menge, Einheit, Einheitspreis, and Gesamtpreis
    from the page's table header and actual numeric/unit rows.
    """
    header_x: Dict[str, float] = {}
    for row in rows[:15]:
        row_str = " ".join(w[4] for w in row)
        if "Menge" in row_str and ("Einheitspreis" in row_str or "Gesamtpreis" in row_str):
            for w in row:
                txt = w[4]
                cx = (w[0] + w[2]) / 2.0
                if txt == "Menge":
                    header_x["menge"] = cx
                elif txt == "Einheit":
                    header_x["einheit"] = cx
                elif txt.startswith("Einheitspreis"):
                    header_x["ep"] = cx
                elif txt.startswith("Gesamtpreis"):
                    header_x["gp"] = cx
            break

    numeric_start_x0s: List[float] = []
    for row in rows:
        if len(row) >= 2 and NUM_RE.match(row[-1][4].rstrip("*€")) and row[-1][0] > page_width * 0.72:
            for w in row:
                tok_clean = w[4].rstrip("*€")
                if w[0] > page_width * 0.38 and (NUM_RE.match(tok_clean) or UNIT_RE.match(w[4])):
                    numeric_start_x0s.append(w[0])
                    break

    if numeric_start_x0s:
        desc_max = min(numeric_start_x0s) - 6.0
    else:
        desc_max = header_x.get("menge", page_width * 0.50) - 35.0

    return {
        "pos_max": page_width * 0.13,
        "desc_max": desc_max,
        "menge": header_x.get("menge", desc_max + 25.0),
        "einheit": header_x.get("einheit", desc_max + 65.0),
        "ep": header_x.get("ep", page_width * 0.78),
        "gp": header_x.get("gp", page_width * 0.91),
    }


def is_footer_or_header_row(row: List[Tuple], page_height: float) -> bool:
    """Filters out page headers, footers, page numbers, and firm stamps."""
    if not row:
        return True
    y0 = row[0][1]
    row_text = " ".join(w[4] for w in row).strip()

    if y0 > page_height * 0.92:
        return True

    skip_phrases = (
        "LV: RINGSCHLUSS",
        "Pos-Nr.",
        "LV-Datum:",
        "Einheitspreis in",
        "Gesamtpreis in",
        "Gesamtbetrag:",
        "Seite:",
        "Übertrag:",
        "Zwischensumme",
    )
    if any(p in row_text for p in skip_phrases):
        return True

    if re.fullmatch(r"\[FIRMA_\d+\]", row_text):
        return True

    return False


def split_lv_row(
    row: List[Tuple], centers: Dict[str, float], page_width: float
) -> Tuple[List[str], List[str], List[Tuple[float, str]]]:
    """
    Splits a visual row into pos_tokens, desc_tokens, and right-hand numeric/unit tokens.
    """
    pos_toks: List[str] = []
    remaining: List[Tuple] = []

    for w in row:
        if w[2] <= centers["pos_max"]:
            pos_toks.append(w[4])
        else:
            remaining.append(w)

    if not remaining:
        return pos_toks, [], []

    split_idx = len(remaining)
    last_clean = remaining[-1][4].rstrip("*€")
    if NUM_RE.match(last_clean) and remaining[-1][0] > page_width * 0.70:
        idx = len(remaining) - 1
        while idx >= 0:
            w = remaining[idx]
            txt_clean = w[4].rstrip("*€")
            if NUM_RE.match(txt_clean) or UNIT_RE.match(w[4]) or w[0] >= centers["desc_max"]:
                split_idx = idx
                idx -= 1
            else:
                break
    else:
        for idx, w in enumerate(remaining):
            if w[0] >= centers["desc_max"]:
                split_idx = idx
                break

    desc_toks = [w[4] for w in remaining[:split_idx]]
    right_toks = [((w[0] + w[2]) / 2.0, w[4]) for w in remaining[split_idx:]]
    return pos_toks, desc_toks, right_toks


def parse_lv_and_zusammenstellung(
    doc: fitz.Document,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Parses all Leistungsverzeichnis items and the final Zusammenstellung summary table.
    """
    items: List[Dict[str, Any]] = []
    zusammenstellung_sections: Dict[str, Dict[str, Any]] = {}
    zusammenstellung_totals: Dict[str, Optional[float]] = {}

    current_item: Optional[Dict[str, Any]] = None
    in_zusammenstellung = False

    for page_num in range(len(doc)):
        page = doc[page_num]
        page_width = page.rect.width
        page_height = page.rect.height
        words = page.get_text("words")
        if not words:
            continue

        full_page_text = page.get_text("text")
        if "Zusammenstellung" in full_page_text:
            in_zusammenstellung = True
            if current_item:
                items.append(current_item)
                current_item = None

        if not in_zusammenstellung and "Pos-Nr." not in full_page_text:
            continue

        words.sort(key=lambda w: (round(w[1] / 3.0), w[0]))
        rows: List[List[Tuple]] = []
        current_row: List[Tuple] = []
        last_y: Optional[float] = None
        for w in words:
            if last_y is None or abs(w[1] - last_y) <= 3.5:
                current_row.append(w)
            else:
                current_row.sort(key=lambda item: item[0])
                rows.append(current_row)
                current_row = [w]
            last_y = w[1]
        if current_row:
            current_row.sort(key=lambda item: item[0])
            rows.append(current_row)

        centers = detect_lv_column_layout(rows, page_width)

        for row in rows:
            if is_footer_or_header_row(row, page_height):
                continue

            row_text = " ".join(w[4] for w in row).strip()

            # --- FINAL SUMMARY TABLE (ZUSAMMENSTELLUNG) ---
            if in_zusammenstellung:
                pos_toks = [w[4] for w in row if w[2] <= centers["pos_max"]]
                desc_toks = [
                    w[4] for w in row if centers["pos_max"] < w[2] <= centers["ep"] - 30.0
                ]
                right_nums = [
                    w[4]
                    for w in row
                    if w[0] >= centers["ep"] - 30.0 and NUM_RE.match(w[4].rstrip("*€"))
                ]

                if "Summe Brutto" in row_text and right_nums:
                    zusammenstellung_totals["summe_brutto"] = parse_german_float(right_nums[-1])
                elif "USt" in row_text and right_nums:
                    zusammenstellung_totals["ust_19_percent"] = parse_german_float(right_nums[-1])
                elif ("Summe:" in row_text or row_text.startswith("Summe")) and "Brutto" not in row_text:
                    if right_nums:
                        zusammenstellung_totals["summe_netto"] = parse_german_float(right_nums[-1])
                elif pos_toks and SEC_RE.match(pos_toks[0]) and right_nums:
                    sec_id = pos_toks[0]
                    sec_sum = parse_german_float(right_nums[-1])
                    if sec_sum is not None:
                        zusammenstellung_sections[sec_id] = {
                            "title": " ".join(desc_toks).strip(),
                            "expected_total": sec_sum,
                        }
                continue

            # --- LEISTUNGSVERZEICHNIS LINE ITEMS ---
            pos_toks, desc_toks, right_toks = split_lv_row(row, centers, page_width)
            pos_candidate = pos_toks[0] if pos_toks else ""

            # 1. New LV line item (e.g., 1.1.5 or 5.2.1.1)
            if POS_RE.match(pos_candidate):
                if current_item:
                    items.append(current_item)
                current_item = {
                    "pos_nr": pos_candidate,
                    "description": " ".join(desc_toks).strip(),
                    "quantity": None,
                    "unit": None,
                    "unit_price": None,
                    "total_price": None,
                }
                _extract_right_columns(current_item, right_toks, centers)
                continue

            # 2. Section or subsection header (e.g., "1" or "1.1") closes active item
            if SEC_RE.match(pos_candidate) and not right_toks:
                if current_item:
                    items.append(current_item)
                    current_item = None
                continue

            # 3. Continuation lines of the active LV item
            if current_item is not None:
                if desc_toks:
                    line_desc = " ".join(desc_toks).strip()
                    if line_desc:
                        current_item["description"] = (
                            (current_item["description"] + "\n" + line_desc).strip()
                        )
                if right_toks:
                    _extract_right_columns(current_item, right_toks, centers)

    if current_item:
        items.append(current_item)

    zusammenstellung_data = {
        "sections": zusammenstellung_sections,
        "totals": zusammenstellung_totals,
    }
    return items, zusammenstellung_data


def _extract_right_columns(
    item: Dict[str, Any],
    right_toks: List[Tuple[float, str]],
    centers: Dict[str, float],
) -> None:
    """
    Extracts quantity, unit, unit_price, and total_price from right-hand column tokens
    in left-to-right order.
    """
    sorted_toks = sorted(right_toks, key=lambda t: t[0])

    nums: List[Tuple[float, float]] = []
    for cx, tok in sorted_toks:
        tok_clean = tok.rstrip("*€")
        if NUM_RE.match(tok_clean):
            val = parse_german_float(tok_clean)
            if val is not None:
                nums.append((cx, val))
        elif UNIT_RE.match(tok):
            item["unit"] = tok

    if len(nums) == 3:
        item["quantity"] = nums[0][1]
        item["unit_price"] = nums[1][1]
        item["total_price"] = nums[2][1]
    elif len(nums) == 2:
        if nums[0][0] < (centers["menge"] + centers["ep"]) / 2.0:
            item["quantity"] = nums[0][1]
            if nums[1][0] < (centers["ep"] + centers["gp"]) / 2.0:
                item["unit_price"] = nums[1][1]
            else:
                item["total_price"] = nums[1][1]
        else:
            item["unit_price"] = nums[0][1]
            item["total_price"] = nums[1][1]
    elif len(nums) == 1:
        cx, val = nums[0]
        col_keys = ("menge", "ep", "gp")
        nearest = min(col_keys, key=lambda k: abs(cx - centers[k]))
        if nearest == "menge":
            item["quantity"] = val
        elif nearest == "ep":
            item["unit_price"] = val
        else:
            item["total_price"] = val


def reconcile_with_zusammenstellung(
    items: List[Dict[str, Any]], zusam_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Cross-checks all parsed LV items against the final Zusammenstellung summary table.
    """
    item_math_errors = []
    missing_price_positions = []
    calculated_grand_total = 0.0

    for it in items:
        q = it["quantity"]
        ep = it["unit_price"]
        gp = it["total_price"]
        if gp is None:
            missing_price_positions.append(it["pos_nr"])
        else:
            calculated_grand_total += gp
        if q is not None and ep is not None and gp is not None:
            expected_gp = round(q * ep, 2)
            if abs(expected_gp - gp) > 0.02:
                item_math_errors.append(
                    {
                        "pos_nr": it["pos_nr"],
                        "quantity": q,
                        "unit": it["unit"],
                        "unit_price": ep,
                        "expected_total": expected_gp,
                        "parsed_total": gp,
                    }
                )

    section_comparisons = {}
    for sec_id, sec_info in zusam_data.get("sections", {}).items():
        prefix = sec_id + "."
        sec_items = [it for it in items if it["pos_nr"].startswith(prefix)]
        calc_sum = round(sum(it["total_price"] or 0.0 for it in sec_items), 2)
        exp_sum = sec_info["expected_total"]
        diff = round(calc_sum - exp_sum, 2)
        section_comparisons[sec_id] = {
            "title": sec_info["title"],
            "items_count": len(sec_items),
            "calculated_sum": calc_sum,
            "zusammenstellung_sum": exp_sum,
            "difference": diff,
            "is_match": abs(diff) <= 0.05,
        }

    expected_netto = zusam_data.get("totals", {}).get("summe_netto")
    calculated_grand_total = round(calculated_grand_total, 2)
    grand_diff = (
        round(calculated_grand_total - expected_netto, 2)
        if expected_netto is not None
        else None
    )

    return {
        "total_items_parsed": len(items),
        "calculated_summe_netto": calculated_grand_total,
        "zusammenstellung_summe_netto": expected_netto,
        "zusammenstellung_ust": zusam_data.get("totals", {}).get("ust_19_percent"),
        "zusammenstellung_summe_brutto": zusam_data.get("totals", {}).get("summe_brutto"),
        "grand_total_difference": grand_diff,
        "grand_total_match": (abs(grand_diff) <= 0.05) if grand_diff is not None else None,
        "missing_price_positions": missing_price_positions,
        "section_comparisons": section_comparisons,
        "item_math_mismatches": item_math_errors,
    }


def parse_pdf(pdf_path: str) -> Dict[str, Any]:
    fitz.TOOLS.mupdf_display_errors(False)
    path = Path(pdf_path)
    doc = fitz.open(path)

    intro_pages_lines = [
        extract_contract_lines_with_geometry(doc[i]) for i in range(min(len(doc), 20))
    ]
    first_page_lines = intro_pages_lines[0] if intro_pages_lines else []

    is_vertrag = check_is_vertrag(first_page_lines)
    vergabenummer = extract_vergabenummer(intro_pages_lines[:5])

    positions, zusam_data = parse_lv_and_zusammenstellung(doc)
    reconciliation = reconcile_with_zusammenstellung(positions, zusam_data)

    result: Dict[str, Any] = {
        "filename": path.name,
        "source_format": "pdf",
        "document_role": "vertrag" if is_vertrag else "unknown",
        "Vergabenummer": vergabenummer,
        "currency": "EUR",
        "requirements": parse_contract_requirements(intro_pages_lines) if is_vertrag else [],
        "positions": positions,
        "zusammenstellung_reconciliation": reconciliation,
    }

    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python parse_vertrag_lv.py <path_to_pdf> [output_json]")
        sys.exit(1)

    input_pdf = sys.argv[1]
    output_json = (
        sys.argv[2]
        if len(sys.argv) > 2
        else Path(input_pdf).with_suffix(".parsed.json")
    )

    parsed_data = parse_pdf(input_pdf)

    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(parsed_data, f, ensure_ascii=False, indent=2)

    rec = parsed_data["zusammenstellung_reconciliation"]
    print(f"Done! Saved to: {output_json}")
    print(
        f"Document role: {parsed_data['document_role']} | Vergabenummer: {parsed_data['Vergabenummer']}"
    )
    print(f"Checked requirements found: {len(parsed_data['requirements'])}")
    print(f"LV positions parsed: {rec['total_items_parsed']}")
    print(
        f"Netto reconciliation: calculated = {rec['calculated_summe_netto']} EUR | "
        f"Zusammenstellung = {rec['zusammenstellung_summe_netto']} EUR | "
        f"diff = {rec['grand_total_difference']} EUR | "
        f"match: {rec['grand_total_match']}"
    )

    mismatched_sections = {
        sec_id: info
        for sec_id, info in rec["section_comparisons"].items()
        if not info["is_match"]
    }
    if mismatched_sections:
        print("\nSections with discrepancies:")
        for sec_id, info in mismatched_sections.items():
            print(
                f"  - Section {sec_id} ({info['title']}): "
                f"calc={info['calculated_sum']} vs expected={info['zusammenstellung_sum']} "
                f"(diff={info['difference']})"
            )
    if rec["missing_price_positions"]:
        print(f"\nPositions with missing total_price: {rec['missing_price_positions']}")
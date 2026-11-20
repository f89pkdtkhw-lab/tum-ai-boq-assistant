"""GAEB 90 records used by the dataset; unsupported records remain in raw bytes."""
import base64
import hashlib
import re
from .schemas import BoQDocument, Evidence, Item, RawContent, Source, TextValue
from .gaeb import decimal_value


def parse_legacy(filename: str, content: bytes) -> BoQDocument:
    # GAEB 90 uses the DOS character set; no replacement decoding is needed.
    lines = content.decode("cp850").splitlines()
    header = next(((i, line) for i, line in enumerate(lines, 1) if line.startswith("00")), None)
    if not header or any(len(line) != 80 for line in lines):
        raise ValueError("Invalid GAEB 90 file. Expected 80-column records and an opening record.")
    header_line, opening = header
    mask = opening[62:71]
    if not re.fullmatch(r"[1-5PI ]{9}", mask) or "P" not in mask:
        raise ValueError("Unsupported GAEB 90 item-number mask.")
    parts = [(m.start(), m.end(), m.group()[0]) for m in re.finditer(r"(.)\1*", mask) if m.group()[0] != " "]
    def traced(value, line, start, end, original=None):
        return TextValue(value=value, original=value if original is None else original,
                         sources=[Source(file=filename, line=line, path=f"columns[{start + 1}:{end}]")])
    def oz(raw, line):
        codes = []
        for start, end, kind in parts:
            fragment = raw[start:end].strip()
            if fragment:
                if kind == "I":
                    if codes:
                        codes[-1] += fragment
                else:
                    codes.append(fragment.zfill(end - start) if fragment.isdigit() else fragment)
        if not codes:
            raise ValueError("GAEB 90 record has no original item number.")
        return traced(".".join(codes), line, 2, 11, raw)
    def number(raw, line, start, end, scale, price=False):
        if price and raw.strip():
            # EP consists of 10 cent digits plus an optional tenth-cent digit.
            numeric = raw[:10].strip() + (raw[10:11].strip() or "0")
        else:
            numeric = raw
        v = decimal_value(numeric, [Source(file=filename, line=line, path=f"columns[{start + 1}:{end}]")], scale)
        if v:
            v.original = raw
        return v
    items, titles, totals = [], [], {}
    current = None
    active_section = None
    def append_text(item, field, raw, line, end):
        v = traced(raw.rstrip(), line, 2, end, raw)
        previous = getattr(item, field)
        if previous:
            previous.value += "\n" + v.value
            previous.original += "\n" + raw
            previous.sources.extend(v.sources)
        else:
            setattr(item, field, v)
    for line_number, line in enumerate(lines, 1):
        tag, raw_oz = line[:2], line[2:11]
        if tag == "11":
            current = None
            code = oz(raw_oz, line_number)
            while titles and not code.value.startswith(titles[-1][0].value + "."):
                titles.pop()
            active_section = TextValue(value=code.value, original=raw_oz, sources=code.sources)
            titles.append((code, active_section))
        elif tag == "12" and active_section is not None:
            label = line[2:72].rstrip()
            active_section.value += " " + label
            active_section.original += "\n" + line[2:72]
            active_section.sources.append(Source(file=filename, line=line_number, path="columns[3:72]"))
        elif tag == "21":
            item_type = "alternativ" if line[11:12] == "A" else "bedarf" if line[12:13] in ("E", "M") else "normal"
            current = Item(oz=oz(raw_oz, line_number), quantity=number(line[23:34], line_number, 23, 34, 3),
                           unit=traced(line[34:38].strip(), line_number, 34, 38, line[34:38]) if line[34:38].strip() else None,
                           title_path=[title.model_copy(deep=True) for _, title in titles], kind=item_type)
            items.append(current)
        elif tag == "23":
            code = oz(raw_oz, line_number)
            if current is None or current.oz.value != code.value or current.unit_price is not None:
                current = Item(oz=code, title_path=[title.model_copy(deep=True) for _, title in titles])
                items.append(current)
            current.unit_price = number(line[12:23], line_number, 12, 23, 3, price=True)
            current.total_price = number(line[24:36], line_number, 24, 36, 2)
            if current.quantity is None:
                current.quantity = number(line[37:48], line_number, 37, 48, 3)
        elif tag in ("25", "26") and current is not None:
            end = 72 if tag == "25" else 57
            append_text(current, "short_text" if tag == "25" else "detailed_text", line[2:end], line_number, end)
        elif tag == "31":
            current = None
            active_section = None
            if titles:
                titles.pop()
        elif tag in ("20", "T0", "T9", "99"):
            current = None
    phase = traced(opening[10:12], header_line, 10, 12)
    return BoQDocument(source_file=filename, sha256=hashlib.sha256(content).hexdigest(),
                       phase=phase, evidence=[Evidence(rule="GAEB 90 exchange phase", value=phase)],
                       positions=items, section_totals=totals,
                       raw=RawContent(content=base64.b64encode(content).decode("ascii")),
                       warnings=["GAEB 90: unsupported records and section totals retained in raw; no values inferred."])

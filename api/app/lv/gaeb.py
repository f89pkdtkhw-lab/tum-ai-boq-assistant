"""Local GAEB parsing with original values and source paths; no model calls."""
import base64
import hashlib
import math
import re
from pathlib import Path
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree as ET
from ..modelle import LV, Position, PositionQuelle
from .schemas import BoQDocument, DecimalValue, Evidence, Item, RawContent, Source, TextValue


def local(element):
    return element.tag.rsplit("}", 1)[-1]


def child(element, name):
    return next((e for e in element if local(e) == name), None)


def descend(element, *names):
    for name in names:
        element = child(element, name) if element is not None else None
    return element


def readable(element):
    if element is None:
        return ""
    def walk(e):
        text = e.text or ""
        for c in e:
            tag = local(c).lower()
            if tag in ("p", "div", "li", "tr", "br", "page"):
                text += "\n"
            text += walk(c)
            if tag in ("p", "div", "li", "tr"):
                text += "\n"
            elif tag == "td":
                text += "\t"
            text += c.tail or ""
        return text
    return "\n".join(re.sub(r"[\t\r ]+", " ", line).strip()
                     for line in walk(element).splitlines() if line.strip())


def decimal_value(text, sources, scale=0):
    if not text.strip():
        return None
    try:
        number = Decimal(text.strip().replace(",", "."))
        if not number.is_finite():
            raise InvalidOperation
        if scale:
            number = number.scaleb(-scale)
    except (InvalidOperation, ValueError):
        raise ValueError("Invalid GAEB numeric value. Check quantities and prices.") from None
    return DecimalValue(value=format(number, "f"), original=text, sources=sources)


def parse_gaeb(dateiname: str, inhalt: bytes) -> BoQDocument:
    """Parse XML; the document export keeps every input byte, including unknown tags."""
    if Path(dateiname).suffix.lower() in (".d83", ".d84", ".d86"):
        from .gaeb90 import parse_legacy
        return parse_legacy(dateiname, inhalt)
    # Reject DTDs/entities before parsing, including UTF-16/32 representations.
    if re.search(br"<!\s*(DOCTYPE|ENTITY)\b", inhalt.replace(b"\x00", b""), re.I):
        raise ValueError("GAEB XML declarations with DTDs or entities are not supported.")
    try:
        root = ET.fromstring(inhalt)
    except (ET.ParseError, ValueError):
        raise ValueError("Invalid GAEB XML. Please upload a complete GAEB file.") from None
    if local(root) != "GAEB":
        raise ValueError("Invalid GAEB root. Expected a GAEB document.")
    award = child(root, "Award")
    boq = child(award, "BoQ") if award is not None else None
    if boq is None or child(boq, "BoQBody") is None:
        raise ValueError("GAEB document has no BoQ body.")
    paths = {}
    def index(e, path):
        paths[id(e)] = path
        counts = {}
        for c in e:
            tag = local(c)
            counts[tag] = counts.get(tag, 0) + 1
            index(c, f"{path}/{tag}[{counts[tag]}]")
    index(root, "/GAEB[1]")
    def value(e, attribute=None, rendered=None):
        if e is None:
            return None
        raw = e.attrib.get(attribute, "") if attribute else "".join(e.itertext())
        path = paths[id(e)] + ("/@" + attribute if attribute else "")
        return TextValue(value=rendered if rendered is not None else raw.strip(), original=raw,
                         sources=[Source(file=dateiname, path=path)])
    def number(e):
        v = value(e)
        return decimal_value(v.original, v.sources) if v else None
    info = child(boq, "BoQInfo")
    breakdown = [e for e in info if local(e) == "BoQBkdn"] if info is not None else []
    widths = []
    item_width = None
    for b in breakdown:
        type_ = readable(child(b, "Type"))
        length = readable(child(b, "Length"))
        if not length.isdigit() or int(length) > 14:
            raise ValueError("Invalid GAEB numbering breakdown.")
        if type_ in ("BoQLevel", "Lot"):
            widths.append(int(length))
        elif type_ == "Item":
            item_width = int(length)
    def part(e, width):
        raw = e.attrib.get("RNoPart", "").strip()
        if not raw:
            raise ValueError("GAEB section or item has no original item number.")
        return raw.zfill(width) if width and raw.isdigit() else raw
    items, totals = [], {}
    def visit(body, codes, titles):
        for e in body:
            tag = local(e)
            if tag == "BoQCtgy":
                code = part(e, widths[len(codes)] if len(codes) < len(widths) else None)
                label = value(child(e, "LblTx"), rendered=readable(child(e, "LblTx")))
                label_text = code + (" " + label.value if label and label.value else "")
                label_sources = value(e, "RNoPart").sources + (label.sources if label else [])
                title = TextValue(value=label_text, original=label.original if label else code, sources=label_sources)
                section_titles = titles + [title]
                nested = child(e, "BoQBody")
                if nested is not None:
                    visit(nested, codes + [code], section_titles)
                total = number(descend(e, "Totals", "Total"))
                if total is not None:
                    key = " / ".join(t.value for t in section_titles)
                    if key in totals:
                        raise ValueError("Duplicate GAEB section total path cannot be represented in LV.")
                    totals[key] = total
            elif tag == "Itemlist":
                for item in e:
                    if local(item) != "Item":
                        continue
                    item_code = part(item, item_width) + item.attrib.get("RNoIndex", "")
                    sources = [Source(file=dateiname, path=paths[id(item)] + "/@RNoPart")]
                    if "RNoIndex" in item.attrib:
                        sources.append(Source(file=dateiname, path=paths[id(item)] + "/@RNoIndex"))
                    # Section fragments also form the original OZ, not a new sequence.
                    sources = [s for t in titles for s in t.sources if s.path.endswith("/@RNoPart")] + sources
                    oz = TextValue(value=".".join(codes + [item_code]), original=item.attrib["RNoPart"], sources=sources)
                    desc = descend(item, "Description", "CompleteText")
                    short = descend(desc, "OutlineText")
                    detail = descend(desc, "DetailTxt")
                    kind = "normal"
                    if child(item, "LumpSumItem") is not None:
                        kind = "pauschal"
                    if child(item, "Provis") is not None:
                        kind = "bedarf"
                    items.append(Item(oz=oz, short_text=value(short, rendered=readable(short)),
                                      detailed_text=value(detail, rendered=readable(detail)),
                                      quantity=number(child(item, "Qty")), unit=value(child(item, "QU")),
                                      unit_price=number(child(item, "UP")), total_price=number(child(item, "IT")),
                                      title_path=titles, kind=kind))
    visit(child(boq, "BoQBody"), [], [])
    phase = value(child(award, "DP"))
    evidence = [Evidence(rule="GAEB structured BoQ", value=value(boq, rendered="BoQ"))]
    if phase:
        evidence = [Evidence(rule="GAEB exchange phase", value=phase)]
    return BoQDocument(source_file=dateiname, sha256=hashlib.sha256(inhalt).hexdigest(), evidence=evidence,
                       phase=phase, title=value(child(info, "Name")) if info is not None else None,
                       positions=items, section_totals=totals,
                       raw=RawContent(content=base64.b64encode(inhalt).decode("ascii")))


def _quelle(item: Item) -> PositionQuelle | None:
    """#170: GAEB XML element path of the item (from its own RNoPart source), or the GAEB 90 record line."""
    eigene = [s for s in item.oz.sources if s.path and s.path.endswith("/@RNoPart")]
    if eigene and eigene[-1].path.startswith("/GAEB"):
        return PositionQuelle(pfad=eigene[-1].path.removesuffix("/@RNoPart"))
    zeile = item.oz.sources[-1].line if item.oz.sources else None
    return PositionQuelle(zeile=zeile) if zeile else None


def to_lv(document: BoQDocument) -> LV:
    def number(value):
        if value is None:
            return None
        result = float(value.value)
        if not math.isfinite(result):
            raise ValueError("GAEB number is outside the supported LV numeric range.")
        return result
    return LV(name=document.title.value if document.title and document.title.value else document.source_file,
              quelle=document.source_file,
              positionen=[Position(oz=p.oz.value, kurztext=p.short_text.value if p.short_text else "",
                                   langtext=p.detailed_text.value if p.detailed_text else "",
                                   menge=number(p.quantity), einheit=p.unit.value if p.unit else None,
                                   ep=number(p.unit_price), gp=number(p.total_price), typ=p.kind,
                                   titel_pfad=[t.value for t in p.title_path], quelle=_quelle(p))
                         for p in document.positions],
              summen={key: number(value) for key, value in document.section_totals.items()})


def importiere(dateiname: str, inhalt: bytes) -> LV:
    return to_lv(parse_gaeb(dateiname, inhalt))

"""Synthetic XLSX fixtures for the Excel import tests (#9).

Everything here is invented; no real or confidential BoQ content. The builder writes a minimal
Office Open XML workbook by hand (shared strings, inline strings, numbers, formulas with and without
a cached result), so the tests need no Excel writer dependency. Output is byte-for-byte
deterministic, so `lv_synthetisch.xlsx` can be checked against `beispiel_lv()`.
"""
import io
import zipfile
from dataclasses import dataclass
from xml.sax.saxutils import escape

_DATUM = (2026, 11, 21, 0, 0, 0)


@dataclass(frozen=True)
class Formel:
    """A formula cell; `ergebnis=None` means Excel never stored a cached result."""
    formel: str
    ergebnis: float | None = None


@dataclass(frozen=True)
class Inline:
    """A text cell stored as an inline string instead of a shared string."""
    text: str


def _spalte(index: int) -> str:
    name = ""
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        name = chr(65 + rest) + name
    return name


def _blatt(zeilen, strings: list[str]) -> str:
    teile = []
    for nummer, zeile in enumerate(zeilen, start=1):
        zellen = []
        for spalte, wert in enumerate(zeile):
            ref = f"{_spalte(spalte)}{nummer}"
            if wert is None or wert == "":
                continue
            if isinstance(wert, Formel):
                cache = "" if wert.ergebnis is None else f"<v>{wert.ergebnis!r}</v>"
                zellen.append(f'<c r="{ref}"><f>{escape(wert.formel)}</f>{cache}</c>')
            elif isinstance(wert, Inline):
                zellen.append(f'<c r="{ref}" t="inlineStr"><is><t>{escape(wert.text)}</t></is></c>')
            elif isinstance(wert, (int, float)):
                zellen.append(f'<c r="{ref}"><v>{wert!r}</v></c>')
            else:
                if wert not in strings:
                    strings.append(wert)
                zellen.append(f'<c r="{ref}" t="s"><v>{strings.index(wert)}</v></c>')
        if zellen:
            teile.append(f'<row r="{nummer}">{"".join(zellen)}</row>')
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<sheetData>{"".join(teile)}</sheetData></worksheet>')


def xlsx(blaetter: dict[str, list[list]], versteckt: tuple[str, ...] = ()) -> bytes:
    """Workbook bytes; `blaetter` maps sheet name -> rows -> cells (str, number, Formel, Inline, None)."""
    strings: list[str] = []
    inhalte = [_blatt(zeilen, strings) for zeilen in blaetter.values()]
    eintraege = "".join(
        f'<sheet name="{escape(name)}" sheetId="{i}" r:id="rId{i}"{" state=\"hidden\"" if name in versteckt else ""}/>'
        for i, name in enumerate(blaetter, start=1))
    rels = "".join(
        f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        f'Target="worksheets/sheet{i}.xml"/>' for i in range(1, len(blaetter) + 1))
    rels += ('<Relationship Id="rIdS" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
             'sharedStrings" Target="sharedStrings.xml"/>')
    teile = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            + "".join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" '
                      'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                      for i in range(1, len(blaetter) + 1))
            + '<Override PartName="/xl/sharedStrings.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
            '</Types>'),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
            'officeDocument" Target="xl/workbook.xml"/></Relationships>'),
        "xl/workbook.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<sheets>{eintraege}</sheets></workbook>'),
        "xl/_rels/workbook.xml.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{rels}</Relationships>'),
    }
    for i, inhalt in enumerate(inhalte, start=1):
        teile[f"xl/worksheets/sheet{i}.xml"] = inhalt
    teile["xl/sharedStrings.xml"] = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="{len(strings)}" '
        f'uniqueCount="{len(strings)}">'
        + "".join(f'<si><t xml:space="preserve">{escape(s)}</t></si>' for s in strings) + "</sst>")
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as archiv:
        for name, inhalt in teile.items():
            info = zipfile.ZipInfo(name, _DATUM)
            info.compress_type = zipfile.ZIP_DEFLATED
            archiv.writestr(info, inhalt.encode("utf-8"))
    return puffer.getvalue()


KOPF = ["OZ", "Kurztext", "Langtext", "Menge", "Einheit", "EP", "GP", "Typ", "Titel"]


def beispiel_lv() -> bytes:
    """The issue's acceptance sheet: three items, comma decimals, 2 × 12,50 = 25,00, an unknown price,
    a duplicate OZ, an empty row, a sum row and a formula without a cached result."""
    return xlsx({"LV": [
        ["Synthetisches Leistungsverzeichnis (Testdaten)"],
        KOPF,
        ["01.01", "Baustelleneinrichtung", "Einrichten und Räumen der Baustelle", 1, "psch", 1500, 1500,
         "Pauschal", "01 Baustelle"],
        [],
        ["01.02", "Mauerwerk KS 17,5 cm", "Kalksandstein, Mörtelgruppe IIa", 2, "m2", "12,50", "25,00",
         "", "02 Rohbau / 02.1 Mauerwerk"],
        ["01.02", "Mauerwerk KS 24 cm", Inline("Wie vor, jedoch 24 cm"), "3,5", "m2", None,
         Formel("D6*F6"), "Bedarf", "02 Rohbau / 02.1 Mauerwerk"],
        [None, "Summe Leistungsverzeichnis", None, None, None, None, Formel("SUM(G3:G6)", 1525.0)],
    ]})


def anderes_layout() -> bytes:
    """Other headers, other order, section rows instead of a title column: no fixed layout."""
    return xlsx({
        "Deckblatt": [["Projekt", "Testhaus (synthetisch)"], ["Stand", "2026-11-21"]],
        "Positionen": [
            ["Einheitspreis", "Pos.", "Bezeichnung", "Mengeneinheit", "Menge", "Gesamtpreis"],
            [None, "01", "Erdarbeiten"],
            ["8,40", "01.0010", "Oberboden abtragen", "m2", "120", "1.008,00"],
            [None, "01.0020", "Baugrube ausheben", "m3", "45,5"],
            [None, "02", "Entwässerung"],
            ["35", "02.0010", "KG-Rohr DN 150", "m", 18, 630],
        ],
        "Kalkulation intern": [["OZ", "Menge"], ["99.99", 1]],
    }, versteckt=("Kalkulation intern",))


def ohne_oz() -> bytes:
    return xlsx({"Tabelle1": [["Kurztext", "Menge", "Einheit", "EP"], ["Mauerwerk", 2, "m2", "12,50"]]})


def gross(anzahl: int) -> bytes:
    zeilen = [["OZ", "Kurztext", "Menge", "Einheit", "EP"]]
    zeilen += [[f"01.{i:04d}", f"Position {i}", i, "m", "1,25"] for i in range(1, anzahl + 1)]
    return xlsx({"LV": zeilen})


if __name__ == "__main__":  # regenerate the committed example: python api/tests/fixtures/excel/synthetic.py
    from pathlib import Path
    (Path(__file__).parent / "lv_synthetisch.xlsx").write_bytes(beispiel_lv())

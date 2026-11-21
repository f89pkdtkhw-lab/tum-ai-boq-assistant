"""Norm check N6: closed-list checks for concrete classes and insulation product standards.

Deterministic and offline. `pruefe_listen(lv)` is called from `pruefe_normen` (so it runs under
the `NORMPRUEFUNG` switch and the `pruefe_normen_sicher` guard) and creates two kinds of findings:

- `NORM_KLASSE_UNGUELTIG`: an exposure class, moisture class or strength class that is not on the
  closed list of the concrete standard (token typo such as "XC5", empty element in a class list such
  as "XC4/XF1//WF", strength class that is no pair of the table such as "C25/35").
- `NORM_PRODUKTNORM_WIDERSPRUCH`: an item names exactly one insulation material but cites only
  product standards of the DIN EN 13162–13171 series that belong to other materials.

Both are hints, not standards expert opinions; the lists below are tool assumptions, no standard
text is quoted. Findings carry the note `KEIN_NORMGUTACHTEN`.
"""
import re

from ..modelle import LV, Finding, Position
from .normen import KEIN_NORMGUTACHTEN

NORM_KLASSE_UNGUELTIG = "NORM_KLASSE_UNGUELTIG"
NORM_PRODUKTNORM_WIDERSPRUCH = "NORM_PRODUKTNORM_WIDERSPRUCH"

# Source: exposure classes of DIN EN 206 / DIN 1045-2 (table of exposure classes).
EXPOSITIONSKLASSEN = frozenset(
    {"X0"}
    | {f"XC{i}" for i in range(1, 5)}
    | {f"XD{i}" for i in range(1, 4)}
    | {f"XS{i}" for i in range(1, 4)}
    | {f"XF{i}" for i in range(1, 5)}
    | {f"XA{i}" for i in range(1, 4)}
    | {f"XM{i}" for i in range(1, 4)}
)
# Tool assumption: "XC0" is a common spelling of X0 (no risk of corrosion) in LVs; tolerated, not flagged.
_TOLERIERT = frozenset({"XC0"})
# Source: moisture classes of DIN 1045-2 (alkali-silica reaction), W0 / WF / WA / WS.
FEUCHTEKLASSEN = frozenset({"W0", "WF", "WA", "WS"})
# Source: strength classes of normal-weight concrete in DIN EN 206 (cylinder/cube pairs, C8/10 … C100/115).
FESTIGKEITSKLASSEN = frozenset({
    "C8/10", "C12/15", "C16/20", "C20/25", "C25/30", "C30/37", "C35/45", "C40/50", "C45/55",
    "C50/60", "C55/67", "C60/75", "C70/85", "C80/95", "C90/105", "C100/115",
})
# Source: product standards DIN EN 13162–13171 (factory-made thermal insulation products), by material.
PRODUKTNORMEN = {
    "MW": "13162", "EPS": "13163", "XPS": "13164", "PU": "13165", "PF": "13166",
    "CG": "13167", "WW": "13168", "EPB": "13169", "ICB": "13170", "WF": "13171",
}

_EXPOSITION = re.compile(r"(?<![A-Za-z0-9])X[CDSFAM]\d+(?![A-Za-z0-9])")
# A class list starts at an exposure/moisture-like token; elements start with X or W, empty elements
# count only when another separator follows directly ("//").
_KLASSENLISTE = re.compile(
    r"(?<![A-Za-z0-9/])(?:X[A-Z0-9]{0,3}|W[A-Z0-9]?)(?![A-Za-z0-9])"
    r"(?:\s*[/,]\s*(?:(?:X[A-Z0-9]{0,3}|W[A-Z0-9]?)(?![A-Za-z0-9])|(?=[/,])))+"
)
_ELEMENT = re.compile(r"\s*[/,]\s*")
_FESTIGKEIT = re.compile(r"(?<![A-Za-z0-9])C(\d{1,3})/(\d{1,3})(?![0-9])")
_NORM_1316X = re.compile(r"(?<![A-Za-z0-9])(?:DIN\s*)?EN\s*(131(?:6[2-9]|7[01]))(?!\d)", re.IGNORECASE)

_DAEMMSTOFFE: dict[str, re.Pattern] = {
    "MW": re.compile(r"\bMW\b|Mineralwolle|Steinwolle|Glaswolle", re.IGNORECASE),
    "XPS": re.compile(r"\bXPS\b|extrudiert", re.IGNORECASE),
    "PU": re.compile(r"\b(?:PU|PUR|PIR)\b|Polyurethan|Polyisocyanurat", re.IGNORECASE),
    "PF": re.compile(r"\bPF\b|Phenolharz", re.IGNORECASE),
    "CG": re.compile(r"\bCG\b|Schaumglas", re.IGNORECASE),
    "WW": re.compile(r"\bWW\b|Holzwolle", re.IGNORECASE),
    "EPB": re.compile(r"\bEPB\b|Perlit", re.IGNORECASE),
    "ICB": re.compile(r"\bICB\b|Kork", re.IGNORECASE),
    "WF": re.compile(r"\bWF\b|Holzfaser", re.IGNORECASE),
}
_EPS_KUERZEL = re.compile(r"\bEPS\b")
_EPS_WORT = re.compile(r"Polystyrol|Styropor", re.IGNORECASE)


def _text(position: Position) -> str:
    return f"{position.kurztext}\n{position.langtext}"


def _ohne_doppelte(tokens: list[str]) -> list[str]:
    return list(dict.fromkeys(tokens))


def _ungueltige_klassen(text: str) -> list[str]:
    """Offending tokens in order of appearance (empty list elements are shown as "(empty element)")."""
    gefunden: list[tuple[int, str]] = []
    abgedeckt: list[tuple[int, int]] = []
    for liste in _KLASSENLISTE.finditer(text):
        abgedeckt.append(liste.span())
        offset = liste.start()
        for element in _ELEMENT.split(liste.group()):
            if element == "":
                gefunden.append((offset, "(empty element)"))
            elif element not in EXPOSITIONSKLASSEN | FEUCHTEKLASSEN | _TOLERIERT:
                gefunden.append((offset, element))
    for treffer in _EXPOSITION.finditer(text):
        if treffer.group() not in EXPOSITIONSKLASSEN | _TOLERIERT and not any(a <= treffer.start() < b for a, b in abgedeckt):
            gefunden.append((treffer.start(), treffer.group()))
    for treffer in _FESTIGKEIT.finditer(text):
        if treffer.group().replace(" ", "") not in FESTIGKEITSKLASSEN:
            gefunden.append((treffer.start(), treffer.group()))
    return _ohne_doppelte([token for _, token in sorted(gefunden, key=lambda g: g[0])])


def _benannte_materialien(text: str) -> set[str]:
    materialien = {kuerzel for kuerzel, muster in _DAEMMSTOFFE.items() if muster.search(text)}
    if _EPS_KUERZEL.search(text) or (_EPS_WORT.search(text) and "XPS" not in materialien):
        materialien.add("EPS")  # "extrudierter Polystyrol-Hartschaum" is XPS, not additionally EPS
    return materialien


def pruefe_listen(lv: LV) -> list[Finding]:
    """Closed-list findings in position order: `NORM_KLASSE_UNGUELTIG`, `NORM_PRODUKTNORM_WIDERSPRUCH`."""
    findings: list[Finding] = []
    for position in lv.positionen:
        text = _text(position)
        ungueltig = _ungueltige_klassen(text)
        if ungueltig:
            tokens = ", ".join(f'"{t}"' if not t.startswith("(") else t for t in ungueltig)
            findings.append(Finding(
                id=f"{NORM_KLASSE_UNGUELTIG}:{position.oz}", oz=position.oz, kategorie="fehler", schwere="mittel",
                titel="Concrete class not on the closed list",
                begruendung=(f"OZ {position.oz}: {tokens} is not a valid exposure, moisture or strength class "
                             f"according to the class lists of DIN EN 206 / DIN 1045-2. {KEIN_NORMGUTACHTEN}"),
                vorschlag=(f"Bidder question (Bieterfrage): which class is meant in OZ {position.oz} instead of "
                           f"{tokens}? Please correct the class designation in the LV."),
                quelle="regel", regel_id=NORM_KLASSE_UNGUELTIG, euro_wirkung=None))
        materialien = _benannte_materialien(text)
        nummern = _ohne_doppelte([m.group(1) for m in _NORM_1316X.finditer(text)])
        if len(materialien) == 1 and nummern:
            (material,) = materialien
            if PRODUKTNORMEN[material] not in nummern:
                zitiert = ", ".join(f"DIN EN {n}" for n in nummern)
                findings.append(Finding(
                    id=f"{NORM_PRODUKTNORM_WIDERSPRUCH}:{position.oz}", oz=position.oz, kategorie="fehler",
                    schwere="mittel", titel="Product standard does not match the insulation material",
                    begruendung=(f"OZ {position.oz} names the insulation material {material} but cites {zitiert}; "
                                 f"in the DIN EN 13162–13171 series this product standard belongs to a different "
                                 f"material (list in the tool, source: DIN EN 13162–13171). {KEIN_NORMGUTACHTEN}"),
                    vorschlag=(f"Bidder question (Bieterfrage): Which product standard applies to the specified "
                               f"material in OZ {position.oz}?"),
                    quelle="regel", regel_id=NORM_PRODUKTNORM_WIDERSPRUCH, euro_wirkung=None))
    return findings

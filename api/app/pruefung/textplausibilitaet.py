"""Deterministic text plausibility rules on the long text of BoQ positions.

1. Dimension unit error (MASS_EINHEIT_UNPLAUSIBEL): a named dimension (wall
   thickness, width, height, ...) stated in cm with a value below 1 and at
   least two decimal places, e.g. "0,240cm". That precision in cm is not used
   in construction and reads like metres. No per-component ranges are used
   (they false-alarm on pipe wall thicknesses).
2. Dangling manufacturer name (FABRIKAT_WIDERSPRUCH): "oder gleichwertig" is
   followed by a line holding only a second, capitalised manufacturer name.

Both are errors from a fixed rule, one finding per OZ, without euro impact.
"""
import re

from ..modelle import Finding, LV, Position

_DIMENSION = (r"(?:Auflagerl[äa]nge|Wanddicke|Wandst[äa]rke|Dicke|St[äa]rke|Breite|H[öo]he|"
              r"Tiefe|L[äa]nge|[dhbt]\s*=)")
_DIMENSION_CM = re.compile(
    rf"(?<![\wÄÖÜäöüß])(?P<name>{_DIMENSION})[ \t:=]*(?:\s*\n\s*)?[ \t]*"
    r"(?P<value>0[,.]\d{2,})[ \t]*cm\b",
    re.IGNORECASE,
)
_DANGLING_MANUFACTURER = re.compile(
    r"(?i:oder\s+gleichwertig)[.,;]?[ \t]*\n[ \t]*"
    r"(?P<name>[A-ZÄÖÜ][\w&.-]+(?:[ \t]+[A-ZÄÖÜ][\w&.-]+)?)[ \t]*\n[ \t]*\n"
)
_PRODUCT = re.compile(r"(?i:Fabrikat|Typ|Produkt)\s*:?[ \t]*(?P<name>[^\n]*?)[ \t]*,?[ \t]*(?i:oder\s+gleichwertig)")


def _finding(pos: Position, rule_id: str, title: str, reason: str, proposal: str) -> Finding:
    return Finding(id=f"{rule_id}:{pos.oz}", oz=pos.oz, kategorie="fehler", schwere="mittel",
                   titel=title, begruendung=reason, vorschlag=proposal, quelle="regel",
                   regel_id=rule_id, euro_wirkung=None)


def _check_dimension_unit(pos: Position) -> Finding | None:
    match = _DIMENSION_CM.search(pos.langtext)
    if not match:
        return None
    name = match.group("name").strip().rstrip("=").strip()
    value = match.group("value")
    number = float(value.replace(",", "."))
    mm = f"{number * 10:g}".replace(".", ",")
    cm = f"{number * 100:g}".replace(".", ",")
    return _finding(
        pos, "MASS_EINHEIT_UNPLAUSIBEL", "Implausible dimension unit",
        (f"OZ {pos.oz} states {name} {value} cm. That precision in cm is not used in construction "
         f"and reads like metres. Read as stated, {value} cm = {mm} mm; "
         f"read as metres, {value} m = {cm} cm."),
        f"Ask the bidder or planner whether {name} {value} is meant in cm, mm or m, and correct the unit.",
    )


def _check_dangling_manufacturer(pos: Position) -> Finding | None:
    match = _DANGLING_MANUFACTURER.search(pos.langtext + "\n\n")
    if not match:
        return None
    dangling = match.group("name")
    product = _PRODUCT.search(pos.langtext[:match.start() + len(match.group(0))])
    planned = product.group("name").strip(" ,;:") if product else ""
    planned_part = f"the planned product “{planned}”" if planned else "the planned product"
    return _finding(
        pos, "FABRIKAT_WIDERSPRUCH", "Second manufacturer name after “oder gleichwertig”",
        (f"OZ {pos.oz} names {planned_part} “oder gleichwertig” and then a separate line "
         f"with only “{dangling}”. That reads like a second, contradicting manufacturer name."),
        f"Ask which manufacturer applies: {planned or 'the planned product'} or {dangling}.",
    )


def pruefe_textplausibilitaet(lv: LV) -> list[Finding]:
    findings: list[Finding] = []
    for pos in lv.positionen:
        for check in (_check_dimension_unit, _check_dangling_manufacturer):
            found = check(pos)
            if found:
                findings.append(found)
    return findings

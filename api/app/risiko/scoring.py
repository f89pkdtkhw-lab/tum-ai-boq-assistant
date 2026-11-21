"""Offline, evidenced work-condition hints; no price or standards inference."""
import re
from collections import defaultdict
from decimal import Decimal

from ..modelle import Finding, LV, Position


# Ordinal uncertainty is a review heuristic, not a probability of extra cost.
_CONDITIONS = {
    "bedarf": (3, "Optional work", "The item is explicitly optional (bedarf)",
               "Under which conditions will this optional work be instructed, and what quantity is expected?"),
    "alternativ": (3, "Alternative work", "The item is explicitly alternative (alternativ)",
                  "Which alternative is to be selected, and which other OZ does it replace?"),
    "zulage": (2, "Supplementary work", "The item is explicitly supplementary (zulage)",
               "To which base OZ and quantities does this supplement apply?"),
    "pauschal": (2, "Lump-sum scope", "The item is explicitly lump-sum work (pauschal)",
                 "Which services and scope boundaries are included in this lump sum?"),
    "stundenlohn": (3, "Hourly work", "The item is explicitly hourly work (stundenlohn)",
                    "What hours are expected, and how will the instructed hours be recorded?"),
}
_AS_REQUIRED = re.compile(r"\b(as required|as needed|bei bedarf|nach bedarf|nach erfordernis)\b", re.I)
_UNCERTAINTY = {"kritisch": 3, "hoch": 3, "mittel": 2, "niedrig": 1}


def _material_context(lv: LV) -> dict[int, str]:
    """Conservative description groups, without unit conversion or material inference.

    Both descriptions, stated unit and work type must match exactly. Optional
    quantities are kept apart from firm quantities. Context is attached to
    actual hints only; a quantity total alone is not a domain risk.
    """
    groups: dict[tuple, list[tuple[int, Position]]] = defaultdict(list)
    for index, pos in enumerate(lv.positionen):
        groups[(pos.kurztext, pos.langtext, pos.einheit, pos.typ)].append((index, pos))
    context = {}
    for members in groups.values():
        first = members[0][1]
        if not first.kurztext.strip():
            continue  # no evidenced description on which to group materials
        sources = ", ".join(p.oz for _, p in members)
        prefix = f'Material/work quantity context "{first.kurztext}": '
        if not first.einheit or not first.einheit.strip():
            total_text = "unit missing; no material total"
        else:
            known = [Decimal(str(p.menge)) for _, p in members if p.menge is not None]
            missing = len(members) - len(known)
            total = sum(known, Decimal(0))
            amount = format(total.normalize(), "f")
            if missing:
                total_text = (f"known subtotal {amount} {first.einheit}; {missing} unknown quantity "
                              "entries; complete total unavailable")
            else:
                total_text = f"{amount} {first.einheit}"
        text = (f"{prefix}{total_text} (OZ {sources}; identical descriptions, unit and "
                f"work type {first.typ}; stated work quantities, not inferred material consumption).")
        for index, _ in members:
            context[index] = text
    return context


def bewerte(lv: LV, findings: list[Finding]) -> list[Finding]:
    result = list(findings)
    material = _material_context(lv)
    for index, pos in enumerate(lv.positionen):
        conditions = []
        if pos.typ in _CONDITIONS:
            conditions.append((f"RISK_{pos.typ.upper()}", _CONDITIONS[pos.typ]))
        match = _AS_REQUIRED.search(f"{pos.kurztext}\n{pos.langtext}")
        if match:
            conditions.append(("RISK_AS_REQUIRED", (
                3, "Unspecified demand", f'The description explicitly states "{match.group()}"',
                "What measurable demand and instruction criteria define the required quantity?",
            )))
        for rule, (uncertainty, title, evidence, question) in conditions:
            type_hint = rule != "RISK_AS_REQUIRED"
            reason = (f"OZ {pos.oz}: {evidence}. " if type_hint else
                      f"OZ {pos.oz}: {evidence}. Scope or quantity needs clarification; "
                      "this does not establish an entitlement to additional payment. ")
            result.append(Finding(
                id=f"{rule}:{pos.oz}:{index}", oz=pos.oz,
                kategorie="nachtrag" if rule == "RISK_AS_REQUIRED" else "risiko",
                schwere="hoch" if uncertainty == 3 and not type_hint else "mittel", titel=title,
                begruendung=reason + material.get(index, ""),
                vorschlag=f"OZ {pos.oz}: {question}", quelle="regel", regel_id=rule,
            ))
    # Preserve error evidence verbatim, including #7's measured arithmetic deltas.
    preserved = [f for f in result if f.kategorie == "fehler" or f.regel_id.startswith("MOCK_")]
    hints = [f for f in result if f.kategorie != "fehler" and not f.regel_id.startswith("MOCK_")]
    hints.sort(key=lambda f: (
        -_UNCERTAINTY[f.schwere], f.euro_wirkung is None,
        -abs(f.euro_wirkung) if f.euro_wirkung is not None else 0,
        f.oz, f.regel_id, f.id,
    ))
    ranked = []
    for rank, finding in enumerate(hints, 1):
        impact = ("no evidenced euro impact; no amount claimed" if finding.euro_wirkung is None
                  else f"evidenced euro impact {finding.euro_wirkung:g} EUR (supplied finding)")
        view = "Priority view" if rank <= 100 else "Review remainder"
        rationale = (f"{view}: rank {rank}/{len(hints)}. "
                     f"Uncertainty {_UNCERTAINTY[finding.schwere]}/3 (ordinal review heuristic; "
                     f"existing hints use severity); {impact}. "
                     "Order: uncertainty descending, known absolute euro impact descending, "
                     "then OZ, rule and stable ID; unknown impact ranks after known impact at equal uncertainty.")
        ranked.append(finding.model_copy(update={"begruendung": f"{finding.begruendung} {rationale}"}))
    return preserved + ranked

"""Plausibility hints for quantity relations between related BoQ positions.

All thresholds are transparent plausibility assumptions of this tool, not
building standards. Positions are only compared within the same title
(titel_pfad), with compatible units and known quantities > 0. No euro impact.

1. Layer build-up (MENGE_SCHICHTEN_ABWEICHUNG): layers of the same component
   (e.g. primer, welded membrane, insulation, PE foil under the floor slab)
   usually cover the same area. A layer deviating from the group median by
   more than LAYER_TOLERANCE yields a hint.
2. Ratio rules (MENGE_VERHAELTNIS): explicitly configured pairs with a
   plausibility range, e.g. reinforcement per m³ concrete. Custom rules (such as
   a synthetic chairs/tables ratio) are passed in via `ratio_rules`.
"""
from dataclasses import dataclass
from statistics import median

from ..modelle import Finding, LV, Position

LAYER_TOLERANCE = 0.10  # assumption: ±10 % from the group median is unremarkable

LAYER_TERMS = (
    "voranstrich", "schweißbahn", "schweissbahn", "bitumenbahn", "abdichtung",
    "dämmung", "daemmung", "pe-folie", "folie", "trennlage", "sauberkeitsschicht",
)
COMPONENT_TERMS = ("bodenplatte", "kellerwand", "decke", "dach", "terrasse", "balkon")

# unit -> (base unit, factor). Unknown units are never compared.
UNITS = {
    "m²": ("m²", 1.0), "m2": ("m²", 1.0), "qm": ("m²", 1.0),
    "m³": ("m³", 1.0), "m3": ("m³", 1.0), "cbm": ("m³", 1.0),
    "m": ("m", 1.0), "lfm": ("m", 1.0),
    "kg": ("kg", 1.0), "t": ("kg", 1000.0),
    "st": ("St", 1.0), "stk": ("St", 1.0), "stck": ("St", 1.0), "stk.": ("St", 1.0),
}

# Contingency, alternative and surcharge positions carry no real quantity.
COMPARABLE_TYPES = {"normal", "pauschal"}


@dataclass(frozen=True)
class RatioRule:
    """Plausibility range for quantity(compare) / quantity(base), per title."""
    name: str
    base_terms: tuple[str, ...]
    base_unit: str  # base unit, e.g. "m³"
    compare_terms: tuple[str, ...]
    compare_unit: str
    minimum: float
    maximum: float
    assumption: str  # transparent rationale, explicitly not a standard


CONCRETE_REINFORCEMENT = RatioRule(
    name="Bewehrung je Beton",
    base_terms=("beton",),
    base_unit="m³",
    compare_terms=("bewehrung", "betonstahl", "baustahlmatte"),
    compare_unit="kg",
    minimum=40.0,
    maximum=200.0,
    assumption=("Plausibilitätsannahme 40–200 kg Bewehrung je m³ Beton für übliche "
                "Stahlbetonbauteile; kein normativer Grenzwert, statische Berechnung maßgeblich"),
)

DEFAULT_RATIO_RULES: tuple[RatioRule, ...] = (CONCRETE_REINFORCEMENT,)


def _text(pos: Position) -> str:
    return pos.kurztext.casefold()


def _contains(pos: Position, terms: tuple[str, ...]) -> bool:
    text = _text(pos)
    return any(term in text for term in terms)


def _base_quantity(pos: Position) -> tuple[str, float] | None:
    """Quantity in base unit, only for a known unit and quantity > 0."""
    if pos.typ not in COMPARABLE_TYPES or pos.menge is None or pos.menge <= 0:
        return None
    entry = UNITS.get((pos.einheit or "").strip().casefold())
    if entry is None:
        return None
    unit, factor = entry
    return unit, pos.menge * factor


def _num(value: float) -> str:
    return f"{value:g}".replace(".", ",")


def _title(pos: Position) -> str:
    return " / ".join(pos.titel_pfad) or "ohne Titel"


def _hint(id_: str, oz: str, title: str, reason: str, proposal: str, rule_id: str) -> Finding:
    return Finding(id=id_, oz=oz, kategorie="risiko", schwere="mittel", titel=title,
                   begruendung=reason, vorschlag=proposal, quelle="regel",
                   regel_id=rule_id, euro_wirkung=None)


def _check_layers(lv: LV) -> list[Finding]:
    groups: dict[tuple[tuple[str, ...], str], list[tuple[Position, float]]] = {}
    for pos in lv.positionen:
        if not _contains(pos, LAYER_TERMS):
            continue
        component = next((c for c in COMPONENT_TERMS if c in _text(pos)), None)
        quantity = _base_quantity(pos)
        if component is None or quantity is None or quantity[0] != "m²":
            continue
        groups.setdefault((tuple(pos.titel_pfad), component), []).append((pos, quantity[1]))

    findings = []
    for (_, component), members in groups.items():
        if len(members) < 2:
            continue
        mid = median(q for _, q in members)
        name = component.capitalize()
        overview = "; ".join(f"OZ {p.oz} {p.kurztext.strip()} {_num(q)} m²" for p, q in members)
        for pos, quantity in members:
            deviation = (quantity - mid) / mid
            if abs(deviation) <= LAYER_TOLERANCE:
                continue
            findings.append(_hint(
                f"MENGE_SCHICHTEN_ABWEICHUNG:{pos.oz}", pos.oz,
                f"Schichtfläche {name} auffällig",
                (f"{_num(quantity)} m² weicht {deviation:+.0%} vom Median {_num(mid)} m² "
                 f"der Schichten {name} im Titel „{_title(pos)}“ ab ({overview}). "
                 f"Annahme: Schichten desselben Bauteils decken etwa dieselbe Fläche ab, "
                 f"Toleranz ±{LAYER_TOLERANCE:.0%}; keine Norm."),
                "Fläche gegen Aufmaß bzw. Planunterlagen prüfen; Überstände oder Teilflächen im Langtext begründen.",
                "MENGE_SCHICHTEN_ABWEICHUNG",
            ))
    return findings


def _check_ratio(lv: LV, rule: RatioRule) -> list[Finding]:
    by_title: dict[tuple[str, ...], tuple[list[tuple[Position, float]], list[tuple[Position, float]]]] = {}
    for pos in lv.positionen:
        quantity = _base_quantity(pos)
        if quantity is None:
            continue
        unit, value = quantity
        base, compare = by_title.setdefault(tuple(pos.titel_pfad), ([], []))
        if unit == rule.compare_unit and _contains(pos, rule.compare_terms):
            compare.append((pos, value))
        elif unit == rule.base_unit and _contains(pos, rule.base_terms):
            base.append((pos, value))

    findings = []
    for base, compare in by_title.values():
        # Only clearly delimited titles: exactly one base and one compare position.
        if len(base) != 1 or len(compare) != 1:
            continue
        (b_pos, b_value), (c_pos, c_value) = base[0], compare[0]
        ratio = c_value / b_value
        if rule.minimum <= ratio <= rule.maximum:
            continue
        unit = f"{rule.compare_unit}/{rule.base_unit}"
        findings.append(_hint(
            f"MENGE_VERHAELTNIS:{rule.name}:{c_pos.oz}", c_pos.oz,
            f"Mengenverhältnis {rule.name} auffällig",
            (f"OZ {c_pos.oz} {_num(c_value)} {rule.compare_unit} zu OZ {b_pos.oz} "
             f"{_num(b_value)} {rule.base_unit} ergibt {_num(round(ratio, 2))} {unit} "
             f"im Titel „{_title(c_pos)}“, erwartet {_num(rule.minimum)}–{_num(rule.maximum)} "
             f"{unit}. {rule.assumption}."),
            f"Mengen von OZ {c_pos.oz} und OZ {b_pos.oz} gegen Aufmaß bzw. Planung prüfen.",
            "MENGE_VERHAELTNIS",
        ))
    return findings


def pruefe_mengen(lv: LV, ratio_rules: tuple[RatioRule, ...] | None = None) -> list[Finding]:
    rules = DEFAULT_RATIO_RULES if ratio_rules is None else ratio_rules
    findings = _check_layers(lv)
    for rule in rules:
        findings.extend(_check_ratio(lv, rule))
    return findings

"""Plausibility hints for quantity relations between related BoQ positions.

All thresholds are transparent plausibility assumptions of this tool, not
building standards. Positions are only compared within the same title
(titel_pfad), with compatible units and known quantities > 0. No euro impact.

1. Layer build-up (MENGE_SCHICHTEN_ABWEICHUNG): layers of the same component
   (e.g. primer, welded membrane, insulation, PE foil under the floor slab)
   usually cover the same area. A layer deviating from the group median by
   more than LAYER_TOLERANCE yields a hint. The component is taken from the
   short text first and from the long text as a fallback; long-text mentions
   that only reference the component ("Anschluss an Bodenplatte") are ignored.
   Trade sections ("Abdichtungsarbeiten", "Dämmarbeiten") split one building
   part across titles, so they are ignored when grouping; all other title
   levels (objects, building parts) still separate the groups.
   A layer of at most SMALL_LAYER_MAX_AREA m² without a named component is
   compared with all layer items of the same scope (implausibly small area).
2. Insulation thermal conductivity group (BEZEICHNUNG_ABWEICHUNG): among
   insulation items of one title naming exactly one group (e.g. WLG 035), a
   single item with the minority of exactly two groups yields a hint.
3. Ratio rules (MENGE_VERHAELTNIS): explicitly configured pairs with a
   plausibility range, e.g. reinforcement per m³ concrete. Custom rules (such as
   a synthetic chairs/tables ratio) are passed in via `ratio_rules`.
4. Text plausibility (textplausibilitaet.py): dimension unit error and dangling
   manufacturer name, called once at the end of `pruefe_mengen`.
"""
import re
from dataclasses import dataclass
from statistics import median

from ..modelle import Finding, LV, Position
from .regeln import _bezeichnungen
from .textplausibilitaet import pruefe_textplausibilitaet

LAYER_TOLERANCE = 0.10  # assumption: ±10 % from the group median is unremarkable
# Plausibility assumptions (not standards) for a layer without a named component.
SMALL_LAYER_MAX_AREA = 1.0  # m²: at most this area counts as implausibly small
SMALL_LAYER_FACTOR = 20.0  # sibling median must be at least this many times the item's area
SMALL_LAYER_MIN_SIBLINGS = 3  # layer items (incl. the small one) needed for a comparison
WLG_MIN_ITEMS = 3  # insulation items with one thermal conductivity group needed for a comparison

LAYER_TERMS = (
    "voranstrich", "schweißbahn", "schweissbahn", "bitumenbahn", "abdichtung",
    "dämmung", "daemmung", "pe-folie", "folie", "trennlage", "sauberkeitsschicht",
)
COMPONENT_TERMS = ("bodenplatte", "kellerwand", "decke", "dach", "terrasse", "balkon")

# Long text is wordier than the short text: a component term only counts there at the start or
# end of a word ("Stahlbetonbodenplatte", "Deckenabdichtung", but not "volldeckend"), and not
# when the text merely names it as a connection point.
_LONGTEXT_COMPONENT = {
    term: re.compile(rf"\b{term}|{term}\b") for term in COMPONENT_TERMS
}
_REFERENCE_BEFORE = re.compile(r"anschlu(?:ss|ß)\s+(?:an|zur|zum)\s+(?:die\s+|der\s+|den\s+)?$")
# A title naming a trade ("Abdichtungsarbeiten", "Dämmarbeiten") is a trade section, not an object.
_TRADE_TITLE = re.compile(r"arbeiten\b")

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
    assumption=("Plausibility assumption of 40–200 kg reinforcement per m³ concrete for typical "
                "reinforced concrete components; not a normative limit, structural calculations govern"),
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
    return " / ".join(pos.titel_pfad) or "no section"


def _hint(id_: str, oz: str, title: str, reason: str, proposal: str, rule_id: str) -> Finding:
    return Finding(id=id_, oz=oz, kategorie="risiko", schwere="mittel", titel=title,
                   begruendung=reason, vorschlag=proposal, quelle="regel",
                   regel_id=rule_id, euro_wirkung=None)


def _longtext_component(pos: Position) -> str | None:
    """First component named in the long text, skipping mere connection references."""
    text = pos.langtext.casefold()
    hits = []
    for term, pattern in _LONGTEXT_COMPONENT.items():
        for match in pattern.finditer(text):
            if not _REFERENCE_BEFORE.search(text[max(0, match.start() - 30):match.start()]):
                hits.append((match.start(), term))
                break
    return min(hits)[1] if hits else None


def _component(pos: Position) -> str | None:
    """Component from the short text first, the long text as fallback."""
    short = next((c for c in COMPONENT_TERMS if c in _text(pos)), None)
    return short or _longtext_component(pos)


def _layer_scope(pos: Position) -> tuple[str, ...]:
    """Title path without trade sections, so one building part split by trade stays one group."""
    return tuple(t for t in pos.titel_pfad if not _TRADE_TITLE.search(t.casefold()))


def _layer_groups(lv: LV) -> dict[tuple[tuple[str, ...], str], list[tuple[Position, float]]]:
    """Layer items (m², known quantity) grouped by scope and named component."""
    groups: dict[tuple[tuple[str, ...], str], list[tuple[Position, float]]] = {}
    for pos in lv.positionen:
        if not _contains(pos, LAYER_TERMS):
            continue
        quantity = _base_quantity(pos)
        if quantity is None or quantity[0] != "m²":
            continue
        component = _component(pos)
        if component is None:
            continue
        groups.setdefault((_layer_scope(pos), component), []).append((pos, quantity[1]))
    return groups


def erwartete_schichtmengen(lv: LV) -> dict[str, float]:
    """Expected area (group median, m²) per MENGE_SCHICHTEN_ABWEICHUNG finding id of the layer check.

    Exposes the number `_check_layers` already computes, for structured adjustments (#113). The
    small-layer check is not included: its median only marks an implausible area, it does not
    evidence the intended one (the item may be a partial area).
    """
    expected = {}
    for members in _layer_groups(lv).values():
        if len(members) < 2:
            continue
        mid = median(q for _, q in members)
        for pos, quantity in members:
            if abs((quantity - mid) / mid) > LAYER_TOLERANCE:
                expected[f"MENGE_SCHICHTEN_ABWEICHUNG:{pos.oz}"] = mid
    return expected


def _check_layers(lv: LV) -> list[Finding]:
    groups = _layer_groups(lv)
    findings = []
    for (_, component), members in groups.items():
        if len(members) < 2:
            continue
        mid = median(q for _, q in members)
        name = {"bodenplatte": "floor slab", "kellerwand": "basement wall", "decke": "ceiling",
                "dach": "roof", "terrasse": "terrace", "balkon": "balcony"}[component]
        overview = "; ".join(f"OZ {p.oz} {p.kurztext.strip()} {_num(q)} m²" for p, q in members)
        titles = list(dict.fromkeys(_title(p) for p, _ in members))
        sections = ("section " if len(titles) == 1 else "sections ") + ", ".join(f"“{t}”" for t in titles)
        for pos, quantity in members:
            deviation = (quantity - mid) / mid
            if abs(deviation) <= LAYER_TOLERANCE:
                continue
            findings.append(_hint(
                f"MENGE_SCHICHTEN_ABWEICHUNG:{pos.oz}", pos.oz,
                f"Unusual layer area for {name}",
                (f"{_num(quantity)} m² deviates {deviation:+.0%} from the median {_num(mid)} m² "
                 f"of the {name} layers in {sections} ({overview}). "
                 f"Assumption: layers of the same component cover approximately the same area, "
                 f"tolerance ±{LAYER_TOLERANCE:.0%}; not a standard."),
                "Check the area against measurements or plans; explain overhangs or partial areas in the detailed description.",
                "MENGE_SCHICHTEN_ABWEICHUNG",
            ))
    findings.extend(_check_small_layers(lv, {f.oz for f in findings}))
    return findings


def _check_small_layers(lv: LV, reported: set[str]) -> list[Finding]:
    """Tiny layer area without a named component, compared with the layers of the same scope."""
    scopes: dict[tuple[str, ...], list[tuple[Position, float]]] = {}
    for pos in lv.positionen:
        if not _contains(pos, LAYER_TERMS):
            continue
        quantity = _base_quantity(pos)
        if quantity is not None and quantity[0] == "m²":
            scopes.setdefault(_layer_scope(pos), []).append((pos, quantity[1]))

    findings = []
    for members in scopes.values():
        if len(members) < SMALL_LAYER_MIN_SIBLINGS:
            continue
        for pos, quantity in members:
            if quantity > SMALL_LAYER_MAX_AREA or pos.oz in reported or _component(pos) is not None:
                continue
            others = [(p, q) for p, q in members if p is not pos]
            mid = median(q for _, q in others)
            if mid < SMALL_LAYER_FACTOR * quantity:
                continue
            ozs = ", ".join(f"OZ {p.oz}" for p, _ in others)
            findings.append(_hint(
                f"MENGE_SCHICHTEN_ABWEICHUNG:{pos.oz}", pos.oz, "Implausibly small layer area",
                (f"{_num(quantity)} m² is far below the median {_num(mid)} m² of the other layers "
                 f"in section “{_title(pos)}” ({ozs}). "
                 f"Assumption: tolerance factor {SMALL_LAYER_FACTOR:g}; not a standard."),
                "Check the area against measurements or plans; a missing component name may hide a partial area.",
                "MENGE_SCHICHTEN_ABWEICHUNG",
            ))
    return findings


def _check_wlg(lv: LV) -> list[Finding]:
    """Insulation item whose thermal conductivity group differs from all its siblings but one group."""
    by_title: dict[tuple[str, ...], list[tuple[Position, str, str]]] = {}
    for pos in lv.positionen:
        if not _contains(pos, ("dämm", "daemm")):
            continue
        # Short text first; the long text only when the short text names no group.
        groups = (_bezeichnungen(pos.kurztext or "").get("thermal conductivity group")
                  or _bezeichnungen(pos.langtext or "").get("thermal conductivity group", {}))
        if len(groups) == 1:
            key, spelling = next(iter(groups.items()))
            by_title.setdefault(tuple(pos.titel_pfad), []).append((pos, key, spelling))

    findings = []
    for members in by_title.values():
        keys = {k for _, k, _ in members}
        if len(members) < WLG_MIN_ITEMS or len(keys) != 2:
            continue
        counts = {k: sum(1 for _, m, _ in members if m == k) for k in keys}
        minority = [k for k, c in counts.items() if c == 1]
        if len(minority) != 1:
            continue
        pos, _, spelling = next(m for m in members if m[1] == minority[0])
        majority = next(k for k in keys if k != minority[0])
        major_spelling = next(sp for _, k, sp in members if k == majority)
        ozs = ", ".join(f"OZ {p.oz}" for p, k, _ in members if k == majority)
        findings.append(_hint(
            f"BEZEICHNUNG_ABWEICHUNG:{pos.oz}", pos.oz, "Deviating thermal conductivity group",
            (f"“{spelling}” differs from {major_spelling}, used by {ozs} for the insulation items "
             f"in section “{_title(pos)}”. Assumption: insulation items of one section normally share "
             f"one thermal conductivity group; not a standard."),
            "Check whether the deviating thermal conductivity group is intended and align the description if not.",
            "BEZEICHNUNG_ABWEICHUNG",
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

    display_name = "reinforcement per concrete" if rule is CONCRETE_REINFORCEMENT else rule.name
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
            f"Unusual quantity ratio: {display_name}",
            (f"OZ {c_pos.oz} {_num(c_value)} {rule.compare_unit} to OZ {b_pos.oz} "
             f"{_num(b_value)} {rule.base_unit} yields {_num(round(ratio, 2))} {unit} "
             f"in section “{_title(c_pos)}”, expected {_num(rule.minimum)}–{_num(rule.maximum)} "
             f"{unit}. {rule.assumption}."),
            f"Check quantities for OZ {c_pos.oz} and OZ {b_pos.oz} against measurements or plans.",
            "MENGE_VERHAELTNIS",
        ))
    return findings


def pruefe_mengen(lv: LV, ratio_rules: tuple[RatioRule, ...] | None = None) -> list[Finding]:
    rules = DEFAULT_RATIO_RULES if ratio_rules is None else ratio_rules
    findings = _check_layers(lv)
    findings.extend(_check_wlg(lv))
    for rule in rules:
        findings.extend(_check_ratio(lv, rule))
    findings.extend(pruefe_textplausibilitaet(lv))
    return findings

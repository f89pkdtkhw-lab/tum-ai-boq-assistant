"""Comparison-step HTTP contract with offline adapters to the #13/#19/#20 module contracts.

Two request shapes are answered:

* Fixture requests (``specifications`` / ``history_records`` only) keep returning the fixed
  synthetic #28 placeholders for the documented fixture and ``placeholder_unavailable`` otherwise.
* Adapter requests (``sources`` + ``checked_on`` for Notes 1/2, ``estimates`` for Notes 3/4) run
  the deterministic rules of docs/spezifikationen.md and docs/schaetzszenarien.md. They never
  invent items, prices or standards; every note cites its source records or case IDs.

No live model API, internet or history store is contacted. The optional seams
``comparison_model`` (#13 structured review) and ``history_service`` (#18) default to None.
"""
import re
from collections import Counter
from collections.abc import Callable, Sequence
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Literal
from urllib.parse import urlparse

from fastapi import APIRouter
from pydantic import Field, model_validator

from ..modelle import Finding, LV, Position, Vertrag
from ..pruefung import llm_pruefung

Step = Literal["comparison", "standards", "historical_adjustment", "what_if"]
router = APIRouter()


class Specification(Vertrag):
    id: str = Field(min_length=1)
    oz: str = Field(min_length=1)
    text: str = Field(min_length=1)
    source: Literal["user", "internet", "standard"]
    verified_applicable: bool = False


class Measurement(Vertrag):
    oz: str = Field(min_length=1)
    title_path: list[str] = Field(default_factory=list)
    metric: str = Field(min_length=1)
    value: float | None
    unit: str = Field(min_length=1)


class HistoryRecord(Vertrag):
    """Provisional, client-supplied record; no history service is contacted."""

    case_id: str = Field(min_length=1)
    date: date
    description: str
    tags: list[str] = Field(default_factory=list)
    estimated_values: list[Measurement] = Field(default_factory=list)
    real_values: list[Measurement] = Field(default_factory=list)


class Evidence(Vertrag):
    reference_id: str
    oz: str
    source: str
    detail: str


class Note(Vertrag):
    id: str
    step: Step
    oz: str
    # "model_mock": fixed synthetic placeholder; "rule": deterministic #19/#20 adapter result.
    source: Literal["model_mock", "rule"] = "model_mock"
    placeholder: bool = True
    text: str
    manual_review: bool = True
    evidence: list[Evidence] = Field(default_factory=list)
    case_ids: list[str] = Field(default_factory=list)
    case_count: int = Field(default=0, ge=0)
    selection_reason: str | None = None
    base_value: float | None = None
    estimated_value: float | None = None
    unit: str | None = None
    assumption: str | None = None
    uncertainty: str | None = None
    approval_required: bool = True


class SourceScope(Vertrag):
    oz: list[str] = Field(default_factory=list)
    description: str = ""


class Requirement(Vertrag):
    parameter: str = Field(min_length=1)
    comparator: Literal["eq", "min", "max"]
    value: float
    unit: str = Field(min_length=1)


class SourceRecord(Vertrag):
    """#19 source record; texts are data, never instructions, and are not echoed into notes."""

    spec_id: str = Field(min_length=1)
    source_type: Literal["user", "internet"]
    category: Literal["german_standard", "user_requirement", "external_other"]
    title: str = ""
    source_url: str | None = Field(default=None, pattern=r"^https://\S+$")
    document_ref: str | None = None
    location: str | None = None
    as_of: str | None = None  # kept as text so that invalid dates become `invalid_as_of`
    scope: SourceScope
    text: str = ""
    requirement: Requirement | None = None
    verified: bool = False


class EstimatePosition(Vertrag):
    oz: str = Field(min_length=1)
    kurztext: str = ""
    title_path: list[str] = Field(default_factory=list)
    work_tags: list[str] = Field(default_factory=list)
    metric: str = Field(min_length=1)
    unit: str = Field(min_length=1)


class Baseline(Vertrag):
    value: float | None
    unit: str
    source: str


class UnitPrice(Vertrag):
    value: float | None
    currency: str
    per_unit: str
    source: str
    approved: bool = False


class Assumptions(Vertrag):
    """Chosen by the estimator, never by a model (#20 §1)."""

    ratio_method: str | None = None
    selected_by: str | None = None
    baseline: Baseline | None = None
    unit_price: UnitPrice | None = None


class EstimateTarget(Vertrag):
    position: EstimatePosition
    assumptions: Assumptions = Field(default_factory=Assumptions)
    limit: int = Field(default=20, strict=True)


class StepRequest(Vertrag):
    step: Step
    lv: LV
    specifications: list[Specification] = Field(default_factory=list)
    history_records: list[HistoryRecord] = Field(default_factory=list)
    previous_notes: list[Note] = Field(default_factory=list)
    sources: list[SourceRecord] = Field(default_factory=list)
    checked_on: date | None = None
    estimates: list[EstimateTarget] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_references(self):
        positions = [p.oz for p in self.lv.positionen]
        if any(not oz.strip() for oz in positions) or len(set(positions)) != len(positions):
            raise ValueError("LV OZ must be nonblank and unique.")
        if any(item.oz not in positions for item in [*self.specifications, *self.previous_notes]):
            raise ValueError("Specification and note OZ must exist in the LV.")
        for items, attribute in ((self.specifications, "id"), (self.history_records, "case_id")):
            ids = [getattr(item, attribute) for item in items]
            if len(set(ids)) != len(ids):
                raise ValueError("Reference IDs must be unique.")
        if self.sources:
            if self.step not in ("comparison", "standards"):
                raise ValueError("Sources are only accepted by the comparison and standards steps.")
            if self.checked_on is None:
                raise ValueError("Sources require checked_on (YYYY-MM-DD).")
            if self.specifications:
                raise ValueError("Send either specifications or sources, not both.")
        if self.estimates:
            if self.step not in ("historical_adjustment", "what_if"):
                raise ValueError("Estimates are only accepted by the historical_adjustment and what_if steps.")
            targets = [t.position.oz for t in self.estimates]
            if any(oz not in positions for oz in targets):
                raise ValueError("Estimate position OZ must exist in the LV.")
            if len(set(targets)) != len(targets):
                raise ValueError("Estimate position OZ must be unique.")
        return self


class StepError(Vertrag):
    step: Step
    code: str
    message: str
    retryable: bool = False


class StepResponse(Vertrag):
    step: Step
    status: Literal["placeholder", "complete", "error"]
    notes: list[Note]
    findings: list[Finding] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    errors: list[StepError] = Field(default_factory=list)


SYNTHETIC_LV = {
    "name": "Synthetic bridge repair", "quelle": "synthetic:comparison-v1",
    "positionen": [{"oz": "01.001"}],
}
CONFLICT_EXAMPLE = {
    "step": "comparison", "lv": SYNTHETIC_LV,
    "specifications": [
        {"id": "S10", "oz": "01.001", "text": "10 cm", "source": "user"},
        {"id": "S12", "oz": "01.001", "text": "12 cm", "source": "internet"},
    ],
}
ADAPTER_EXAMPLE = {
    "step": "comparison", "lv": SYNTHETIC_LV, "checked_on": "2026-11-20",
    "sources": [{
        "spec_id": "S10", "source_type": "user", "category": "user_requirement",
        "title": "User requirement A (synthetic)", "document_ref": "Synthetic client requirement sheet A",
        "location": "Item 1", "as_of": "2026-11-01", "scope": {"oz": ["01.001"]}, "text": "10 cm",
        "requirement": {"parameter": "thickness", "comparator": "eq", "value": 10, "unit": "cm"},
        "verified": True,
    }],
}
StepRequest.model_config["json_schema_extra"] = {"examples": [CONFLICT_EXAMPLE, ADAPTER_EXAMPLE]}


def step_error(request: StepRequest, code: str, message: str, retryable: bool = False) -> StepResponse:
    return StepResponse(step=request.step, status="error", notes=request.previous_notes,
                        errors=[StepError(step=request.step, code=code, message=message,
                                          retryable=retryable)])


def synthetic_note(request: StepRequest) -> Note | None:
    """Recognize documented fixtures, never infer domain claims from arbitrary LVs."""
    if request.lv.model_dump() != LV.model_validate(SYNTHETIC_LV).model_dump():
        return None
    if request.step in ("comparison", "standards"):
        if [s.model_dump() for s in request.specifications] != [
            Specification.model_validate(s).model_dump() for s in CONFLICT_EXAMPLE["specifications"]
        ]:
            return None
        evidence = [Evidence(reference_id=s.id, oz=s.oz, source=s.source, detail=s.text)
                    for s in request.specifications]
        return Note(id="Note1" if request.step == "comparison" else "Note2",
                    step=request.step, oz="01.001", evidence=evidence,
                    text="Synthetic placeholder: 10 cm / 12 cm conflict; manual review required. "
                         "Applicable standard evidence is missing; no verified norm breach.")
    pool = "H" if request.step == "historical_adjustment" else "W"
    ids = [f"{pool}{i}" for i in range(1, 4)]
    records = request.history_records
    expected = 120 if pool == "H" else 140
    if {r.case_id for r in records} != set(ids):
        return None
    for record in records:
        for values, value in ((record.estimated_values, 100), (record.real_values, expected)):
            if len(values) != 1 or values[0].model_dump() != Measurement(
                oz="01.001", metric="hours", value=value, unit="h"
            ).model_dump():
                return None
    return Note(
        id="Note3" if pool == "H" else "Note4", step=request.step, oz="01.001",
        text="Synthetic placeholder estimate; calculator approval required.",
        case_ids=ids, case_count=3, base_value=50, estimated_value=60 if pool == "H" else 70,
        unit="h", selection_reason="Fixed synthetic comparable pool" if pool == "H"
        else "Fixed synthetic broader what-if pool; separate from comparable cases",
        assumption="Fixed example: median actual/expected ratio 1.2" if pool == "H"
        else "Hypothetical fixed example: median actual/expected ratio 1.4",
        uncertainty="Synthetic example only; no calibrated confidence or real case selection.",
        evidence=[Evidence(reference_id=r.case_id, oz="01.001", source="history_fixture",
                           detail=f"Synthetic expected 100 h / actual {expected} h")
                  for r in sorted(records, key=lambda item: item.case_id)],
    )


# ---------------------------------------------------------------------------------------------
# #19 adapter: specification context and Notes 1/2 (docs/spezifikationen.md §3-§5)
# ---------------------------------------------------------------------------------------------
PRIORITY = {"german_standard": 1, "user_requirement": 2, "external_other": 3}
UNVERIFIED_PRIORITY = 4
CATEGORY_LABEL = {"german_standard": "source labelled German standard",
                  "user_requirement": "user requirement", "external_other": "external source"}


class SourceEntry(Vertrag):
    """One source attached to one OZ, with derived verification and priority (#19 §4)."""

    spec_id: str
    source_type: Literal["user", "internet"]
    category: Literal["german_standard", "user_requirement", "external_other"]
    priority: int
    verification: Literal["verified", "unverified"]
    unverified_reasons: list[str]
    record: SourceRecord


class ContextItem(Vertrag):
    oz: str
    kurztext: str
    titel_pfad: list[str]
    sources: list[SourceEntry]


class RejectedSource(Vertrag):
    spec_id: str
    reason: Literal["duplicate_spec_id", "missing_scope", "unknown_oz"]
    oz: list[str]


class SpecificationContext(Vertrag):
    lv: dict[str, str]
    checked_on: date
    content_is_data: Literal[True] = True
    items: list[ContextItem]
    rejected_sources: list[RejectedSource]


def verify_source(source: SourceRecord, checked_on: date) -> list[str]:
    """Fixed verification rules; reasons keep the documented order. Empty list = verified."""
    reasons = []
    if not (source.source_url or source.document_ref):
        reasons.append("missing_source_reference")
    if not source.location:
        reasons.append("missing_location")
    if not source.as_of:
        reasons.append("missing_as_of")
    else:
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", source.as_of):
                raise ValueError
            if date.fromisoformat(source.as_of) > checked_on:
                reasons.append("as_of_in_future")
        except ValueError:
            reasons.append("invalid_as_of")
    if source.verified is not True:
        reasons.append("not_confirmed")
    return reasons


def build_specification_context(lv: LV, sources: Sequence[SourceRecord], *,
                                checked_on: date) -> SpecificationContext:
    """Pure and offline: attach sources to original OZ, verify and prioritize them."""
    attached: dict[str, list[tuple[int, int, SourceEntry]]] = {p.oz: [] for p in lv.positionen}
    rejected, seen = [], set()
    for index, source in enumerate(sources):
        oz_list = source.scope.oz
        reason = ("duplicate_spec_id" if source.spec_id in seen else
                  "missing_scope" if not oz_list else
                  "unknown_oz" if any(oz not in attached for oz in oz_list) else None)
        seen.add(source.spec_id)
        if reason:
            rejected.append(RejectedSource(spec_id=source.spec_id, reason=reason, oz=oz_list))
            continue
        reasons = verify_source(source, checked_on)
        priority = UNVERIFIED_PRIORITY if reasons else PRIORITY[source.category]
        entry = SourceEntry(spec_id=source.spec_id, source_type=source.source_type,
                            category=source.category, priority=priority,
                            verification="unverified" if reasons else "verified",
                            unverified_reasons=reasons, record=source)
        for oz in dict.fromkeys(oz_list):
            attached[oz].append((priority, index, entry))
    return SpecificationContext(
        lv={"name": lv.name, "quelle": lv.quelle}, checked_on=checked_on,
        items=[ContextItem(oz=p.oz, kurztext=p.kurztext, titel_pfad=p.titel_pfad,
                           sources=[e for _, _, e in sorted(attached[p.oz], key=lambda t: t[:2])])
               for p in lv.positionen],
        rejected_sources=rejected,
    )


def _num(value: float | Decimal) -> str:
    number = Decimal(str(value))
    return str(int(number)) if number == number.to_integral_value() else str(float(number))


def _phrase(requirement: Requirement) -> str:
    prefix = {"eq": "", "min": "at least ", "max": "at most "}[requirement.comparator]
    return f"{prefix}{_num(requirement.value)} {requirement.unit}"


def _comparable(a: Requirement, b: Requirement) -> bool:
    return (a.parameter.strip().casefold() == b.parameter.strip().casefold()
            and a.unit.strip().casefold() == b.unit.strip().casefold())


def _contradicts(a: Requirement, b: Requirement) -> bool:
    """True when no value can satisfy both structured requirements."""
    if not _comparable(a, b):
        return False
    if a.comparator == "eq" and b.comparator == "eq":
        return a.value != b.value
    if b.comparator == "eq":
        a, b = b, a
    if a.comparator == "eq":
        return a.value < b.value if b.comparator == "min" else a.value > b.value
    if a.comparator == b.comparator:
        return False
    low, high = (a, b) if a.comparator == "min" else (b, a)
    return low.value > high.value


def _reference(source: SourceRecord) -> str:
    if source.document_ref:
        return source.document_ref
    if source.source_url:
        return urlparse(source.source_url).hostname or source.source_url
    return "no reference"


def source_evidence(entry: SourceEntry, oz: str) -> Evidence:
    record = entry.record
    status = entry.verification
    if entry.unverified_reasons:
        status += f" ({', '.join(entry.unverified_reasons)})"
    parts = [_reference(record)]
    if record.location:
        parts.append(record.location)
    if record.as_of:
        parts.append(f"as of {record.as_of}")
    return Evidence(reference_id=entry.spec_id, oz=oz, source=record.source_type,
                    detail=f"{status}, priority {entry.priority}; {', '.join(parts)}")


def _fragment(entry: SourceEntry) -> str:
    head = (f"{CATEGORY_LABEL[entry.category]} {entry.spec_id} "
            f"({entry.source_type}, {entry.verification})")
    requirement = entry.record.requirement
    if requirement is None:
        return f"{head} has no structured requirement; its text is not interpreted"
    verb = "requires" if entry.verification == "verified" else "states"
    return f"{head} {verb} {_phrase(requirement)}"


def comparison_note(item: ContextItem) -> Note:
    """Note 1: every attached source of the OZ, and conflicts between structured requirements."""
    sources = item.sources
    pairs = [(a, b) for i, a in enumerate(sources) for b in sources[i + 1:]
             if a.record.requirement and b.record.requirement
             and _contradicts(a.record.requirement, b.record.requirement)]
    if any("verified" in (a.verification, b.verification) for a, b in pairs):
        head = f"Conflict for OZ {item.oz}"
    elif pairs:
        head = f"Possible conflict for OZ {item.oz} between unverified sources"
    else:
        head = f"No conflict found for OZ {item.oz} among structured requirements"
    text = f"{head}: {'; '.join(_fragment(e) for e in sources)}."
    if any(e.verification == "unverified" for e in sources):
        text += " Unverified sources are shown as unconfirmed data only."
    text += " Manual review required."
    return Note(id=f"Note1:{item.oz}", step="comparison", oz=item.oz, source="rule",
                placeholder=False, text=text,
                evidence=[source_evidence(e, item.oz) for e in sources])


def _relation(given: Requirement, standard: Requirement) -> str:
    if given.comparator == "eq" and standard.comparator == "min":
        return f"is below the minimum of {_num(standard.value)} {standard.unit}"
    if given.comparator == "eq" and standard.comparator == "max":
        return f"is above the maximum of {_num(standard.value)} {standard.unit}"
    return f"conflicts with the requirement of {_phrase(standard)}"


def standards_note(item: ContextItem) -> Note:
    """Note 2: a deviation only against a cited verified, applicable German source (priority 1)."""
    standards = [e for e in item.sources if e.priority == 1]
    if not standards:
        return Note(id=f"Note2:{item.oz}", step="standards", oz=item.oz, source="rule",
                    placeholder=False,
                    text=f"Manual review: no verified applicable German source for OZ {item.oz}.",
                    evidence=[source_evidence(e, item.oz) for e in item.sources])
    given = [e for e in item.sources if e.priority in (2, 3) and e.record.requirement]
    deviations, cited = [], {e.spec_id for e in standards}
    for standard in standards:
        rule = standard.record.requirement
        for entry in given:
            if rule and _contradicts(entry.record.requirement, rule):
                record = standard.record
                where = ", ".join(x for x in (_reference(record), record.location,
                                              record.as_of and f"as of {record.as_of}") if x)
                deviations.append(
                    f"{CATEGORY_LABEL[entry.category]} {entry.spec_id} "
                    f"({_phrase(entry.record.requirement)}) {_relation(entry.record.requirement, rule)} "
                    f"in the verified applicable German source {standard.spec_id} ({where})")
                cited.add(entry.spec_id)
    if deviations:
        text = (f"Deviation for OZ {item.oz}: {'; '.join(deviations)}. Precedence and contractual "
                "effect stay with a person; manual review required.")
    else:
        ids = ", ".join(e.spec_id for e in standards)
        text = (f"No deviation found for OZ {item.oz} from the verified applicable German source "
                f"{ids} among structured requirements; manual review required.")
        cited |= {e.spec_id for e in item.sources if e.verification == "verified"}
    return Note(id=f"Note2:{item.oz}", step="standards", oz=item.oz, source="rule",
                placeholder=False, text=text,
                evidence=[source_evidence(e, item.oz) for e in item.sources if e.spec_id in cited])


# Optional #13 seam: a structured model ``(batch of Position) -> raw JSON``. None = not wired.
comparison_model: llm_pruefung.MockModel | None = None


def model_findings(context: SpecificationContext, lv: LV) -> tuple[list[Finding], int]:
    """Run the #13 model per OZ with sources; a standard may be cited only if it is priority 1
    for that OZ (``validiere_antwort`` rejects every other ``norm_ref``)."""
    if comparison_model is None:
        return [], 0
    positions = {p.oz: p for p in lv.positionen}
    findings, rejected = [], 0
    for item in context.items:
        if not item.sources:
            continue
        catalogue = {e.spec_id: f"{_reference(e.record)}, {e.record.location}, as of {e.record.as_of}"
                     for e in item.sources if e.priority == 1}
        batch: list[Position] = [positions[item.oz]]
        try:
            raw = comparison_model(batch)
        except Exception:
            rejected += 1
            continue
        result = llm_pruefung.validiere_antwort(raw, batch, catalogue)
        findings += result.findings
        rejected += len(result.rejected)
    return findings, rejected


def specification_step(request: StepRequest) -> StepResponse:
    context = build_specification_context(request.lv, request.sources, checked_on=request.checked_on)
    build = comparison_note if request.step == "comparison" else standards_note
    notes = [build(item) for item in context.items if item.sources]
    errors = [StepError(step=request.step, code="source_rejected",
                        message=f"Source {r.spec_id} was not attached ({r.reason}).")
              for r in context.rejected_sources]
    findings: list[Finding] = []
    if request.step == "comparison":
        findings, rejected = model_findings(context, request.lv)
        if rejected:
            errors.append(StepError(step=request.step, code="model_output_rejected",
                                    message=f"{rejected} model output(s) failed validation and were dropped."))
    return complete(request, notes, findings, errors)


# ---------------------------------------------------------------------------------------------
# #20 adapter: case selection and Notes 3/4 (docs/schaetzszenarien.md §2-§4)
# ---------------------------------------------------------------------------------------------
LIMIT_RANGE = (3, 20)
MIN_CASES, TARGET_CASES = 3, 10
RATIO_METHODS = ("median",)
LABEL = "Estimate – approval required"
RATIO_STEP, VALUE_STEP = Decimal("0.0001"), Decimal("0.01")
UNIT_ALIASES = {"h": ("h", "Std", "Std.", "hour", "hours"), "d": ("d", "day", "days", "Tag", "Tage"),
                "m2": ("m2", "m²", "qm"), "m3": ("m3", "m³", "cbm")}
Mode = Literal["comparable", "what_if"]


class SelectedCase(Vertrag):
    case_id: str
    date: date
    tags: list[str]
    description: str
    case_oz: str
    title_path: list[str]
    estimated_value: Decimal
    real_value: Decimal
    unit: str
    ratio: Decimal


class ExcludedCase(Vertrag):
    case_id: str
    date: date
    reason: str


class CaseSelection(Vertrag):
    mode: Mode
    oz: str
    limit: int
    candidate_count: int
    status: str
    case_count: int
    selected: list[SelectedCase]
    excluded: list[ExcludedCase]


class EstimateResult(Vertrag):
    status: Literal["estimated", "factor_only", "no_factor"]
    factor: Decimal | None
    base_value: Decimal | None
    estimated_value: Decimal | None
    euro_amount: Decimal | None
    missing_evidence: list[str]


def canonical_unit(unit: str) -> str:
    stripped = unit.strip()
    for canonical, aliases in UNIT_ALIASES.items():
        if stripped.casefold() in {alias.casefold() for alias in aliases}:
            return canonical
    return stripped


def _tags(tags: Sequence[str]) -> set[str]:
    return {tag.strip().casefold() for tag in tags if tag.strip()}


def _exclusion(record: HistoryRecord, position: EstimatePosition, mode: Mode):
    """First documented exclusion reason, or the (estimated, actual) measurement pair."""
    work = _tags(position.work_tags)
    same_work = bool(work) and work <= _tags(record.tags)
    if mode == "comparable" and not same_work:
        return "work_mismatch", None
    if mode == "what_if" and same_work:
        return "comparable_case", None
    estimated = [m for m in record.estimated_values if m.metric == position.metric]
    if not estimated:
        return "missing_estimated_value", None
    if len(estimated) > 1:
        return "ambiguous_measurement", None
    est = estimated[0]
    real = [m for m in record.real_values
            if (m.metric, m.oz, m.title_path) == (est.metric, est.oz, est.title_path)]
    if not real:
        return "missing_real_value", None
    if len(real) > 1:
        return "ambiguous_measurement", None
    act = real[0]
    if est.value is None:
        return "missing_estimated_value", None
    if act.value is None:
        return "missing_real_value", None
    target = canonical_unit(position.unit)
    if canonical_unit(est.unit) != target or canonical_unit(act.unit) != target:
        return "incompatible_unit", None
    if est.value == 0:
        return "zero_estimated_value", None
    if est.value < 0 or act.value < 0:
        return "negative_value", None
    return None, (est, act)


def _recency(record) -> tuple[int, str]:
    return -record.date.toordinal(), record.case_id


def select_cases(position: EstimatePosition, history: Sequence[HistoryRecord], mode: Mode,
                 limit: int = 20) -> CaseSelection:
    """Pure and deterministic; every input case is either selected or excluded."""
    base = {"mode": mode, "oz": position.oz, "limit": limit, "candidate_count": len(history)}
    if isinstance(limit, bool) or not isinstance(limit, int) or not LIMIT_RANGE[0] <= limit <= LIMIT_RANGE[1]:
        return CaseSelection(**base, status="invalid_limit", case_count=0, selected=[], excluded=[])
    qualifying, excluded = [], []
    for record in sorted(history, key=_recency):
        reason, pair = _exclusion(record, position, mode)
        if reason:
            excluded.append(ExcludedCase(case_id=record.case_id, date=record.date, reason=reason))
            continue
        est, act = pair
        estimated, real = Decimal(str(est.value)), Decimal(str(act.value))
        qualifying.append(SelectedCase(
            case_id=record.case_id, date=record.date, tags=record.tags,
            description=record.description, case_oz=est.oz, title_path=est.title_path,
            estimated_value=estimated, real_value=real, unit=canonical_unit(position.unit),
            ratio=(real / estimated).quantize(RATIO_STEP, ROUND_HALF_EVEN)))
    selected = qualifying[:limit]
    excluded += [ExcludedCase(case_id=c.case_id, date=c.date, reason="over_limit")
                 for c in qualifying[limit:]]
    excluded.sort(key=_recency)
    count = len(selected)
    status = ("no_history" if not history else "no_qualifying_cases" if count == 0 else
              "insufficient_cases" if count < MIN_CASES else
              "small_dataset" if count < TARGET_CASES else "sufficient")
    return CaseSelection(**base, status=status, case_count=count, selected=selected, excluded=excluded)


def _median(values: list[Decimal]) -> Decimal:
    ordered, middle = sorted(values), len(values) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2


def estimate(position: EstimatePosition, selection: CaseSelection,
             assumptions: Assumptions) -> EstimateResult:
    """Factor only for an estimator-selected method; euro only for an approved estimator price."""
    missing, status = [], selection.status
    if status in ("invalid_limit", "no_history", "no_qualifying_cases", "insufficient_cases"):
        missing.append(status)
    if status == "small_dataset":
        missing.append("below_target_case_count")
    method_ok = False
    if assumptions.ratio_method is None:
        missing.append("ratio_method_not_selected")
    elif assumptions.ratio_method not in RATIO_METHODS:
        missing.append("unsupported_ratio_method")
    elif assumptions.selected_by != "estimator":
        missing.append("ratio_method_not_approved")
    else:
        method_ok = True
    factor = None
    if method_ok and status in ("sufficient", "small_dataset"):
        factor = _median([c.ratio for c in selection.selected]).quantize(RATIO_STEP, ROUND_HALF_EVEN)
    target, baseline, base = canonical_unit(position.unit), assumptions.baseline, None
    if baseline is None or baseline.value is None:
        missing.append("missing_baseline")
    elif canonical_unit(baseline.unit) != target:
        missing.append("incompatible_baseline_unit")
    else:
        base = Decimal(str(baseline.value))
    estimated = (base * factor).quantize(VALUE_STEP, ROUND_HALF_EVEN) \
        if base is not None and factor is not None else None
    price, price_ok = assumptions.unit_price, False
    if price is None or price.value is None:
        missing.append("missing_price")
    elif price.source != "estimator" or price.approved is not True:
        missing.append("price_not_approved")
    elif price.currency != "EUR" or canonical_unit(price.per_unit) != target:
        missing.append("incompatible_price_unit")
    else:
        price_ok = True
    euro = (estimated * Decimal(str(price.value))).quantize(VALUE_STEP, ROUND_HALF_EVEN) \
        if price_ok and estimated is not None else None
    return EstimateResult(
        status="estimated" if estimated is not None else "factor_only" if factor is not None
        else "no_factor", factor=factor, base_value=base, estimated_value=estimated,
        euro_amount=euro, missing_evidence=missing)


def _plain(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


def estimate_note(target: EstimateTarget, selection: CaseSelection, result: EstimateResult) -> Note:
    """Project one estimate onto the existing Note (#20 §4)."""
    position, assumptions = target.position, target.assumptions
    what_if, unit = selection.mode == "what_if", canonical_unit(position.unit)
    kind = "broader what-if case" if what_if else "comparable case"
    kind += "" if selection.case_count == 1 else "s"
    ids = [c.case_id for c in selection.selected]
    work = ", ".join(position.work_tags) or "no stated work"
    ratios = [c.ratio for c in selection.selected]
    small = selection.status == "small_dataset"

    if result.factor is not None and result.estimated_value is not None:
        calc = (f"median actual/expected ratio {_num(result.factor)} × baseline "
                f"{_num(result.base_value)} {unit} = {_num(result.estimated_value)} {unit}.")
    elif result.factor is not None:
        missing_base = "no baseline" if "missing_baseline" in result.missing_evidence \
            else "baseline unit not compatible"
        calc = f"median actual/expected ratio {_num(result.factor)}; {missing_base}, no {position.metric} estimate."
    else:
        calc = "no historical factor."
    text = f"{LABEL}. " + ("What-if (hypothetical): " if what_if else "")
    text += f"OZ {position.oz}: {selection.case_count} {kind} ({', '.join(ids) or 'none'}); {calc}"
    if result.euro_amount is not None:
        text += (f" Estimator-approved price {_num(assumptions.unit_price.value)} EUR/{unit}: "
                 f"{_num(result.euro_amount)} EUR.")
    else:
        text += " No euro amount."
    if result.missing_evidence:
        text += f" Missing evidence: {', '.join(result.missing_evidence)}."

    rule = f"work other than {work}" if what_if else f"tags include {work}"
    reason = (f"{selection.case_count} most recent {'broader what-if' if what_if else 'comparable'} "
              f"cases of {selection.candidate_count}: {rule}; metric {position.metric}, unit compatible "
              f"with {unit}; ordered by date descending, ties by case_id; limit {selection.limit}.")
    counts = Counter(c.reason for c in selection.excluded)
    if counts:
        reason += " Excluded: " + ", ".join(f"{k} {counts[k]}" for k in sorted(counts)) + "."
    reason += {
        "sufficient": " Target of 10–20 cases met.",
        "small_dataset": " Small dataset: below the target of 10 cases.",
        "insufficient_cases": " Below the minimum of 3 cases; no factor.",
        "no_qualifying_cases": " No qualifying cases; no factor.",
        "no_history": " No history records supplied; no factor.",
        "invalid_limit": " Limit must be an integer from 3 to 20; no selection.",
    }[selection.status]

    hypothetical = "Hypothetical: if this item behaved like broader recent cases of other work. "
    baseline = assumptions.baseline
    if result.factor is not None and result.base_value is not None:
        assumption = (f"Estimator-selected median actual/expected ratio {_num(result.factor)} applied "
                      f"to the baseline {_num(result.base_value)} {unit} ({baseline.source}).")
    elif result.factor is not None:
        assumption = (f"Estimator-selected median actual/expected ratio {_num(result.factor)}; "
                      + ("no baseline supplied." if "missing_baseline" in result.missing_evidence
                         else f"baseline unit is not compatible with {unit}."))
    elif "ratio_method_not_selected" in result.missing_evidence:
        assumption = "No ratio method selected by the estimator; no factor applied."
    elif "unsupported_ratio_method" in result.missing_evidence:
        assumption = "Unsupported ratio method; only median is defined; no factor applied."
    elif "ratio_method_not_approved" in result.missing_evidence:
        assumption = "Ratio method was not selected by the estimator; no factor applied."
    else:
        assumption = "Estimator selected the median ratio, but the case pool does not support a factor."
    if what_if:
        assumption = hypothetical + assumption

    spread = (f"Case ratios range {_num(min(ratios))}–{_num(max(ratios))} over "
              f"{selection.case_count} cases." if ratios else "No case ratios.")
    if result.factor is not None:
        uncertainty = spread + (" Small dataset below the target of 10 cases." if small else "") \
            + " Past ratios do not prove future effort; no calibrated confidence."
    else:
        uncertainty = f"No factor: {', '.join(result.missing_evidence)}. {spread}"
    if what_if:
        uncertainty = "Hypothetical and less certain than Note 3: cases of other work. " + uncertainty

    evidence = [Evidence(
        reference_id=c.case_id, oz=position.oz, source="history",
        detail=(f"case OZ {c.case_oz}, {c.date.isoformat()}: expected {_num(c.estimated_value)} {unit} "
                f"/ actual {_num(c.real_value)} {unit}, ratio {_num(c.ratio)}; "
                f"tags {', '.join(c.tags) or 'none'}"),
    ) for c in selection.selected]
    return Note(
        id=f"{'Note4' if what_if else 'Note3'}:{position.oz}",
        step="what_if" if what_if else "historical_adjustment", oz=position.oz, source="rule",
        placeholder=False, text=text, manual_review=True, evidence=evidence, case_ids=ids,
        case_count=selection.case_count, selection_reason=reason,
        base_value=_plain(result.base_value), estimated_value=_plain(result.estimated_value),
        unit=unit, assumption=assumption, uncertainty=uncertainty, approval_required=True,
    )


class HistoryUnavailable(Exception):
    """Raised by a history service that cannot answer; reported as `history_unavailable`."""


# Optional #18 seam: ``(position, mode) -> records``. None = no history service connected.
HistoryService = Callable[[EstimatePosition, Mode], Sequence[HistoryRecord]]
history_service: HistoryService | None = None
OPEN_SPEC_CAVEAT = " Estimate does not account for the open specification note"


def estimate_step(request: StepRequest) -> StepResponse:
    mode: Mode = "comparable" if request.step == "historical_adjustment" else "what_if"
    notes = []
    for target in request.estimates:
        history: Sequence[HistoryRecord] = request.history_records
        if not history:
            if history_service is None:
                return step_error(request, "history_unavailable",
                                  "No history records supplied; history service is not connected.")
            try:
                history = [HistoryRecord.model_validate(r.model_dump() if isinstance(r, Vertrag) else r)
                           for r in history_service(target.position, mode)]
            except Exception:
                return step_error(request, "history_unavailable",
                                  "History service failed; previous notes were preserved.",
                                  retryable=True)
        selection = select_cases(target.position, history, mode, target.limit)
        note = estimate_note(target, selection, estimate(target.position, selection, target.assumptions))
        if mode == "what_if":
            comparable = {c for n in request.previous_notes
                          if n.step == "historical_adjustment" and n.oz == note.oz for c in n.case_ids}
            if comparable & set(note.case_ids):
                return step_error(request, "case_pool_overlap",
                                  f"What-if cases for OZ {note.oz} overlap the comparable Note 3 cases; "
                                  "the case pools must stay separate.")
        open_specs = [n.id for n in request.previous_notes
                      if n.step in ("comparison", "standards") and n.oz == note.oz and n.manual_review]
        if open_specs:
            note.uncertainty += f"{OPEN_SPEC_CAVEAT} ({', '.join(open_specs)})."
        notes.append(note)
    return complete(request, notes, [], [])


def complete(request: StepRequest, notes: list[Note], findings: list[Finding],
             errors: list[StepError]) -> StepResponse:
    """New notes replace earlier notes with the same ID in place; others are appended."""
    new = {n.id: n for n in notes}
    merged = [new.pop(n.id) if n.id in new else n for n in request.previous_notes]
    merged += [n for n in notes if n.id in new]
    return StepResponse(step=request.step, status="complete", notes=merged, findings=findings,
                        evidence=[e for n in notes for e in n.evidence], errors=errors)


@router.post(
    "/api/comparison/steps", response_model=StepResponse,
    responses={200: {"content": {"application/json": {"example": StepResponse(
        step="comparison", status="placeholder", notes=[Note(
            id="Note1", step="comparison", oz="01.001",
            text="Synthetic placeholder: 10 cm / 12 cm conflict; manual review required. "
                 "Applicable standard evidence is missing; no verified norm breach.",
            evidence=[Evidence(reference_id=s["id"], oz=s["oz"], source=s["source"], detail=s["text"])
                      for s in CONFLICT_EXAMPLE["specifications"]],
        )], evidence=[Evidence(reference_id=s["id"], oz=s["oz"], source=s["source"], detail=s["text"])
                      for s in CONFLICT_EXAMPLE["specifications"]],
    ).model_dump()}}}},
)
def comparison_step(request: StepRequest) -> StepResponse:
    from ..pruefung.normen import mit_register_quellen  # B4 #97; late import: normen builds on this module
    request = mit_register_quellen(request)  # checked norm register key values as Note 2 sources
    if request.sources or request.estimates:
        adapter = specification_step if request.sources else estimate_step
        try:
            return adapter(request)
        except Exception:
            return step_error(request, "step_failed", "Step failed; previous notes were preserved.")
    if request.step in ("historical_adjustment", "what_if") and not request.history_records:
        return step_error(request, "history_unavailable",
                          "No history records supplied; history service is not connected.")
    try:
        note = synthetic_note(request)
    except Exception:
        return step_error(request, "step_failed", "Step failed; previous notes were preserved.")
    if note is None:
        return step_error(request, "placeholder_unavailable",
                          "Specifications or history records alone only answer the documented synthetic "
                          "fixture; send sources with checked_on (Notes 1/2) or estimates (Notes 3/4).")
    return StepResponse(step=request.step, status="placeholder",
                        notes=[*request.previous_notes, note], evidence=note.evidence)

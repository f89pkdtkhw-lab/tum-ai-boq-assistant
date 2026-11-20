"""Offline HTTP contract; all new notes are fixed synthetic placeholders."""
from datetime import date
from typing import Literal

from fastapi import APIRouter
from pydantic import Field, model_validator

from ..modelle import Finding, LV, Vertrag

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
    source: Literal["model_mock"] = "model_mock"
    placeholder: Literal[True] = True
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


class StepRequest(Vertrag):
    step: Step
    lv: LV
    specifications: list[Specification] = Field(default_factory=list)
    history_records: list[HistoryRecord] = Field(default_factory=list)
    previous_notes: list[Note] = Field(default_factory=list)

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
        return self


class StepError(Vertrag):
    step: Step
    code: str
    message: str
    retryable: bool = False


class StepResponse(Vertrag):
    step: Step
    status: Literal["placeholder", "error"]
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
StepRequest.model_config["json_schema_extra"] = {"examples": [CONFLICT_EXAMPLE]}


def step_error(request: StepRequest, code: str, message: str) -> StepResponse:
    return StepResponse(step=request.step, status="error", notes=request.previous_notes,
                        errors=[StepError(step=request.step, code=code, message=message)])


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


@router.post("/api/comparison/steps", response_model=StepResponse)
def comparison_step(request: StepRequest) -> StepResponse:
    if request.step in ("historical_adjustment", "what_if") and not request.history_records:
        return step_error(request, "history_unavailable",
                          "No history records supplied; history service is not connected.")
    try:
        note = synthetic_note(request)
    except Exception:
        return step_error(request, "step_failed", "Step failed; previous notes were preserved.")
    if note is None:
        return step_error(request, "placeholder_unavailable",
                          "Only the documented synthetic fixture is supported; real adapters are pending.")
    return StepResponse(step=request.step, status="placeholder",
                        notes=[*request.previous_notes, note], evidence=note.evidence)

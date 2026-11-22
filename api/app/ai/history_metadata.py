"""Generate offline description/tag fixtures without interpreting user text as instructions."""
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import Field, model_validator

from ..modelle import LV, Vertrag
from . import llm
from .step_api import Measurement, SYNTHETIC_LV

router = APIRouter()


class UserMark(Vertrag):
    oz: str = Field(min_length=1)
    title_path: list[str] = Field(default_factory=list)
    status: str = Field(min_length=1)
    what_happened: str | None = None
    reason: str | None = None


class MetadataRequest(Vertrag):
    lv: LV
    estimated_values: list[Measurement] = Field(default_factory=list)
    real_values: list[Measurement] = Field(default_factory=list)
    comments: list[str] = Field(default_factory=list)
    marks: list[UserMark] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_references(self):
        positions = [p.oz for p in self.lv.positionen]
        if any(not oz.strip() for oz in positions) or len(set(positions)) != len(positions):
            raise ValueError("LV OZ must be nonblank and unique.")
        if any(item.oz not in positions for item in [*self.estimated_values, *self.real_values, *self.marks]):
            raise ValueError("Measurement and mark OZ must exist in the parsed case LV.")
        return self


class MetadataResponse(Vertrag):
    description: str
    tags: list[str]
    source: Literal["model_mock"]
    estimated_values: list[Measurement]
    real_values: list[Measurement]
    comments: list[str]
    marks: list[UserMark]


METADATA_EXAMPLE = {
    "lv": SYNTHETIC_LV,
    "real_values": [{"oz": "01.001", "metric": "hours", "value": 120, "unit": "h"}],
    "comments": ["Additional access work observed"],
    "marks": [{"oz": "01.001", "title_path": ["Bridge"], "status": "confirmed"}],
}
MetadataRequest.model_config["json_schema_extra"] = {"examples": [METADATA_EXAMPLE]}


@router.post("/api/history/metadata", response_model=MetadataResponse,
             response_model_exclude_unset=True,
             responses={
                 200: {"content": {"application/json": {"example": {
                     "description": "Bridge repair case.", "tags": ["bridge"], "source": "model_mock",
                     "estimated_values": [], "real_values": METADATA_EXAMPLE["real_values"],
                     "comments": METADATA_EXAMPLE["comments"], "marks": METADATA_EXAMPLE["marks"],
                 }}}},
                 503: {"description": "Offline metadata generation failed; no record was stored."},
             })
def history_metadata(request: MetadataRequest) -> MetadataResponse:
    text = " ".join([request.lv.name, *[p.kurztext + " " + p.langtext for p in request.lv.positionen]]).casefold()
    bridge = "bridge" in text or "brücke" in text
    fixture = {
        "description": "Bridge repair case." if bridge else
        f"Parsed case with {len(request.lv.positionen)} positions.",
        "tags": ["bridge"] if bridge else [],
    }
    try:
        answer = llm.StructuredRun().complete_batch([
            llm.JsonRequest(task="history_metadata", input=request.model_dump(mode="json"),
                            mock_response=fixture)
        ])[0]
    except llm.LLMError:
        raise HTTPException(status_code=503, detail={
            "code": "metadata_failed", "message": "Offline metadata generation failed; no record was stored.",
            "retryable": False,
        }) from None
    return MetadataResponse(
        description=answer.data["description"], tags=answer.data["tags"], source=answer.source,
        estimated_values=request.estimated_values, real_values=request.real_values,
        comments=request.comments, marks=request.marks,
    )

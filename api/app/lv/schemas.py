"""Versioned document exports, separate from the existing public LV contract."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Source(Schema):
    file: str
    path: str | None = None
    page: int | None = Field(default=None, ge=1)
    line: int | None = Field(default=None, ge=1)


class TextValue(Schema):
    value: str
    original: str
    sources: list[Source] = Field(min_length=1)


class DecimalValue(TextValue):
    """value is a finite decimal string; original retains the input representation."""


class Evidence(Schema):
    rule: str
    value: TextValue


class Item(Schema):
    oz: TextValue
    short_text: TextValue | None = None
    detailed_text: TextValue | None = None
    quantity: DecimalValue | None = None
    unit: TextValue | None = None
    unit_price: DecimalValue | None = None
    total_price: DecimalValue | None = None
    title_path: list[TextValue] = Field(default_factory=list)
    kind: Literal["normal", "bedarf", "alternativ", "zulage", "pauschal", "stundenlohn"] = "normal"


class RawContent(Schema):
    encoding: Literal["base64"] = "base64"
    content: str
    description: str = "Complete original bytes, including all unmapped content."


class Document(Schema):
    schema_version: Literal["1.0"] = "1.0"
    source_file: str
    sha256: str
    evidence: list[Evidence]
    phase: TextValue | None = None
    title: TextValue | None = None
    text: list[TextValue] = Field(default_factory=list)
    raw: RawContent
    warnings: list[str] = Field(default_factory=list)


class BoQDocument(Document):
    detected_type: Literal["boq"] = "boq"
    positions: list[Item] = Field(default_factory=list)
    section_totals: dict[str, DecimalValue] = Field(default_factory=dict)

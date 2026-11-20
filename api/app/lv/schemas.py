"""Versioned document exports, separate from the existing public LV contract."""
from decimal import Decimal, InvalidOperation
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Source(Schema):
    file: str = Field(min_length=1)
    path: str | None = None
    page: int | None = Field(default=None, ge=1)
    line: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def require_locator(self):
        if not (self.path or self.page or self.line):
            raise ValueError("A source needs an element path, page or line.")
        return self


class TextValue(Schema):
    value: str
    original: str
    sources: list[Source] = Field(min_length=1)


class DecimalValue(TextValue):
    """value is a finite decimal string; original retains the input representation."""

    @field_validator("value")
    @classmethod
    def finite_decimal(cls, value):
        try:
            if not Decimal(value).is_finite():
                raise InvalidOperation
        except InvalidOperation:
            raise ValueError("Expected a finite decimal string.") from None
        return value


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


class ContractDocument(Document):
    detected_type: Literal["contract"] = "contract"
    requirements: list[TextValue] = Field(default_factory=list)
    deadlines: list[TextValue] = Field(default_factory=list)
    payment_terms: list[TextValue] = Field(default_factory=list)
    parties: list[TextValue] = Field(default_factory=list)
    positions: list[Item] = Field(default_factory=list)
    section_totals: dict[str, DecimalValue] = Field(default_factory=dict)


class PriceListDocument(Document):
    detected_type: Literal["price_list"] = "price_list"
    rates: list[Item] = Field(default_factory=list)


class RegulatoryDocument(Document):
    detected_type: Literal["regulatory"] = "regulatory"
    requirements: list[TextValue] = Field(default_factory=list)
    companies: list[TextValue] = Field(default_factory=list)
    countries: list[TextValue] = Field(default_factory=list)


class UnknownDocument(Document):
    detected_type: Literal["unknown"] = "unknown"


ParsedDocument = BoQDocument | ContractDocument | PriceListDocument | RegulatoryDocument | UnknownDocument
DOCUMENT_SCHEMAS = {"boq": BoQDocument, "contract": ContractDocument, "price_list": PriceListDocument,
                    "regulatory": RegulatoryDocument, "unknown": UnknownDocument}

"""Shared BoQ contract; JSON numbers, unknown quantities/prices remain null."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Vertrag(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Position(Vertrag):
    oz: str = Field(min_length=1)
    kurztext: str = ""
    langtext: str = ""
    menge: float | None = None
    einheit: str | None = None
    ep: float | None = None
    gp: float | None = None
    typ: Literal["normal", "bedarf", "alternativ", "zulage", "pauschal", "stundenlohn"] = "normal"
    titel_pfad: list[str] = Field(default_factory=list)


class LV(Vertrag):
    name: str = Field(min_length=1)
    quelle: str = Field(min_length=1)
    positionen: list[Position] = Field(default_factory=list)
    # Supplied section totals; key = section path joined with " / ". Missing totals = {}.
    summen: dict[str, float] = Field(default_factory=dict)


class Finding(Vertrag):
    id: str = Field(min_length=1)
    oz: str = Field(min_length=1)
    kategorie: Literal["fehler", "risiko", "nachtrag"]
    schwere: Literal["kritisch", "hoch", "mittel", "niedrig"]
    titel: str = Field(min_length=1)
    begruendung: str = Field(min_length=1)
    vorschlag: str = Field(min_length=1)
    quelle: Literal["regel", "modell"]
    regel_id: str = Field(min_length=1)
    euro_wirkung: float | None = None


class Kennzahlen(Vertrag):
    positionen: int = Field(ge=0)
    findings: int = Field(ge=0)
    kritisch: int = Field(ge=0)
    modell_mock: bool = True


class ScoreAbzug(Vertrag):
    grund: str
    punkte: float
    bericht: Literal["regelwerk", "vergleich", "was_wenn"]


class Zusammenfassung(Vertrag):
    score: float = Field(ge=0, le=10)
    score_abzuege: list[ScoreAbzug] = Field(default_factory=list)
    schaetzung_abweichung_eur: float | None = None
    grosse_probleme: int = Field(ge=0)
    warnungen: int = Field(ge=0)
    hinweise: int = Field(ge=0)
    empfehlungen: int = Field(ge=0)


class Pruefbericht(Vertrag):
    lv: LV
    findings: list[Finding]
    kennzahlen: Kennzahlen
    zusammenfassung: Zusammenfassung | None = None


class Beispiel(Vertrag):
    id: str
    titel: str
    beschreibung: str
    lv: LV


class Beispiele(Vertrag):
    items: list[Beispiel]

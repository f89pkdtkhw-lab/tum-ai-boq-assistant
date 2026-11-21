"""Shared BoQ contract; JSON numbers, unknown quantities/prices remain null."""
from typing import Any, Literal
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


# --- Price calculation (B6 #112, epic #93): optional, absent unless a price list is supplied ---

def _ohne_null(wert) -> bool:
    return wert is None


class PreislistenEintrag(Vertrag):
    """One price-list row; mirrors the D4 (#111) contract from epic #93."""
    id: str = Field(min_length=1)
    oz: str | None = None
    kurztext: str = ""
    einheit: str = Field(min_length=1)
    ep: float
    quelle: str = ""


class Preisliste(Vertrag):
    id: str = Field(min_length=1)
    dateiname: str = ""
    waehrung: str = "EUR"
    eintraege: list[PreislistenEintrag] = Field(default_factory=list)
    warnungen: list[str] = Field(default_factory=list)


class KalkulationsPosition(Vertrag):
    oz: str
    kurztext: str = ""
    menge: float | None = None
    einheit: str | None = None
    ep: float | None = None            # unit price from the price list
    gp: float | None = None            # menge × ep, rounded to cents; null without match or quantity
    ep_lv: float | None = None         # the bill's own prices, kept unchanged
    gp_lv: float | None = None
    ep_differenz: float | None = None  # ep - ep_lv, only when both exist
    gp_differenz: float | None = None  # gp - gp_lv, only when both exist
    treffer: Literal["oz", "text", "aehnlich", "kein_treffer"]
    preis_eintrag: str | None = None   # PreislistenEintrag.id
    aehnlichkeit: float | None = None  # short-text token similarity 0–1
    in_summe: bool


class Kalkulation(Vertrag):
    preisliste_id: str | None = None
    waehrung: str = "EUR"
    mwst_satz: float
    positionen: list[KalkulationsPosition] = Field(default_factory=list)
    summe_netto: float
    summe_brutto: float
    ohne_preis: int = Field(ge=0)      # positions without a price-list match
    ohne_menge: int = Field(ge=0)      # matched positions whose quantity is unknown (gp null)
    vollstaendig: bool                 # every summed position has a gp


# --- B5 (#98): three reports, final report and what-if list (epic #93 contract; optional) ---
class Zaehler(Vertrag):
    """Severity groups per report: big problem = kritisch/hoch, warning = mittel, notice = niedrig."""

    grosse_probleme: int = Field(default=0, ge=0)
    warnungen: int = Field(default=0, ge=0)
    hinweise: int = Field(default=0, ge=0)
    empfehlungen: int = Field(default=0, ge=0)
    zu_grosse_naeherungen: int = Field(default=0, ge=0)


class Naeherung(Vertrag):
    """± approximation of one item quantity from similar projects (Report 2, approval required)."""

    oz: str
    kurztext: str = ""
    einheit: str
    menge: float
    geschaetzt: float
    abweichung: float
    abweichung_prozent: float
    abweichung_eur: float | None = None
    zu_gross: bool = False
    faktor: float
    case_ids: list[str] = Field(default_factory=list)
    note_id: str
    warum: str


class WasWenn(Vertrag):
    """Problem from notes/marks of past cases with its chance in this project; never a penalty."""

    oz: str | None = None
    problem: str
    chance: Literal["hoch", "niedrig"]
    empfehlung: str = ""
    case_ids: list[str] = Field(default_factory=list)
    begruendung: str = ""


class Bericht(Vertrag):
    id: Literal["regelwerk", "vergleich", "was_wenn"]
    titel: str
    status: Literal["ok", "nicht_verbunden", "fehler"]
    meldung: str = ""
    finding_ids: list[str] = Field(default_factory=list)
    notes: list[dict[str, Any]] = Field(default_factory=list)  # serialised step API `Note` objects
    neue_tags: list[str] = Field(default_factory=list)  # Report 2 only, when no comparable tag exists
    tags: list[str] = Field(default_factory=list)  # Report 2: comparable DB tags found for this LV
    zaehler: Zaehler = Field(default_factory=Zaehler)
    naeherungen: list[Naeherung] = Field(default_factory=list)
    probleme: list[WasWenn] = Field(default_factory=list)  # Report 2: problems of similar projects


class ProblemVerweis(Vertrag):
    finding_id: str
    schwere: Literal["kritisch", "hoch", "mittel", "niedrig"]
    titel: str
    quelle: Literal["regel", "modell"]
    regel_id: str
    bericht: Literal["regelwerk", "vergleich", "was_wenn"] = "regelwerk"


class SchlussPosition(Vertrag):
    """One row per bill item, in LV order; no item is ever dropped."""

    oz: str
    kurztext: str = ""
    menge: float | None = None
    einheit: str | None = None
    geschaetzt: float | None = None
    abweichung: float | None = None
    abweichung_eur: float | None = None
    warum: str = ""
    nachtrag: list[str] = Field(default_factory=list)
    probleme: list[ProblemVerweis] = Field(default_factory=list)
    warnungen: list[str] = Field(default_factory=list)
    empfehlungen: list[str] = Field(default_factory=list)


class Schlussbericht(Vertrag):
    projektbeschreibung: str
    positionen: list[SchlussPosition]
    allgemein: list[ProblemVerweis] = Field(default_factory=list)  # findings whose OZ is not an item
    warnungen: list[str] = Field(default_factory=list)


class Pruefbericht(Vertrag):
    lv: LV
    findings: list[Finding]
    kennzahlen: Kennzahlen
    zusammenfassung: Zusammenfassung | None = None
    kalkulation: Kalkulation | None = Field(default=None, exclude_if=_ohne_null)  # B6 #112
    # B5 (#98), optional: always three reports in the order regelwerk, vergleich, was_wenn.
    berichte: list[Bericht] | None = None
    was_wenn: list[WasWenn] | None = None
    schlussbericht: Schlussbericht | None = None


class Beispiel(Vertrag):
    id: str
    titel: str
    beschreibung: str
    lv: LV


class Beispiele(Vertrag):
    items: list[Beispiel]

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
    # #147, optional: why the configured model was not used (fallback to the mock), and which model reviewed.
    # Both are absent when the mock runs by configuration, so mock-mode reports stay byte-identical.
    modell_reason: str | None = Field(default=None, exclude_if=lambda wert: wert is None)
    modell: str | None = Field(default=None, exclude_if=lambda wert: wert is None)  # e.g. "gemini/gemini-2.5-flash"


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
    preisliste_id: str | None = None   # B9 (#133): source of the price, upload id or "preis-db"
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
    warnungen: list[str] = Field(default_factory=list)  # B9 (#133): e.g. price database unreachable


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


# --- B7 (#113): structured adjustments from the reports (epic #93, "Price calculation") ---------
class Anpassung(Vertrag):
    """One machine-readable change for the estimated bill (B8). Never carries a price."""
    id: str = Field(min_length=1)
    # Item concerned; for "hinzufuegen" the new item's OZ (also `position.oz`).
    oz: str = Field(min_length=1)
    art: Literal["menge", "hinzufuegen", "entfernen"]
    menge_alt: float | None = None
    menge_neu: float | None = None
    position: Position | None = None  # only for "hinzufuegen": kurztext, einheit, menge, titel_pfad
    grund: str = Field(min_length=1)
    bericht: Literal["regelwerk", "vergleich", "was_wenn"]
    finding_id: str | None = None  # finding or note id the adjustment comes from
    freigabe_noetig: bool = False  # an estimator must approve it before it counts
# --- end B7 ---------------------------------------------------------------------------------------


# --- B8 (#114): new estimated bill with the adjustments applied (epic #93, "Price calculation") ---
class GeschaetztePosition(Vertrag):
    """One row of the estimated bill; every original item stays, removed ones with `gp_neu` 0."""
    oz: str
    status: Literal["unchanged", "updated", "added", "removed"]
    kurztext: str = ""
    einheit: str | None = None
    menge_alt: float | None = None     # null for added items
    menge_neu: float | None = None     # 0 for removed items
    ep: float | None = None            # unit price from the price list; null without a match
    gp_alt: float | None = None
    gp_neu: float | None = None
    anpassung_ids: list[str] = Field(default_factory=list)
    grund: str = ""
    freigabe_noetig: bool = False      # true for adjustments from Report 2/3 or needing approval
    in_summe: bool = True              # false for "bedarf"/"alternativ" items, as in `kalkulation`


class StatusAnzahl(Vertrag):
    unchanged: int = Field(default=0, ge=0)
    updated: int = Field(default=0, ge=0)
    added: int = Field(default=0, ge=0)
    removed: int = Field(default=0, ge=0)


class GeschaetztesLv(Vertrag):
    preisliste_id: str | None = None
    waehrung: str = "EUR"
    mwst_satz: float = 0.19
    positionen: list[GeschaetztePosition] = Field(default_factory=list)
    summe_netto: float | None = None        # null without a price list
    summe_brutto: float | None = None
    differenz_netto: float | None = None    # summe_netto - kalkulation.summe_netto
    differenz_prozent: float | None = None  # null when the original net sum is 0 or unknown
    ohne_preis: int = Field(default=0, ge=0)  # kept or added rows without a unit price
    vollstaendig: bool = False                # every summed row has a gp_neu
    anzahl: StatusAnzahl = Field(default_factory=StatusAnzahl)
# --- end B8 ---------------------------------------------------------------------------------------


# --- D (#168): per-step AI status, so failures and mock fallbacks are visible in the report (optional) ---
class KiSchritt(Vertrag):
    """How one AI step ran; filled by `app.ai.ki_status.melde`. Absent steps ran as configured mock or not at all."""
    schritt: str = Field(min_length=1)  # "positionspruefung", "normrecherche", "evaluation", "vergleich", "was_wenn", …
    titel: str = Field(min_length=1)
    status: Literal["ok", "mock", "fehler", "aus"]  # ok = model answered; mock = fell back; fehler = result missing
    grund: str | None = Field(default=None, exclude_if=_ohne_null)  # UI-safe reason, e.g. timeout after 60 s
    modell: str | None = Field(default=None, exclude_if=_ohne_null)  # "anthropic/claude-sonnet-5-5"
# --- end D ---------------------------------------------------------------------------------------------


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
    anpassungen: list[Anpassung] | None = Field(default=None, exclude_if=_ohne_null)  # B7 #113
    geschaetztes_lv: GeschaetztesLv | None = Field(default=None, exclude_if=_ohne_null)  # B8 #114
    ki_schritte: list[KiSchritt] | None = Field(default=None, exclude_if=_ohne_null)  # D #168


class Beispiel(Vertrag):
    id: str
    titel: str
    beschreibung: str
    lv: LV


class Beispiele(Vertrag):
    items: list[Beispiel]


# --- Regulation document (B3, issue #96): optional, additive models for /api/regelwerk/import and
# /api/lv/analyse (body model AnalyseAnfrage lives in main.py, B6). Shared contract of epic #93; existing models above stay unchanged.
class RegelwerkNormverweis(Vertrag):
    norm_id: str = Field(min_length=1)  # normalised designation, e.g. "DIN 1045-2"
    ausgabe: str | None = None  # edition "2008-08" or year, if stated
    fundstelle: str = Field(min_length=1)  # "<file>, page <p>, line <l>" of the first occurrence


class RegelwerkKennwert(Vertrag):
    norm: str | None = None  # norm the value belongs to (last reference before it), if any
    kennwert: str = Field(min_length=1)  # "min_strength_class" or the stated name, e.g. "Betondeckung c_nom"
    wert: str = Field(min_length=1)  # as a string: "C30/37", "40", "0.035"
    einheit: str | None = None
    fundstelle: str = Field(min_length=1)
    bedingung: str | None = None  # condition, e.g. exposure class "XC4"
    vergleich: Literal["min", "max"] | None = None


class Regelwerk(Vertrag):
    id: str = Field(min_length=1)
    dateiname: str = Field(min_length=1)
    normverweise: list[RegelwerkNormverweis] = Field(default_factory=list)
    kennwerte: list[RegelwerkKennwert] = Field(default_factory=list)
    warnungen: list[str] = Field(default_factory=list)

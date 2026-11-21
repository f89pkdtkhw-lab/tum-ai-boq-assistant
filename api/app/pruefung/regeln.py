"""Fixed domain rules without model calls: arithmetic and formal BoQ checks.

Five contractually defined rule IDs (docs/schnittstelle.md): RECHENFEHLER,
EINHEIT_FEHLT, MENGE_FEHLT, LANGTEXT_FEHLT, OZ_DUPLIKAT. Further rules below
have their own stable IDs. No invented prices/standards; numbering gaps
alone do not establish missing work.
"""
import re
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from ..modelle import Finding, LV, Position

GELDTOLERANZ = Decimal("0.01")

# Known variant unit spellings; only these are treated as typos,
# unknown units are not guessed.
BEKANNTE_EINHEITEN_TIPPFEHLER = {
    "m2": "m²", "qm": "m²", "m3": "m³", "cbm": "m³",
    "stk": "St", "stck": "St", "stk.": "St", "stck.": "St",
    "lfm": "m", "psch.": "psch",
}

MENGE_EINHEIT_MUSTER = re.compile(r"(\d+(?:[.,]\d+)?)\s*(m³|m²|m|St|kg|t|h|psch)\b")


def _geld(wert: float) -> Decimal:
    return Decimal(str(wert))


def _formatiere_geld(betrag: Decimal) -> str:
    if betrag == betrag.to_integral_value():
        return str(int(betrag))
    return f"{betrag:.2f}"


def _finding(id_: str, oz: str, schwere: str, titel: str, begruendung: str, vorschlag: str,
             regel_id: str, euro_wirkung: float | None = None) -> Finding:
    return Finding(id=id_, oz=oz, kategorie="fehler", schwere=schwere, titel=titel,
                    begruendung=begruendung, vorschlag=vorschlag, quelle="regel",
                    regel_id=regel_id, euro_wirkung=euro_wirkung)


def _pruefe_rechenfehler(pos: Position) -> Finding | None:
    if pos.menge is None or pos.ep is None or pos.gp is None:
        return None  # no arithmetic findings when prices/quantities are missing
    erwartet = (_geld(pos.menge) * _geld(pos.ep)).quantize(GELDTOLERANZ, rounding=ROUND_HALF_UP)
    angegeben = _geld(pos.gp).quantize(GELDTOLERANZ, rounding=ROUND_HALF_UP)
    differenz = angegeben - erwartet
    if abs(differenz) <= GELDTOLERANZ:
        return None
    return _finding(
        f"RECHENFEHLER:{pos.oz}", pos.oz, "hoch", "Arithmetic error in total price",
        f"{pos.menge:g} × {pos.ep:g} = {_formatiere_geld(erwartet)}, supplied total price {_formatiere_geld(angegeben)}.",
        "Correct the total price to quantity × unit price.", "RECHENFEHLER",
        euro_wirkung=float(differenz),
    )


def _aus_pdf(lv: LV) -> bool:
    """The PDF importer records the uploaded file name in `LV.quelle`."""
    return lv.quelle.strip().lower().endswith(".pdf")


def _pruefe_einheit_fehlt(pos: Position, pdf: bool = False) -> Finding | None:
    if pos.einheit:
        return None
    if pdf:
        return _finding(
            f"EINHEIT_FEHLT:{pos.oz}", pos.oz, "niedrig", "Unit not read from PDF (possible parser gap)",
            "No unit was extracted from the PDF; the parser may have missed it.",
            "Check the unit in the original document.", "EINHEIT_FEHLT",
        )
    return _finding(
        f"EINHEIT_FEHLT:{pos.oz}", pos.oz, "mittel", "Missing unit",
        "Missing unit.", "Add the unit specified in the work description.", "EINHEIT_FEHLT",
    )


def _pruefe_menge_fehlt(pos: Position, pdf: bool = False) -> Finding | None:
    if pos.menge is not None:
        return None  # Zero quantity is known, not unknown
    if pdf:
        return _finding(
            f"MENGE_FEHLT:{pos.oz}", pos.oz, "niedrig", "Quantity not read from PDF (possible parser gap)",
            "No quantity was extracted from the PDF; the parser may have missed it.",
            "Check the quantity in the original document.", "MENGE_FEHLT",
        )
    return _finding(
        f"MENGE_FEHLT:{pos.oz}", pos.oz, "hoch", "Missing quantity",
        "Quantity unknown; do not treat it as zero.",
        "Ask the client for the quantity or determine it by measurement.", "MENGE_FEHLT",
    )


def _pruefe_langtext_fehlt(pos: Position) -> Finding | None:
    if pos.langtext.strip():
        return None
    return _finding(
        f"LANGTEXT_FEHLT:{pos.oz}", pos.oz, "mittel", "Missing detailed description",
        "Detailed description is empty.", "Add the complete work description.", "LANGTEXT_FEHLT",
    )


def _kanonische_einheit(einheit: str) -> str:
    """Canonical unit for a known variant spelling; any other unit is returned as written."""
    roh = einheit.strip()
    return BEKANNTE_EINHEITEN_TIPPFEHLER.get(roh.lower(), roh)


def _pruefe_einheit_tippfehler(lv: LV) -> list[Finding]:
    """Variant spellings are typos only when the same LV also uses another spelling of that unit.

    A variant used consistently on every item is the LV's convention and stays silent.
    """
    schreibweisen: dict[str, dict[str, list[Position]]] = defaultdict(lambda: defaultdict(list))
    kanonische_formen = {k.lower() for k in BEKANNTE_EINHEITEN_TIPPFEHLER.values()}
    for pos in lv.positionen:
        if not pos.einheit or not pos.einheit.strip():
            continue
        roh = pos.einheit.strip()
        if roh.lower() in BEKANNTE_EINHEITEN_TIPPFEHLER or roh.lower() in kanonische_formen:
            schreibweisen[_kanonische_einheit(roh).lower()][roh].append(pos)
    befunde = []
    for varianten in schreibweisen.values():
        if len(varianten) < 2:
            continue
        for roh, positionen in varianten.items():
            korrektur = BEKANNTE_EINHEITEN_TIPPFEHLER.get(roh.lower())
            if not korrektur:
                continue
            andere = ", ".join(f"“{s}” ({len(p)} item{'s' if len(p) != 1 else ''})"
                               for s, p in varianten.items() if s != roh)
            for pos in positionen:
                befunde.append(_finding(
                    f"EINHEIT_TIPPFEHLER:{pos.oz}", pos.oz, "niedrig", "Unusual unit spelling",
                    f"Unit “{pos.einheit}” is a known variant spelling, and this LV also uses {andere}.",
                    f"Standardize the unit to “{korrektur}”.", "EINHEIT_TIPPFEHLER",
                ))
    return befunde


def _norm_wert(text: str) -> Decimal:
    return Decimal(text.replace(",", "."))


_MASS_FAKTOR_MM = {"mm": Decimal(1), "cm": Decimal(10), "m": Decimal(1000)}


def _bezeichnung_beton(m: re.Match) -> tuple[str, str]:
    return "concrete strength class", re.sub(r"\s+", "", m.group(1)).upper()


def _bezeichnung_betonstahl(m: re.Match) -> tuple[str, str]:
    return "reinforcing steel grade", f"BSt {m.group(1)} {m.group(2).upper()}"


def _bezeichnung_exposition(m: re.Match) -> tuple[str, str]:
    return f"exposure class X{m.group(1).upper()}", m.group(0).upper()


def _bezeichnung_mass(m: re.Match) -> tuple[str, str]:
    mm = _norm_wert(m.group(2)) * _MASS_FAKTOR_MM[m.group(3).lower()]
    return f"dimension {m.group(1).lower()}", f"{m.group(1).lower()} = {mm.normalize():f} mm"


def _bezeichnung_produkt(m: re.Match) -> tuple[str, str]:
    return f"product type {m.group(1)}", f"{m.group(1)} {m.group(2)}"


def _bezeichnung_daemmung(m: re.Match) -> tuple[str, str]:
    return "thermal conductivity group", f"{m.group(1).upper()} {int(m.group(2)):03d}"


def _bezeichnung_nennweite(m: re.Match) -> tuple[str, str]:
    return "nominal diameter", f"DN {m.group(1)}"


# Designation kinds compared between short and long text. Each pattern yields
# (kind, normalized token); only tokens of the same kind can contradict.
BEZEICHNUNG_MUSTER = (
    (re.compile(r"\b(L?C\s?\d{1,3}\s?/\s?\d{1,3})\b", re.IGNORECASE), _bezeichnung_beton),
    (re.compile(r"\bB\s?St\s*(\d{3})\s*([SM])\b", re.IGNORECASE), _bezeichnung_betonstahl),
    (re.compile(r"\bX([CDFASM])\d\b"), _bezeichnung_exposition),
    (re.compile(r"\b([dhbt])\s*=\s*(\d+(?:[.,]\d+)?)\s*(mm|cm|m)\b"), _bezeichnung_mass),
    (re.compile(r"\b([A-ZÄÖÜ]{3,})\s+(\d+(?:[/-][A-Z0-9]+)+)\b"), _bezeichnung_produkt),
    (re.compile(r"\b(WL[GS])\s*(\d{2,3})\b"), _bezeichnung_daemmung),
    (re.compile(r"\bDN\s*(\d{2,4})\b"), _bezeichnung_nennweite),
)


def _bezeichnungen(text: str) -> dict[str, dict[str, str]]:
    """Designation tokens per kind: normalized key -> first spelling as written, in order of appearance."""
    gefunden: dict[str, dict[str, str]] = defaultdict(dict)
    for muster, deuten in BEZEICHNUNG_MUSTER:
        for m in muster.finditer(text):
            art, schluessel = deuten(m)
            gefunden[art].setdefault(schluessel, " ".join(m.group(0).split()))
    return gefunden


def _bezeichnungs_widersprueche(kurztext: str, langtext: str) -> list[str]:
    """Kinds named in both texts without any shared token; extra detail in the long text is no conflict."""
    kurz = _bezeichnungen(kurztext)
    lang = _bezeichnungen(langtext)
    widersprueche = []
    for art, kurz_tokens in kurz.items():
        lang_tokens = lang.get(art)
        if not lang_tokens or kurz_tokens.keys() & lang_tokens.keys():
            continue
        widersprueche.append(
            f"{art}: short description “{', '.join(kurz_tokens.values())}”, "
            f"detailed description “{', '.join(lang_tokens.values())}”")
    return widersprueche


def _pruefe_text_widerspruch(pos: Position) -> Finding | None:
    kurztext, langtext = pos.kurztext or "", pos.langtext or ""
    teile = []
    kurz = MENGE_EINHEIT_MUSTER.findall(kurztext)
    lang = MENGE_EINHEIT_MUSTER.findall(langtext)
    if pos.einheit and pos.einheit.strip():
        # compare quantities only in the item unit; other units (e.g. a thickness) are no contradiction
        einheit = _kanonische_einheit(pos.einheit)
        kurz = [m for m in kurz if m[1] == einheit]
        lang = [m for m in lang if m[1] == einheit]
    if kurz and lang and not set(kurz) & set(lang):
        teile.append(f"Short description states {kurz[0][0]} {kurz[0][1]}, "
                     f"detailed description states {lang[0][0]} {lang[0][1]}.")
    bezeichnungen = _bezeichnungs_widersprueche(kurztext, langtext)
    if bezeichnungen:
        teile.append("Conflicting designations – " + "; ".join(bezeichnungen) + ".")
    if not teile:
        return None
    vorschlag = ("Align the short and detailed descriptions on quantity/unit." if not bezeichnungen
                 else "Clarify which designation applies and align the short and detailed descriptions.")
    return _finding(
        f"TEXT_WIDERSPRUCH:{pos.oz}", pos.oz, "mittel", "Short description contradicts detailed description",
        " ".join(teile), vorschlag, "TEXT_WIDERSPRUCH",
    )


def _pruefe_oz_duplikate(lv: LV) -> list[Finding]:
    gruppen: dict[str, list[Position]] = defaultdict(list)
    for pos in lv.positionen:
        gruppen[pos.oz].append(pos)
    befunde = []
    for oz, positionen in gruppen.items():
        if len(positionen) < 2:
            continue
        pfade = ", ".join(" / ".join(p.titel_pfad) or "(no section)" for p in positionen)
        befunde.append(_finding(
            f"OZ_DUPLIKAT:{oz}", oz, "hoch", "Duplicate item number",
            f"{len(positionen)} items share OZ {oz}; distinct section paths preserved ({pfade}).",
            "Renumber one item to restore unique item numbers.", "OZ_DUPLIKAT",
        ))
    return befunde


def _pruefe_inhalt_duplikate(lv: LV) -> list[Finding]:
    gesehen: dict[tuple, Position] = {}
    befunde = []
    for pos in lv.positionen:
        schluessel = (pos.kurztext, pos.langtext, pos.einheit, pos.menge, pos.ep)
        erste = gesehen.get(schluessel)
        if erste is not None and erste.oz != pos.oz:
            befunde.append(_finding(
                f"INHALT_DUPLIKAT:{pos.oz}", pos.oz, "niedrig", "Duplicate item content",
                f"Identical content to item {erste.oz}.",
                "Check whether the item was duplicated accidentally.", "INHALT_DUPLIKAT",
            ))
        else:
            gesehen[schluessel] = pos
    return befunde


def _pruefe_titelsummen(lv: LV) -> list[Finding]:
    if not lv.summen:
        return []
    gruppen: dict[str, list[Position]] = defaultdict(list)
    for pos in lv.positionen:
        gruppen[" / ".join(pos.titel_pfad)].append(pos)
    befunde = []
    for titel_pfad, angegeben in lv.summen.items():
        positionen = gruppen.get(titel_pfad)
        if not positionen or any(p.gp is None for p in positionen):
            continue  # incomplete prices: do not claim an invented total
        summe = sum((_geld(p.gp) for p in positionen), start=Decimal("0")).quantize(
            GELDTOLERANZ, rounding=ROUND_HALF_UP)
        angegeben_dec = _geld(angegeben).quantize(GELDTOLERANZ, rounding=ROUND_HALF_UP)
        if abs(summe - angegeben_dec) <= GELDTOLERANZ:
            continue
        befunde.append(_finding(
            f"TITELSUMME_FALSCH:{positionen[0].oz}", positionen[0].oz, "mittel", "Section total mismatch",
            f"Section “{titel_pfad}”: sum of items {_formatiere_geld(summe)}, "
            f"supplied total {_formatiere_geld(angegeben_dec)}.",
            "Correct the section total to the sum of its items.", "TITELSUMME_FALSCH",
        ))
    return befunde


def pruefe_regeln(lv: LV) -> list[Finding]:
    befunde: list[Finding] = []
    pdf = _aus_pdf(lv)
    for pos in lv.positionen:
        for pruefung in (_pruefe_rechenfehler,
                         lambda p: _pruefe_einheit_fehlt(p, pdf), lambda p: _pruefe_menge_fehlt(p, pdf),
                         _pruefe_langtext_fehlt, _pruefe_text_widerspruch):
            befund = pruefung(pos)
            if befund is not None:
                befunde.append(befund)
    befunde.extend(_pruefe_einheit_tippfehler(lv))
    befunde.extend(_pruefe_oz_duplikate(lv))
    befunde.extend(_pruefe_inhalt_duplikate(lv))
    befunde.extend(_pruefe_titelsummen(lv))
    return befunde

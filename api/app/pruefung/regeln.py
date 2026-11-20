"""Feste Fachregeln ohne Modellaufruf: rechnerische und formale Prüfungen am LV.

Fünf vertraglich festgelegte Regel-IDs (docs/schnittstelle.md): RECHENFEHLER,
EINHEIT_FEHLT, MENGE_FEHLT, LANGTEXT_FEHLT, OZ_DUPLIKAT. Weitere Regeln unten
mit eigenen stabilen IDs. Keine erfundenen Preise/Normen; Nummerierungssprünge
allein gelten nicht als sicher fehlende Leistung.
"""
import re
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from ..modelle import Finding, LV, Position

GELDTOLERANZ = Decimal("0.01")

# Bekannte abweichende Schreibweisen für Einheiten; nur diese gelten als Tippfehler,
# unbekannte Einheiten werden nicht geraten.
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
        return None  # keine Rechenbefunde bei fehlenden Preisen/Mengen
    erwartet = (_geld(pos.menge) * _geld(pos.ep)).quantize(GELDTOLERANZ, rounding=ROUND_HALF_UP)
    angegeben = _geld(pos.gp).quantize(GELDTOLERANZ, rounding=ROUND_HALF_UP)
    differenz = angegeben - erwartet
    if abs(differenz) <= GELDTOLERANZ:
        return None
    return _finding(
        f"RECHENFEHLER:{pos.oz}", pos.oz, "hoch", "Rechenfehler bei Gesamtpreis",
        f"{pos.menge:g} × {pos.ep:g} = {_formatiere_geld(erwartet)}, angegeben GP {_formatiere_geld(angegeben)}.",
        "Gesamtpreis auf Menge × Einheitspreis korrigieren.", "RECHENFEHLER",
        euro_wirkung=float(differenz),
    )


def _pruefe_einheit_fehlt(pos: Position) -> Finding | None:
    if pos.einheit:
        return None
    return _finding(
        f"EINHEIT_FEHLT:{pos.oz}", pos.oz, "mittel", "Einheit fehlt",
        "Einheit fehlt.", "Einheit gemäß Leistungsbeschreibung ergänzen.", "EINHEIT_FEHLT",
    )


def _pruefe_menge_fehlt(pos: Position) -> Finding | None:
    if pos.menge is not None:
        return None  # Null-Menge ist bekannt, nicht unbekannt
    return _finding(
        f"MENGE_FEHLT:{pos.oz}", pos.oz, "hoch", "Menge fehlt",
        "Menge unbekannt; nicht als null Menge behandeln.",
        "Menge beim Auftraggeber erfragen oder im Aufmaß ermitteln.", "MENGE_FEHLT",
    )


def _pruefe_langtext_fehlt(pos: Position) -> Finding | None:
    if pos.langtext.strip():
        return None
    return _finding(
        f"LANGTEXT_FEHLT:{pos.oz}", pos.oz, "mittel", "Langtext fehlt",
        "Langtext leer.", "Vollständige Leistungsbeschreibung ergänzen.", "LANGTEXT_FEHLT",
    )


def _pruefe_einheit_tippfehler(pos: Position) -> Finding | None:
    if not pos.einheit:
        return None
    korrektur = BEKANNTE_EINHEITEN_TIPPFEHLER.get(pos.einheit.strip().lower())
    if not korrektur:
        return None
    return _finding(
        f"EINHEIT_TIPPFEHLER:{pos.oz}", pos.oz, "niedrig", "Ungewöhnliche Schreibweise der Einheit",
        f"Einheit „{pos.einheit}“ ist eine bekannte abweichende Schreibweise.",
        f"Einheit auf „{korrektur}“ vereinheitlichen.", "EINHEIT_TIPPFEHLER",
    )


def _pruefe_text_widerspruch(pos: Position) -> Finding | None:
    kurz = MENGE_EINHEIT_MUSTER.findall(pos.kurztext or "")
    lang = MENGE_EINHEIT_MUSTER.findall(pos.langtext or "")
    if not kurz or not lang or set(kurz) & set(lang):
        return None
    return _finding(
        f"TEXT_WIDERSPRUCH:{pos.oz}", pos.oz, "mittel", "Kurztext widerspricht Langtext",
        f"Kurztext nennt {kurz[0][0]} {kurz[0][1]}, Langtext nennt {lang[0][0]} {lang[0][1]}.",
        "Kurztext und Langtext auf eine gemeinsame Menge/Einheit abstimmen.", "TEXT_WIDERSPRUCH",
    )


def _pruefe_oz_duplikate(lv: LV) -> list[Finding]:
    gruppen: dict[str, list[Position]] = defaultdict(list)
    for pos in lv.positionen:
        gruppen[pos.oz].append(pos)
    befunde = []
    for oz, positionen in gruppen.items():
        if len(positionen) < 2:
            continue
        pfade = ", ".join(" / ".join(p.titel_pfad) or "(ohne Titel)" for p in positionen)
        befunde.append(_finding(
            f"OZ_DUPLIKAT:{oz}", oz, "hoch", "Doppelte Ordnungszahl",
            f"{len(positionen)} Positionen teilen die OZ {oz}; unterschiedliche Titelpfade erhalten ({pfade}).",
            "Eine der Positionen umnummerieren, OZ-Eindeutigkeit wiederherstellen.", "OZ_DUPLIKAT",
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
                f"INHALT_DUPLIKAT:{pos.oz}", pos.oz, "niedrig", "Inhaltlich doppelte Position",
                f"Identischer Inhalt wie Position {erste.oz}.",
                "Prüfen, ob die Position versehentlich doppelt angelegt wurde.", "INHALT_DUPLIKAT",
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
            continue  # unvollständige Preise: keine erfundene Summe behaupten
        summe = sum((_geld(p.gp) for p in positionen), start=Decimal("0")).quantize(
            GELDTOLERANZ, rounding=ROUND_HALF_UP)
        angegeben_dec = _geld(angegeben).quantize(GELDTOLERANZ, rounding=ROUND_HALF_UP)
        if abs(summe - angegeben_dec) <= GELDTOLERANZ:
            continue
        befunde.append(_finding(
            f"TITELSUMME_FALSCH:{positionen[0].oz}", positionen[0].oz, "mittel", "Titelsumme stimmt nicht",
            f"Titel „{titel_pfad}“: Summe der Positionen {_formatiere_geld(summe)}, "
            f"angegebene Summe {_formatiere_geld(angegeben_dec)}.",
            "Titelsumme auf die Summe der Einzelpositionen korrigieren.", "TITELSUMME_FALSCH",
        ))
    return befunde


def pruefe_regeln(lv: LV) -> list[Finding]:
    befunde: list[Finding] = []
    for pos in lv.positionen:
        for pruefung in (_pruefe_rechenfehler, _pruefe_einheit_fehlt, _pruefe_menge_fehlt,
                         _pruefe_langtext_fehlt, _pruefe_einheit_tippfehler, _pruefe_text_widerspruch):
            befund = pruefung(pos)
            if befund is not None:
                befunde.append(befund)
    befunde.extend(_pruefe_oz_duplikate(lv))
    befunde.extend(_pruefe_inhalt_duplikate(lv))
    befunde.extend(_pruefe_titelsummen(lv))
    return befunde

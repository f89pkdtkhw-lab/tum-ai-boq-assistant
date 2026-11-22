"""Score out of 10 and summary counters for the review report (epic #93, issue #94). Pure, offline.

Five selectable models (`Bewertungsmodell`). Tunable constants live in
`web/lib/bewertungsmodell-konstanten.json` (shared with the frontend).
Severity mapping (shared with the UI): big problem = kritisch/hoch, warning = mittel,
notice = niedrig, recommendation = what-if note or approval-required assumption note.
"""
from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any, Literal

from ..modelle import Finding, ScoreAbzug, Zusammenfassung

# --- Tunable constants (one place, shared with the frontend) ------------------------------------
_KONST_PFAD = Path(__file__).resolve().parents[3] / "web/lib/bewertungsmodell-konstanten.json"
KONST: dict[str, Any] = json.loads(_KONST_PFAD.read_text(encoding="utf-8"))

Bewertungsmodell = Literal["streng", "gestaffelt", "anteil", "fehler_klaerung", "ausgewogen"]
MODELLE: tuple[Bewertungsmodell, ...] = tuple(KONST["ids"])  # type: ignore[assignment]
DEFAULT_MODELL: Bewertungsmodell = KONST["default"]

SCORE_START = float(KONST["score_start"])
SCORE_MIN = float(KONST["score_min"])
ABZUG_SCHWERE = {k: float(v) for k, v in KONST["abzug"].items()}
HALB_GEWICHT = float(KONST["halb_gewicht"])
FINDINGS_CAP = float(KONST["findings_cap"])
GROESSE_BEZUG = int(KONST["groesse_bezug"])
ABZUG_BERICHT = float(KONST["streng"]["abzug_bericht"])
ABZUG_BERICHT_SCHWER = float(KONST["streng"]["abzug_bericht_schwer"])
GROSSE_PROBLEME_SCHWER = int(KONST["streng"]["grosse_probleme_schwer"])
ABZUG_APPROX = float(KONST["approx"]["abzug"])
ABZUG_APPROX_MAX = float(KONST["approx"]["max"])
APPROX_GRENZE_RELATIV = float(KONST["approx"]["grenze_relativ"])
ECHTE_FEHLER_REGELN = frozenset(KONST["echte_fehler_regeln"])
AI_QUELLEN = frozenset(KONST["ai_quellen"])
HALB_KATEGORIEN = frozenset(KONST["halb_kategorien"])
AMPEL_STRENG = (float(KONST["streng"]["ampel_gruen"]), float(KONST["streng"]["ampel_gelb"]))
AMPEL_LOCKER = (float(KONST["ampel_gruen"]), float(KONST["ampel_gelb"]))
# ------------------------------------------------------------------------------------------------

BERICHTE = ("regelwerk", "vergleich", "was_wenn")
TITEL = {"regelwerk": "Report 1", "vergleich": "Report 2", "was_wenn": "Report 3"}
GROSS = ("kritisch", "hoch")
_STEP_BERICHT = {"comparison": "regelwerk", "standards": "regelwerk",
                 "historical_adjustment": "vergleich", "what_if": "was_wenn"}
_RANG = {"kritisch": 0, "hoch": 1, "mittel": 2, "niedrig": 3}
_ANTEIL_GEWICHT = {"kritisch": 1.0, "hoch": 1.0, "mittel": 0.2, "niedrig": 0.0}


def ist_modell(wert: str | None) -> bool:
    return wert in MODELLE


def ampel_grenzen(modell: Bewertungsmodell) -> tuple[float, float]:
    """Green / yellow thresholds (inclusive) for this model."""
    return AMPEL_STRENG if modell == "streng" else AMPEL_LOCKER


def ampel_von(score: float, modell: Bewertungsmodell) -> Literal["gruen", "gelb", "rot"]:
    gruen, gelb = ampel_grenzen(modell)
    return "gruen" if score >= gruen else "gelb" if score >= gelb else "rot"


def approximation_zu_gross(note: Any) -> bool:
    """A Report 2 note whose estimate deviates from its base value by more than the limit."""
    base, est = getattr(note, "base_value", None), getattr(note, "estimated_value", None)
    if base is None or est is None or base == 0:
        return False
    return abs(est - base) / abs(base) > APPROX_GRENZE_RELATIV


def volles_gewicht(finding: Any) -> bool:
    """Real rule errors keep full weight; clarification, risk, Nachtrag and AI findings are half."""
    quelle = getattr(finding, "quelle", None) or "regel"
    if quelle in AI_QUELLEN:
        return False
    kategorie = getattr(finding, "kategorie", None) or "fehler"
    if kategorie in HALB_KATEGORIEN:
        return False
    regel_id = getattr(finding, "regel_id", "") or ""
    return kategorie == "fehler" or regel_id in ECHTE_FEHLER_REGELN


def groessen_faktor(n_positionen: int) -> float:
    """Large LVs: scale the findings deduction by sqrt(reference / n). Small LVs stay at 1."""
    n = max(int(n_positionen), 1)
    if n <= GROESSE_BEZUG:
        return 1.0
    return min(1.0, (GROESSE_BEZUG / n) ** 0.5)


def _r1(wert: float) -> float:
    return round(wert + 0.0, 1)


def _n_positionen(findings: Sequence[Finding], n_positionen: int | None) -> int:
    if n_positionen and n_positionen > 0:
        return n_positionen
    return max(len({f.oz for f in findings}), 1)


def _zuordnung(findings: Sequence[Finding], bericht_von: Callable[[Finding], str]):
    gruppen: dict[str, list[Finding]] = {b: [] for b in BERICHTE}
    for f in findings:
        gruppen[bericht_von(f) if bericht_von(f) in gruppen else "regelwerk"].append(f)
    return gruppen


def _befund_grund(titel: str, n_gross: int, n_warn: int, punkte: float, schwer: bool = False) -> str:
    teile: list[str] = []
    if n_gross:
        wort = "big problem" if n_gross == 1 else "big problems"
        teile.append(f"{n_gross} {wort}" + (" (critical or 5+)" if schwer else ""))
    if n_warn:
        teile.append(f"{n_warn} {'warning' if n_warn == 1 else 'warnings'}")
    return f"{titel}: {', '.join(teile)} (−{_r1(abs(punkte)):.1f})"


def _anteil_grund(anteil: float, punkte: float) -> str:
    pct = _r1(anteil * 100)
    if pct == int(pct):
        pct_text = str(int(pct))
    else:
        pct_text = f"{pct:.1f}"
    return f"Share of affected items: {pct_text} % (−{_r1(abs(punkte)):.1f})"


def _verteilen(roh: dict[str, float], ziel: float) -> dict[str, float]:
    """Scale per-report raw deductions so they sum to `ziel` (one decimal), preserving ratios."""
    gesamt = sum(roh.values())
    if gesamt <= 0 or ziel <= 0:
        return {b: 0.0 for b in roh}
    verteilt = {b: _r1(ziel * (wert / gesamt)) for b, wert in roh.items()}
    drift = _r1(ziel - sum(verteilt.values()))
    if drift and verteilt:
        haupt = max(verteilt, key=lambda b: verteilt[b])
        verteilt[haupt] = _r1(verteilt[haupt] + drift)
    return verteilt


def _gestaffelt_roh(findings: Sequence[Finding], mit_gewicht: bool) -> float:
    total = 0.0
    for f in findings:
        basis = ABZUG_SCHWERE.get(f.schwere, 0.0)
        faktor = 1.0 if (not mit_gewicht or volles_gewicht(f)) else HALB_GEWICHT
        total += basis * faktor
    return total


def _anteil_roh(findings: Sequence[Finding], n_positionen: int) -> tuple[float, float]:
    worst: dict[str, str] = {}
    for f in findings:
        alt = worst.get(f.oz)
        if alt is None or _RANG.get(f.schwere, 9) < _RANG.get(alt, 9):
            worst[f.oz] = f.schwere
    n = max(n_positionen, 1)
    anteil = sum(_ANTEIL_GEWICHT.get(s, 0.0) for s in worst.values()) / n
    return SCORE_START * anteil, anteil


def _findings_abzuege(findings: Sequence[Finding], bericht_von: Callable[[Finding], str],
                      n_positionen: int, modell: Bewertungsmodell) -> list[ScoreAbzug]:
    gruppen = _zuordnung(findings, bericht_von)
    if modell == "streng":
        abzuege: list[ScoreAbzug] = []
        for b in BERICHTE:
            gross = [f for f in gruppen[b] if f.schwere in GROSS]
            n = len(gross)
            if not n:
                continue
            schwer = n >= GROSSE_PROBLEME_SCHWER or any(f.schwere == "kritisch" for f in gross)
            punkte = ABZUG_BERICHT_SCHWER if schwer else ABZUG_BERICHT
            abzuege.append(ScoreAbzug(
                grund=_befund_grund(TITEL[b], n, 0, punkte, schwer=schwer),
                punkte=-_r1(punkte), bericht=b))
        return abzuege

    if modell == "anteil":
        roh, anteil = _anteil_roh(findings, n_positionen)
        punkte = min(FINDINGS_CAP, roh)
        if punkte <= 0:
            return []
        return [ScoreAbzug(grund=_anteil_grund(anteil, punkte), punkte=-_r1(punkte), bericht="regelwerk")]

    mit_gewicht = modell in ("fehler_klaerung", "ausgewogen")
    raw_by = {b: _gestaffelt_roh(gruppen[b], mit_gewicht) for b in BERICHTE}
    raw = sum(raw_by.values())
    faktor = groessen_faktor(n_positionen) if modell == "ausgewogen" else 1.0
    ziel = min(FINDINGS_CAP, raw * faktor)
    if ziel <= 0:
        return []
    verteilt = _verteilen(raw_by, ziel)
    abzuege = []
    for b in BERICHTE:
        punkte = verteilt[b]
        if punkte <= 0:
            continue
        n_gross = sum(f.schwere in GROSS for f in gruppen[b])
        n_warn = sum(f.schwere == "mittel" for f in gruppen[b])
        abzuege.append(ScoreAbzug(
            grund=_befund_grund(TITEL[b], n_gross, n_warn, punkte),
            punkte=-_r1(punkte), bericht=b))
    return abzuege


def zusammenfassen(findings: Sequence[Finding], notes: Iterable[Any] = (),
                   bericht_von: Callable[[Finding], str] | None = None,
                   n_positionen: int | None = None,
                   modell: Bewertungsmodell | str | None = None,
                   schaetzung_von: float | None = None,
                   schaetzung_bis: float | None = None) -> Zusammenfassung:
    """`bericht_von` maps a finding to its report id (B5); default: every finding is Report 1.

    `n_positionen` is the BoQ size (used by Share and Balanced). `modell` selects the formula;
    unknown values fall back to the default (Balanced). `schaetzung_von` / `schaetzung_bis`
    are the optional total estimate range (#225); usually filled later from the estimated bill.
    """
    notes = list(notes)
    gewaehlt: Bewertungsmodell = modell if ist_modell(modell) else DEFAULT_MODELL  # type: ignore[arg-type]
    zuordnung = bericht_von or (lambda f: "regelwerk")
    n = _n_positionen(findings, n_positionen)
    abzuege = _findings_abzuege(findings, zuordnung, n, gewaehlt)

    vergleich = [n_ for n_ in notes if _STEP_BERICHT.get(getattr(n_, "step", None)) == "vergleich"]
    zu_gross = sum(approximation_zu_gross(n_) for n_ in vergleich)
    if zu_gross:
        punkte = min(zu_gross * ABZUG_APPROX, ABZUG_APPROX_MAX)
        abzuege.append(ScoreAbzug(grund=f"Report 2: {zu_gross} approximation(s) too big",
                                  punkte=-_r1(punkte), bericht="vergleich"))

    score = _r1(max(SCORE_MIN, SCORE_START + sum(a.punkte for a in abzuege)))
    eur = [abs(n_.estimated_value - n_.base_value) for n_ in vergleich
           if n_.unit == "EUR" and n_.base_value is not None and n_.estimated_value is not None]
    return Zusammenfassung(
        score=score, score_abzuege=abzuege,
        schaetzung_abweichung_eur=round(sum(eur), 2) if eur else None,
        schaetzung_von=schaetzung_von, schaetzung_bis=schaetzung_bis,
        grosse_probleme=sum(f.schwere in GROSS for f in findings),
        warnungen=sum(f.schwere == "mittel" for f in findings),
        hinweise=sum(f.schwere == "niedrig" for f in findings),
        empfehlungen=sum(getattr(n_, "step", None) == "what_if"
                         or bool(getattr(n_, "assumption", None) and getattr(n_, "approval_required", False))
                         for n_ in notes),
        bewertungsmodell=gewaehlt)

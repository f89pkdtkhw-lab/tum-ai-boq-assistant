"""Score out of 10 and summary counters for the review report (epic #93, issue #94). Pure, offline.

Severity mapping (shared with the UI): big problem = kritisch/hoch, warning = mittel,
notice = niedrig, recommendation = what-if note or approval-required assumption note.
"""
from collections.abc import Callable, Iterable, Sequence
from typing import Any

from ..modelle import Finding, ScoreAbzug, Zusammenfassung

# --- Tunable constants (one place) -------------------------------------------------------------
SCORE_START = 10.0
SCORE_MIN = 0.0
ABZUG_BERICHT = 1.0            # at least one big problem in a report
ABZUG_BERICHT_SCHWER = 2.0     # >= GROSSE_PROBLEME_SCHWER big problems or any `kritisch`
GROSSE_PROBLEME_SCHWER = 5
ABZUG_APPROX = 0.1             # per approximation flagged "too big"
ABZUG_APPROX_MAX = 1.0
APPROX_GRENZE_RELATIV = 0.25   # |estimate - base| / |base| above this = "too big"
# ------------------------------------------------------------------------------------------------

BERICHTE = ("regelwerk", "vergleich", "was_wenn")
TITEL = {"regelwerk": "Report 1", "vergleich": "Report 2", "was_wenn": "Report 3"}
GROSS = ("kritisch", "hoch")
_STEP_BERICHT = {"comparison": "regelwerk", "standards": "regelwerk",
                 "historical_adjustment": "vergleich", "what_if": "was_wenn"}


def approximation_zu_gross(note: Any) -> bool:
    """A Report 2 note whose estimate deviates from its base value by more than the limit."""
    base, est = getattr(note, "base_value", None), getattr(note, "estimated_value", None)
    if base is None or est is None or base == 0:
        return False
    return abs(est - base) / abs(base) > APPROX_GRENZE_RELATIV


def zusammenfassen(findings: Sequence[Finding], notes: Iterable[Any] = (),
                   bericht_von: Callable[[Finding], str] | None = None) -> Zusammenfassung:
    """`bericht_von` maps a finding to its report id (B5); default: every finding is Report 1."""
    notes = list(notes)
    zuordnung = bericht_von or (lambda f: "regelwerk")
    gross = {b: [] for b in BERICHTE}
    for f in findings:
        if f.schwere in GROSS:
            gross[zuordnung(f)].append(f)

    abzuege: list[ScoreAbzug] = []
    for b in BERICHTE:
        n = len(gross[b])
        if not n:
            continue
        schwer = n >= GROSSE_PROBLEME_SCHWER or any(f.schwere == "kritisch" for f in gross[b])
        abzuege.append(ScoreAbzug(
            grund=f"{TITEL[b]}: {n} big problem{'s' if n != 1 else ''}"
                  + (" (critical or 5+)" if schwer else ""),
            punkte=-(ABZUG_BERICHT_SCHWER if schwer else ABZUG_BERICHT), bericht=b))

    vergleich = [n for n in notes if _STEP_BERICHT.get(getattr(n, "step", None)) == "vergleich"]
    zu_gross = sum(approximation_zu_gross(n) for n in vergleich)
    if zu_gross:
        punkte = min(zu_gross * ABZUG_APPROX, ABZUG_APPROX_MAX)
        abzuege.append(ScoreAbzug(grund=f"Report 2: {zu_gross} approximation(s) too big",
                                  punkte=-round(punkte, 1), bericht="vergleich"))

    score = round(max(SCORE_MIN, SCORE_START + sum(a.punkte for a in abzuege)), 1)
    eur = [abs(n.estimated_value - n.base_value) for n in vergleich
           if n.unit == "EUR" and n.base_value is not None and n.estimated_value is not None]
    return Zusammenfassung(
        score=score, score_abzuege=abzuege,
        schaetzung_abweichung_eur=round(sum(eur), 2) if eur else None,
        grosse_probleme=sum(len(v) for v in gross.values()),
        warnungen=sum(f.schwere == "mittel" for f in findings),
        hinweise=sum(f.schwere == "niedrig" for f in findings),
        empfehlungen=sum(getattr(n, "step", None) == "what_if"
                         or bool(getattr(n, "assumption", None) and getattr(n, "approval_required", False))
                         for n in notes))

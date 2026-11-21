"""Per-step AI status for the review report (#168, package D): failures and mock fallbacks become visible.

Every AI step of the analysis (position review, norm research, evaluation, AI checks 2/3, …) reports how it ran
with ``melde(...)``. ``erfasse()`` collects these reports while one report is built; ``main._pruefbericht`` puts them
into ``Pruefbericht.ki_schritte``. Outside ``erfasse()`` a report is dropped silently, so steps can call ``melde``
from anywhere (routes, tests, background jobs) without setup.

Steps report only when a real provider is configured or something went wrong. A mock chosen by configuration (no
key) reports nothing, so mock-mode reports stay byte-identical; the UI's demo-mode notice covers that case.

Status values: ``ok`` (the model answered), ``mock`` (a configured model was not used; offline mock shown),
``fehler`` (the step failed and its result is missing), ``aus`` (switched off by configuration).
``grund`` is a UI-safe sentence: never a key, a prompt or dataset text.
"""
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from ..modelle import KiSchritt

_SAMMLUNG: ContextVar[list[KiSchritt] | None] = ContextVar("ki_schritte", default=None)
MAX_GRUND = 300

# Readable step titles; unknown step ids keep the title the caller passes.
TITEL = {
    "positionspruefung": "AI position review",
    "normrecherche": "AI norm research",
    "evaluation": "AI evaluation",
    "vergleich": "AI check 2 (similar projects)",
    "was_wenn": "AI check 3 (what-if)",
}


@contextmanager
def erfasse() -> Iterator[list[KiSchritt]]:
    """Collect the step reports made inside the block; the yielded list fills up as steps report."""
    schritte: list[KiSchritt] = []
    token = _SAMMLUNG.set(schritte)
    try:
        yield schritte
    finally:
        _SAMMLUNG.reset(token)


def _kurz(text: str | None) -> str | None:
    if not text:
        return None
    text = " ".join(str(text).split())
    return text if len(text) <= MAX_GRUND else text[:MAX_GRUND - 1].rstrip() + "…"


def melde(schritt: str, status: str, grund: str | None = None, *, modell: str | None = None,
          titel: str | None = None) -> None:
    """Report one step; a later report of the same step replaces the earlier one. Never raises."""
    schritte = _SAMMLUNG.get()
    if schritte is None:
        return
    try:
        eintrag = KiSchritt(schritt=schritt, titel=titel or TITEL.get(schritt, schritt), status=status,
                            grund=_kurz(grund), modell=modell)
    except Exception:  # an invalid status must never break the report
        return
    schritte[:] = [s for s in schritte if s.schritt != schritt] + [eintrag]


def ergebnis(schritte: list[KiSchritt]) -> list[KiSchritt] | None:
    """The list for ``Pruefbericht.ki_schritte``: None when no step reported (field then absent)."""
    return list(schritte) or None

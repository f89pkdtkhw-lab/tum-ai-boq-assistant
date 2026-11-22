"""Progress API of the analysis pipeline (#165, package F). Small and stable: packages A, B, D and E report into it.

A pipeline step receives a `fortschritt` object and calls it:

    fortschritt(schritt, gesamt, meldung)              # step `schritt` of `gesamt` starts / says what it does
    fortschritt(schritt, gesamt, meldung, anteil=0.4)  # same step, 40 % done (optional, 0..1)
    fortschritt.fehler("AI item review: timeout, mock used")  # a visible, non-fatal problem

A higher `schritt` closes the previous step (it moves to `fertige_schritte`). Repeated calls with the same
`schritt` only update the message and the share, e.g. "Researching standards for item 01.02.0030 …".
`teilschritt(fortschritt, schritt, gesamt)` binds the numbers, so a helper deep in the pipeline only says
`melde("…", anteil)` and never needs to know the step count.

Without a job (sync routes, tests) the pipeline gets `OHNE_FORTSCHRITT`, which does nothing. Calls never
raise, except `AnalyseAbgebrochen` when the job has hit its own timeout: that stops the pipeline cleanly.
"""
from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Callable, Protocol

_AKTUELL: ContextVar["Fortschritt | None"] = ContextVar("analyse_fortschritt", default=None)


class AnalyseAbgebrochen(Exception):
    """Raised by a progress call when the job has passed its timeout; the pipeline stops there."""


class Fortschritt(Protocol):
    def __call__(self, schritt: int, gesamt: int, meldung: str, anteil: float | None = None) -> None: ...

    def fehler(self, meldung: str) -> None: ...


class _OhneFortschritt:
    """No-op progress for the synchronous routes and tests."""

    def __call__(self, schritt: int, gesamt: int, meldung: str, anteil: float | None = None) -> None:
        return None

    def fehler(self, meldung: str) -> None:
        return None


OHNE_FORTSCHRITT: Fortschritt = _OhneFortschritt()


class Aufzeichnung:
    """Progress that records every call; for tests of pipeline steps (`.meldungen`, `.fehlerliste`)."""

    def __init__(self) -> None:
        self.meldungen: list[tuple[int, int, str, float | None]] = []
        self.fehlerliste: list[str] = []

    def __call__(self, schritt: int, gesamt: int, meldung: str, anteil: float | None = None) -> None:
        self.meldungen.append((schritt, gesamt, meldung, anteil))

    def fehler(self, meldung: str) -> None:
        self.fehlerliste.append(meldung)


def teilschritt(fortschritt: Fortschritt | None, schritt: int, gesamt: int) -> Callable[..., None]:
    """`melde(meldung, anteil=None)` for one step; safe with `None`."""
    ziel = fortschritt or OHNE_FORTSCHRITT

    def melde(meldung: str, anteil: float | None = None) -> None:
        ziel(schritt, gesamt, meldung, anteil)

    return melde

def setze(fortschritt: Fortschritt | None) -> Token:
    """Bind the current analysis job so model calls can update the progress message."""
    return _AKTUELL.set(fortschritt)


def zuruecksetzen(token: Token) -> None:
    _AKTUELL.reset(token)


def aktuell() -> Fortschritt | None:
    return _AKTUELL.get()


def warte(meldung: str) -> None:
    """Update the running job's stage message (e.g. 'Wartet auf Grok Bot …').

    No-op when no job is bound. Re-raises ``AnalyseAbgebrochen`` so a timed-out
    analysis stops waiting for the queue.
    """
    ziel = _AKTUELL.get()
    if ziel is None:
        return
    schritt = max(int(getattr(ziel, "schritt", 1) or 1), 1)
    gesamt = max(int(getattr(ziel, "gesamt", 1) or 1), 1)
    ziel(schritt, gesamt, meldung)

"""Background analysis jobs (#165, package F): POST /api/lv/analyse/start → job id, GET …/status/{job_id}.

The analysis runs in a daemon thread, so no HTTP request waits for long research. Each job reports through
the progress API in `fortschritt.py`. Its timeout (`ANALYSE_JOB_TIMEOUT`, default 2400 s) is separate from
request timeouts: a job that passes it is reported as failed and stops at its next progress call. Jobs live
in memory of this process (one uvicorn worker, as `tools/dev.py` and `render.yaml` start it); finished jobs
are dropped after `ANALYSE_JOB_AUFBEWAHRUNG` seconds (default 3600).
"""
from __future__ import annotations

import contextvars
import logging
import threading
import time
import uuid
from typing import Callable, Literal

from pydantic import BaseModel

from .ai import llm
from .fortschritt import AnalyseAbgebrochen, Fortschritt, setze as setze_fortschritt, zuruecksetzen as reset_fortschritt
from .modelle import Pruefbericht

log = logging.getLogger(__name__)

MAX_PARALLEL = 4  # running jobs at once; more → HTTP 429 at start
MAX_JOBS = 32  # kept jobs (running + finished) before the oldest finished ones are dropped


class FertigerSchritt(BaseModel):
    schritt: int
    meldung: str
    sekunden: float


class AnalyseStatus(BaseModel):
    """Answer of GET /api/lv/analyse/status/{job_id}; `ergebnis` only once `status == "fertig"`."""
    job_id: str
    status: Literal["laeuft", "fertig", "fehler"]
    schritt: int
    schritte_gesamt: int
    prozent: int
    meldung: str
    fertige_schritte: list[FertigerSchritt]
    fehler: list[str]
    sekunden: float
    ergebnis: Pruefbericht | None = None


class AnalyseStart(BaseModel):
    job_id: str


class ZuVieleJobs(RuntimeError):
    """More than MAX_PARALLEL jobs are running."""


def job_timeout() -> float:
    return llm.seconds("ANALYSE_JOB_TIMEOUT", 2400)


def aufbewahrung() -> float:
    return llm.seconds("ANALYSE_JOB_AUFBEWAHRUNG", 3600)


class Job:
    """One analysis; implements the `Fortschritt` protocol for its pipeline."""

    def __init__(self, gesamt: int, timeout: float) -> None:
        self.id = uuid.uuid4().hex
        self.lock = threading.Lock()
        self.start = time.monotonic()
        self.ende: float | None = None
        self.timeout = timeout
        self.status: Literal["laeuft", "fertig", "fehler"] = "laeuft"
        self.schritt = 0
        self.gesamt = max(1, gesamt)
        self.anteil = 0.0
        self.meldung = "Waiting to start …"
        self.text = ""
        self.schritt_start = self.start
        self.fertig: list[FertigerSchritt] = []
        self.fehlerliste: list[str] = []
        self.ergebnis: Pruefbericht | None = None
        self.prozent_max = 0
        self.abgebrochen = False

    # --- Fortschritt protocol -------------------------------------------------------------------
    def __call__(self, schritt: int, gesamt: int, meldung: str, anteil: float | None = None) -> None:
        with self.lock:
            if self._abgelaufen():
                raise AnalyseAbgebrochen(f"Job timeout of {self.timeout:.0f} s reached")
            if self.status != "laeuft":
                return
            self.gesamt = max(1, int(gesamt))
            jetzt = time.monotonic()
            if schritt > self.schritt:
                self._schliesse_schritt(jetzt)
                self.schritt, self.schritt_start, self.anteil = int(schritt), jetzt, 0.0
            if anteil is not None:
                self.anteil = min(1.0, max(self.anteil, float(anteil)))
            self.text = str(meldung)
            self.meldung = f"Step {self.schritt}/{self.gesamt}: {self.text}"

    def fehler(self, meldung: str) -> None:
        with self.lock:
            text = str(meldung)[:500]
            if text and text not in self.fehlerliste:
                self.fehlerliste.append(text)

    # --- internal -------------------------------------------------------------------------------
    def _schliesse_schritt(self, jetzt: float) -> None:
        if self.schritt > 0 and self.text:
            self.fertig.append(FertigerSchritt(schritt=self.schritt, meldung=self.text,
                                               sekunden=round(jetzt - self.schritt_start, 2)))

    def _abgelaufen(self) -> bool:
        """Caller holds the lock. Marks a running job that passed its timeout as failed; True once it has."""
        if self.status == "laeuft" and time.monotonic() - self.start > self.timeout:
            self.status, self.ende, self.abgebrochen = "fehler", time.monotonic(), True
            self.fehlerliste.append(f"The analysis took longer than {self.timeout:.0f} s (ANALYSE_JOB_TIMEOUT) and was stopped.")
            self.meldung = f"Stopped at step {self.schritt}/{self.gesamt}: timeout."
        return self.abgebrochen

    def laeuft(self) -> bool:
        with self.lock:
            return not self._abgelaufen() and self.status == "laeuft"

    def beenden(self, ergebnis: Pruefbericht) -> None:
        with self.lock:
            if self.status != "laeuft":
                return  # already timed out: the late result is discarded
            jetzt = time.monotonic()
            self._schliesse_schritt(jetzt)
            self.status, self.ende, self.ergebnis = "fertig", jetzt, ergebnis
            self.schritt, self.anteil, self.meldung = self.gesamt, 1.0, "Analysis complete."

    def scheitern(self, text: str) -> None:
        with self.lock:
            if self.status != "laeuft":
                return
            self.status, self.ende = "fehler", time.monotonic()
            self.fehlerliste.append(text)
            self.meldung = f"Failed at step {self.schritt}/{self.gesamt}."

    def bericht(self) -> AnalyseStatus:
        with self.lock:
            self._abgelaufen()
            if self.status == "fertig":
                prozent = 100
            else:
                prozent = int(((max(self.schritt, 1) - 1) + self.anteil) / self.gesamt * 100) if self.schritt else 0
                prozent = min(99, prozent)
            self.prozent_max = prozent = max(self.prozent_max, prozent)
            ende = self.ende if self.ende is not None else time.monotonic()
            return AnalyseStatus(
                job_id=self.id, status=self.status, schritt=self.schritt, schritte_gesamt=self.gesamt,
                prozent=prozent, meldung=self.meldung, fertige_schritte=list(self.fertig),
                fehler=list(self.fehlerliste), sekunden=round(ende - self.start, 2),
                ergebnis=self.ergebnis if self.status == "fertig" else None,
            )


_JOBS: dict[str, Job] = {}
_JOBS_LOCK = threading.Lock()


def _aufraeumen() -> None:
    """Caller holds _JOBS_LOCK. Drops old finished jobs, then the oldest finished ones above MAX_JOBS."""
    jetzt = time.monotonic()
    fertig = sorted((j for j in _JOBS.values() if j.ende is not None), key=lambda j: j.ende or 0)
    for job in fertig:
        if jetzt - (job.ende or jetzt) > aufbewahrung() or len(_JOBS) > MAX_JOBS:
            _JOBS.pop(job.id, None)


def starte(arbeit: Callable[[Fortschritt], Pruefbericht], gesamt: int) -> str:
    """Runs `arbeit(fortschritt)` in a daemon thread and returns the job id at once."""
    with _JOBS_LOCK:
        _aufraeumen()
        laufend = sum(1 for j in _JOBS.values() if j.laeuft())
        if laufend >= MAX_PARALLEL:
            raise ZuVieleJobs(f"{laufend} analyses are already running. Please wait until one has finished.")
        job = Job(gesamt, job_timeout())
        _JOBS[job.id] = job

    def lauf() -> None:
        token = setze_fortschritt(job)
        try:
            job.beenden(arbeit(job))
        except AnalyseAbgebrochen:
            pass  # status already says timeout
        except Exception as exc:  # the pipeline must never kill the thread silently
            log.exception("Analysis job %s failed", job.id)
            job.scheitern(f"The analysis failed: {type(exc).__name__}: {str(exc)[:300]}")
        finally:
            reset_fortschritt(token)

    # copy_context: the job thread keeps the request's answer language (#196)
    threading.Thread(target=contextvars.copy_context().run, args=(lauf,), name=f"analyse-{job.id[:8]}",
                     daemon=True).start()
    return job.id


def status(job_id: str) -> AnalyseStatus | None:
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
    return job.bericht() if job else None

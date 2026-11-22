"""Deep research with web search in every AI step (#169, package E of epic #93).

After the review report is built, Claude checks the **conspicuous** parts of it against current public
sources found with the server-side ``web_search`` tool, and every result names its sources:

- ``positionen``: findings of severity kritisch/hoch/mittel and all risk/Nachtrag findings (item review, risk
  scoring), grouped by trade (first section of the item's title path). One call per trade group.
- ``preise``: price plausibility. Items whose own unit price (EP) deviates from the price list or price
  database by at least ``PREIS_SCHWELLE``, or that have an EP but no price match, grouped by trade; Claude
  researches current market prices. Only an implausible price backed by a found source becomes a finding.
- ``berichte``: Reports 2/3 problems of similar projects and what-if items; Claude checks how likely they
  are for this kind of work.

Every call goes through the shared research helper ``llm.research`` of package A (#166).

Cost and time are bounded (never one call per item of a 2,500-item bill):

    DEEP_RESEARCH              0/off/false/no switches it off (default on when Claude has a key)
    DEEP_RESEARCH_MAX_USES     web searches per call (default 8)
    DEEP_RESEARCH_MAX_CALLS    research calls per analysis (default 24)
    DEEP_RESEARCH_BUDGET       web searches per analysis across all calls (default 192 = calls × uses,
                               so the call cap is not starved)
    DEEP_RESEARCH_MAX_ITEMS    items or findings per group (default 12)
    DEEP_RESEARCH_TIMEOUT      seconds for all research of one analysis (default 420)
    DEEP_RESEARCH_PARALLEL     concurrent calls (default 6)

Without a key, with another provider or switched off, the report is returned unchanged (no
``recherche`` field, byte-identical to before). With a key, ``Pruefbericht.recherche`` always says what
ran, what it cost and why something did not run, so failures are visible, never silent.

Anti-hallucination: a source counts only when its URL was actually returned by a web search or cited
in this call; results without such a source are dropped. Prices are quoted only from found sources;
no standard is invented (norm research itself is package A, ``normen_ki``).
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from collections import OrderedDict
from collections.abc import Callable
import contextvars
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from threading import Lock

from ..ai import llm
from ..fortschritt import Fortschritt, teilschritt
from ..modelle import (
    Finding, Kalkulation, KiSchritt, LV, Position, Pruefbericht, Recherche, RechercheErgebnis, RechercheQuelle,
)

log = logging.getLogger(__name__)

AUS = frozenset({"0", "off", "false", "no", "aus"})
REGEL_PREIS = "RECHERCHE_MARKTPREIS"
PREIS_SCHWELLE = 0.30  # relative EP deviation that makes a price conspicuous
MAX_LANGTEXT = 400
MAX_BEFUNDTEXT = 300
MAX_TEXT = 600
MAX_QUELLEN = 4
OHNE_ABSCHNITT = "Without section"
EINSCHAETZUNGEN = {
    "positionen": ("bestaetigt", "abgeschwaecht", "unklar"),
    "preise": ("plausibel", "zu_hoch", "zu_niedrig", "unklar"),
    "berichte": ("bestaetigt", "abgeschwaecht", "unklar"),
}
EINSCHAETZUNG_TEXT = {"bestaetigt": "confirmed", "abgeschwaecht": "weakened", "unklar": "unclear",
                      "plausibel": "plausible", "zu_hoch": "above market", "zu_niedrig": "below market"}

SYSTEM = (
    "You are a research assistant for a German construction cost estimator who reviews a bill of quantities "
    "(Leistungsverzeichnis, LV) before pricing. Use the web_search tool to check the items below against "
    "current, publicly available sources (manufacturer data sheets, trade association guidance, public "
    "summaries of DIN/VOB rules, price surveys such as BKI or published unit-price ranges). Search a few "
    "targeted queries for the whole group, not one per item. Never invent prices, standards, items or "
    "sources: cite only URLs you found with web_search in this conversation, and when you find nothing "
    "reliable, say 'unklar'. Write 'text' in English, at most three sentences, keep German domain terms. "
    "Finish with JSON only, no prose after it, exactly in the shape requested."
)

AUFGABEN = {
    "positionen": (
        "Check whether these review findings of one trade hold up against current sources (current rules, "
        "typical execution, typical Nachtrag/change-order risks). Answer with JSON: "
        '{"ergebnisse": [{"finding_id": "<id from input>", "einschaetzung": "bestaetigt|abgeschwaecht|unklar", '
        '"text": "evidence from the sources", "quellen": ["https://..."]}]}'
    ),
    "preise": (
        "Research current German market unit prices (net, per unit given) for these items of one trade and "
        "judge the bill's own unit price ep_lv. Answer with JSON: "
        '{"ergebnisse": [{"oz": "<oz from input>", "einschaetzung": "plausibel|zu_hoch|zu_niedrig|unklar", '
        '"marktpreis_von": number or null, "marktpreis_bis": number or null, '
        '"text": "price range and what it depends on, as stated in the sources", "quellen": ["https://..."]}]}'
    ),
    "berichte": (
        "These problems occurred in similar past projects. Check with current sources how likely each is for "
        "the described work and what usually prevents it. Answer with JSON: "
        '{"ergebnisse": [{"index": 0, "einschaetzung": "bestaetigt|abgeschwaecht|unklar", '
        '"text": "evidence from the sources", "quellen": ["https://..."]}]}'
    ),
}


# ----------------------------------------------------------------------------------------------
# Configuration and budget
# ----------------------------------------------------------------------------------------------
def _zahl(name: str, standard: int) -> int:
    try:
        wert = int(os.environ.get(name, "") or standard)
    except ValueError:
        return standard
    return wert if wert >= 0 else standard


# Defaults sized so every step (findings, prices, reports) can actually run, not just the first groups.
STANDARD_MAX_USES = 8
STANDARD_MAX_CALLS = 24
STANDARD_BUDGET = 192  # 24 calls × 8 searches; a lower budget would skip later groups
STANDARD_MAX_ITEMS = 12
STANDARD_TIMEOUT = 420.0
STANDARD_PARALLEL = 6
MAX_TOKENS = 16000  # output tokens per research call (hard cap for Claude; not an env setting)


@dataclass(frozen=True)
class Einstellungen:
    max_uses: int
    max_calls: int
    budget: int
    max_items: int
    timeout: float
    parallel: int

    @classmethod
    def aus_env(cls) -> "Einstellungen":
        return cls(max_uses=max(1, _zahl("DEEP_RESEARCH_MAX_USES", STANDARD_MAX_USES)),
                   max_calls=_zahl("DEEP_RESEARCH_MAX_CALLS", STANDARD_MAX_CALLS),
                   budget=_zahl("DEEP_RESEARCH_BUDGET", STANDARD_BUDGET),
                   max_items=max(1, _zahl("DEEP_RESEARCH_MAX_ITEMS", STANDARD_MAX_ITEMS)),
                   timeout=llm.seconds("DEEP_RESEARCH_TIMEOUT", STANDARD_TIMEOUT),
                   parallel=max(1, _zahl("DEEP_RESEARCH_PARALLEL", STANDARD_PARALLEL)))


class Budget:
    """Web searches of one analysis, shared by parallel calls: reserve before, settle after."""

    def __init__(self, suchen: int):
        self._frei = suchen
        self.verbraucht = 0
        self._lock = Lock()

    def reserviere(self, wunsch: int) -> int:
        with self._lock:
            menge = min(wunsch, self._frei)
            self._frei -= menge
            return menge

    def abrechnen(self, reserviert: int, verbraucht: int) -> None:
        with self._lock:
            verbraucht = max(0, min(verbraucht, reserviert))
            self._frei += reserviert - verbraucht
            self.verbraucht += verbraucht


def aktiv() -> tuple[bool, str | None]:
    """(runs, reason). The reason is set only when a real provider is configured but research cannot run."""
    if os.environ.get("DEEP_RESEARCH", "").strip().lower() in AUS:
        return False, None
    state = llm.status()
    if state["mock"]:
        return False, None
    if state["provider"] != "anthropic":
        return False, f"Deep research needs Claude (web search); provider {state['provider']} has none."
    return True, None


# ----------------------------------------------------------------------------------------------
# One research call: the shared web research helper of package A (llm.research)
# ----------------------------------------------------------------------------------------------
@dataclass
class Antwort:
    text: str
    quellen: dict[str, str] = field(default_factory=dict)  # url -> title, only URLs seen in this call
    suchen: int | None = None  # web searches used; None = not reported
    unvollstaendig: bool = False  # True when the model hit max_tokens; complete objects may still be usable


Aufruf = Callable[..., Antwort]  # (prompt, system=, max_uses=, max_tokens=, timeout=) -> Antwort


def _url(roh) -> str | None:
    if not isinstance(roh, str):
        return None
    url = roh.strip()
    return url.rstrip("/") if re.match(r"^https?://[^\s]+$", url) else None


def claude_recherche(prompt: str, system: str = "", *, max_uses: int,
                     max_tokens: int = MAX_TOKENS, timeout: float = 60.0) -> Antwort:
    """One research call through the shared helper ``llm.research`` (package A, #166): Claude with the
    server web_search tool, pause_turn handled there. Raises ``llm.LLMError`` (UI-safe). A call that
    hits max_tokens still returns the partial text (``unvollstaendig``) so complete result objects can
    be kept."""
    roh = llm.research(prompt, system, max_tokens, max_searches=max_uses, timeout=timeout)
    if not roh.web_search:
        raise llm.LLMError(f"{roh.provider} has no web search; deep research needs Claude.")
    quellen: dict[str, str] = {}
    for eintrag in [*roh.sources, *roh.citations]:  # only URLs this call actually saw or cited
        url = _url(eintrag.url)
        if url:
            quellen.setdefault(url, (eintrag.title or "")[:200])
    return Antwort(roh.text, quellen, roh.searches, unvollstaendig=bool(getattr(roh, "truncated", False)))


# ----------------------------------------------------------------------------------------------
# Selecting what is worth a search (grouped, capped)
# ----------------------------------------------------------------------------------------------
@dataclass
class Gruppe:
    schritt: str
    name: str
    eingabe: list[dict]
    rang: int  # lower = more important


_RANG = {"kritisch": 0, "hoch": 1, "mittel": 2, "niedrig": 3}


def _gewerk(position: Position | None) -> str:
    return (position.titel_pfad[0].strip() if position and position.titel_pfad else "") or OHNE_ABSCHNITT


def _kurz(text: str, laenge: int) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= laenge else text[:laenge - 1].rstrip() + "…"


def gruppen_positionen(bericht: Pruefbericht, max_items: int) -> list[Gruppe]:
    """Conspicuous findings (kritisch/hoch/mittel or risk/Nachtrag), grouped by trade; mock findings excluded."""
    positionen = {p.oz: p for p in bericht.lv.positionen}
    auffaellig = [f for f in bericht.findings if not f.regel_id.startswith("MOCK_")
                  and (f.schwere in ("kritisch", "hoch", "mittel") or f.kategorie in ("risiko", "nachtrag"))]
    auffaellig.sort(key=lambda f: _RANG[f.schwere])
    gruppen: OrderedDict[str, list[Finding]] = OrderedDict()
    for f in auffaellig:
        gruppen.setdefault(_gewerk(positionen.get(f.oz)), []).append(f)
    ergebnis = []
    for name, liste in gruppen.items():
        eingabe = []
        for f in liste[:max_items]:
            p = positionen.get(f.oz)
            eingabe.append({"finding_id": f.id, "oz": f.oz, "kurztext": p.kurztext if p else "",
                            "langtext": _kurz(p.langtext, MAX_LANGTEXT) if p else "",
                            "menge": p.menge if p else None, "einheit": p.einheit if p else None,
                            "befund": f.titel, "begruendung": _kurz(f.begruendung, MAX_BEFUNDTEXT)})
        ergebnis.append(Gruppe("positionen", name, eingabe, _RANG[liste[0].schwere]))
    return ergebnis


def gruppen_preise(bericht: Pruefbericht, max_items: int) -> list[Gruppe]:
    """Items whose own EP deviates ≥ PREIS_SCHWELLE from the price source, or has no price match."""
    if bericht.kalkulation is None:
        return []
    positionen = {p.oz: p for p in bericht.lv.positionen}
    kandidaten = []
    for k in bericht.kalkulation.positionen:
        if k.ep_lv is None or k.ep_lv <= 0:
            continue
        if k.ep is not None and k.ep > 0 and not k.geschaetzt:
            abweichung = abs(k.ep_lv - k.ep) / k.ep
            if abweichung < PREIS_SCHWELLE:
                continue
        elif k.treffer not in ("kein_treffer", "index", "recherche"):
            continue
        else:
            abweichung = 0.0
        kandidaten.append((abweichung, k))
    kandidaten.sort(key=lambda t: -t[0])
    gruppen: OrderedDict[str, list[dict]] = OrderedDict()
    for _, k in kandidaten:
        p = positionen.get(k.oz)
        liste = gruppen.setdefault(_gewerk(p), [])
        if len(liste) < max_items:
            liste.append({"oz": k.oz, "kurztext": k.kurztext or (p.kurztext if p else ""),
                          "langtext": _kurz(p.langtext, MAX_LANGTEXT) if p else "", "einheit": k.einheit,
                          "ep_lv": k.ep_lv, "ep_preisquelle": None if k.geschaetzt else k.ep})
    return [Gruppe("preise", name, eingabe, 1) for name, eingabe in gruppen.items()]


def gruppen_berichte(bericht: Pruefbericht, max_items: int) -> list[Gruppe]:
    """Problems of similar projects (Report 2) and what-if items (Report 3), high chance first."""
    eintraege = []
    for b in bericht.berichte or []:
        if b.id in ("vergleich", "was_wenn"):
            eintraege.extend((b.id, i, w) for i, w in enumerate(b.probleme))
    eintraege.sort(key=lambda t: t[2].chance != "hoch")
    positionen = {p.oz: p for p in bericht.lv.positionen}
    eingabe = []
    for index, (bericht_id, nummer, w) in enumerate(eintraege[:max_items]):
        p = positionen.get(w.oz or "")
        eingabe.append({"index": index, "bericht": bericht_id, "nummer": nummer, "oz": w.oz,
                        "kurztext": p.kurztext if p else "", "problem": w.problem, "chance": w.chance})
    return [Gruppe("berichte", "Reports 2/3", eingabe, 2)] if eingabe else []


def plane(gruppen: list[list[Gruppe]], max_calls: int) -> list[Gruppe]:
    """Fair share of the call budget across steps (findings, prices, reports).

    One group from each non-empty step is taken first, then the rest are filled round-robin by
    importance. That way a bill with many trade groups in one step cannot use up ``max_calls``
    before the other steps get a turn.
    """
    reihen = [sorted(g, key=lambda x: x.rang) for g in gruppen if g]
    plan = []
    for reihe in reihen:  # first pass: one group per step
        if reihe and len(plan) < max_calls:
            plan.append(reihe.pop(0))
    while len(plan) < max_calls and any(reihen):
        for reihe in reihen:
            if reihe and len(plan) < max_calls:
                plan.append(reihe.pop(0))
    return plan


# ----------------------------------------------------------------------------------------------
# Validating answers
# ----------------------------------------------------------------------------------------------
def _repariere_ergebnisse(text: str) -> dict | list | None:
    """Recover complete result objects from JSON cut off at max_tokens."""
    marker = text.find('"ergebnisse"')
    start = text.find("[", marker) if marker >= 0 else text.find("[")
    if start < 0:
        return None
    decoder = json.JSONDecoder()
    items, i, n = [], start + 1, len(text)
    while i < n:
        while i < n and text[i] in " \t\r\n,":
            i += 1
        if i >= n or text[i] == "]":
            break
        if text[i] != "{":
            break
        try:
            obj, ende = decoder.raw_decode(text, i)
        except ValueError:
            break  # the last object was truncated
        if isinstance(obj, dict):
            items.append(obj)
        i = ende
    return {"ergebnisse": items} if items else None


def _ergebnisliste(text: str) -> list:
    try:
        daten = llm.parse_json(text)
    except ValueError:
        # the JSON usually comes last, after the research prose; it may also be cut off at max_tokens
        start = text.rfind('{"ergebnisse"')
        try:
            daten = llm.parse_json(text[start:]) if start >= 0 else None
        except ValueError:
            daten = _repariere_ergebnisse(text[start:] if start >= 0 else text)
    if isinstance(daten, dict) and isinstance(daten.get("ergebnisse"), list):
        return daten["ergebnisse"]
    if isinstance(daten, list):
        return daten
    repariert = _repariere_ergebnisse(text)
    if isinstance(repariert, dict) and isinstance(repariert.get("ergebnisse"), list):
        return repariert["ergebnisse"]
    return []


def _preis(roh) -> float | None:
    return float(roh) if isinstance(roh, (int, float)) and not isinstance(roh, bool) and roh > 0 else None


def validiere(gruppe: Gruppe, antwort: Antwort) -> list[tuple[dict, RechercheErgebnis]]:
    """(input item, result) pairs; results without a source seen in this call are dropped."""
    schluessel = {"positionen": "finding_id", "preise": "oz", "berichte": "index"}[gruppe.schritt]
    eingaben = {e[schluessel]: e for e in gruppe.eingabe}
    erlaubt = EINSCHAETZUNGEN[gruppe.schritt]
    paare, gesehen = [], set()
    for roh in _ergebnisliste(antwort.text):
        if not isinstance(roh, dict):
            continue
        eingabe = eingaben.get(roh.get(schluessel))
        einschaetzung = str(roh.get("einschaetzung", "")).strip().lower()
        text = _kurz(str(roh.get("text") or ""), MAX_TEXT)
        if eingabe is None or einschaetzung not in erlaubt or not text or roh.get(schluessel) in gesehen:
            continue
        quellen = []
        for url in roh.get("quellen") or []:
            url = _url(url)
            if url and url in antwort.quellen and all(q.url != url for q in quellen):
                quellen.append(RechercheQuelle(url=url, titel=antwort.quellen[url]))
        if not quellen:
            continue
        gesehen.add(roh.get(schluessel))
        ergebnis = RechercheErgebnis(
            schritt=gruppe.schritt, gruppe=gruppe.name, oz=eingabe.get("oz"),
            finding_id=eingabe.get("finding_id"), einschaetzung=einschaetzung, text=text,
            quellen=quellen[:MAX_QUELLEN],
            marktpreis_von=_preis(roh.get("marktpreis_von")) if gruppe.schritt == "preise" else None,
            marktpreis_bis=_preis(roh.get("marktpreis_bis")) if gruppe.schritt == "preise" else None)
        paare.append((eingabe, ergebnis))
    return paare


# ----------------------------------------------------------------------------------------------
# Applying results to the report
# ----------------------------------------------------------------------------------------------
def quellen_text(ergebnis: RechercheErgebnis) -> str:
    return "; ".join(f"{q.titel} <{q.url}>" if q.titel else q.url for q in ergebnis.quellen)


def _anhang(ergebnis: RechercheErgebnis) -> str:
    return (f" Web research ({EINSCHAETZUNG_TEXT[ergebnis.einschaetzung]}): {ergebnis.text.rstrip('.')}."
            f" Sources: {quellen_text(ergebnis)}.")


def _preis_finding(eingabe: dict, ergebnis: RechercheErgebnis) -> Finding:
    spanne = ""
    if ergebnis.marktpreis_von is not None or ergebnis.marktpreis_bis is not None:
        von = f"{ergebnis.marktpreis_von:g}" if ergebnis.marktpreis_von is not None else "?"
        bis = f"{ergebnis.marktpreis_bis:g}" if ergebnis.marktpreis_bis is not None else "?"
        spanne = f" Researched market range: {von}–{bis} EUR per {eingabe.get('einheit') or 'unit'} (net)."
    richtung = "above" if ergebnis.einschaetzung == "zu_hoch" else "below"
    return Finding(
        id=f"recherche-preis-{re.sub(r'[^A-Za-z0-9]+', '-', ergebnis.oz or 'x').strip('-').lower()}",
        oz=ergebnis.oz or "?", kategorie="risiko", schwere="mittel",
        titel=f"Unit price {richtung} researched market prices",
        begruendung=(f"The bill's EP is {eingabe['ep_lv']:g} EUR"
                     + (f" (price source: {eingabe['ep_preisquelle']:g} EUR)" if eingabe.get("ep_preisquelle") else "")
                     + f".{spanne}" + _anhang(ergebnis)),
        vorschlag="Check the unit price against current supplier quotes before pricing the bid.",
        quelle="modell", regel_id=REGEL_PREIS, euro_wirkung=None)


def _neu_zusammensetzen(bericht: Pruefbericht, findings: list[Finding]) -> Pruefbericht:
    """New price findings: recount figures, Report 1, the final report and the summary."""
    from . import berichte as b  # local import: berichte imports the step API
    update: dict = {"findings": findings, "kennzahlen": bericht.kennzahlen.model_copy(update={
        "findings": len(findings), "kritisch": sum(f.schwere == "kritisch" for f in findings)})}
    if bericht.berichte and len(bericht.berichte) == 3:
        try:
            berichte = [b.bericht_regelwerk(findings), *bericht.berichte[1:]]
            update["berichte"] = berichte
            if bericht.schlussbericht is not None:
                update["schlussbericht"] = b.schlussbericht(bericht.lv, findings, berichte)
            if bericht.zusammenfassung is not None:
                update["zusammenfassung"] = b.zusammenfassung_mit_berichten(findings, berichte)
        except Exception:
            log.exception("Deep research: recounting the reports failed; previous reports kept")
    return bericht.model_copy(update=update)


def anwenden(bericht: Pruefbericht, paare: list[tuple[str, dict, RechercheErgebnis]]) -> Pruefbericht:
    findings = list(bericht.findings)
    index = {f.id: i for i, f in enumerate(findings)}
    berichte = [b.model_copy(deep=True) for b in bericht.berichte] if bericht.berichte else None
    neu = False
    for schritt, eingabe, ergebnis in paare:
        if schritt == "positionen" and ergebnis.finding_id in index:
            i = index[ergebnis.finding_id]
            findings[i] = findings[i].model_copy(update={"begruendung": findings[i].begruendung + _anhang(ergebnis)})
        elif schritt == "preise" and ergebnis.einschaetzung in ("zu_hoch", "zu_niedrig"):
            finding = _preis_finding(eingabe, ergebnis)
            if finding.id not in index:
                index[finding.id] = len(findings)
                findings.append(finding)
                ergebnis.finding_id = finding.id
                neu = True
        elif schritt == "berichte" and berichte:
            ziel = next((b for b in berichte if b.id == eingabe["bericht"]), None)
            if ziel is not None and eingabe["nummer"] < len(ziel.probleme):
                w = ziel.probleme[eingabe["nummer"]]
                w.begruendung = (w.begruendung + _anhang(ergebnis)).strip()
    update: dict = {"findings": findings}
    if berichte is not None:
        update["berichte"] = berichte
        was_wenn = next((b for b in berichte if b.id == "was_wenn"), None)
        if was_wenn is not None and bericht.was_wenn is not None:
            update["was_wenn"] = was_wenn.probleme
    ergebnis_bericht = bericht.model_copy(update=update)
    return _neu_zusammensetzen(ergebnis_bericht, findings) if neu else ergebnis_bericht


# ----------------------------------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------------------------------
SCHRITT_ID = "recherche"
SCHRITT_TITEL = "AI deep research (web)"
SCHRITT_STATUS = {"ok": "ok", "teilweise": "fehler", "fehler": "fehler", "aus": "aus"}


def _mit_recherche(bericht: Pruefbericht, recherche: Recherche) -> Pruefbericht:
    """Set ``recherche`` and report the step in ``ki_schritte`` (D #168) so the UI's AI status shows it too."""
    modell = f"anthropic/{llm.model('anthropic')}" if recherche.aufrufe else None
    schritt = KiSchritt(schritt=SCHRITT_ID, titel=SCHRITT_TITEL, status=SCHRITT_STATUS[recherche.status],
                        grund=_kurz(recherche.meldung, 300) or None, modell=modell)
    schritte = [s for s in bericht.ki_schritte or [] if s.schritt != SCHRITT_ID] + [schritt]
    return bericht.model_copy(update={"recherche": recherche, "ki_schritte": schritte})


def _prompt(gruppe: Gruppe) -> str:
    return (f"{AUFGABEN[gruppe.schritt]}\nTrade/group: {gruppe.name}\n"
            f"Input:\n{json.dumps(gruppe.eingabe, ensure_ascii=False)}")


def vertiefe_recherche(bericht: Pruefbericht, *, aufruf: Aufruf | None = None,
                       einstellungen: Einstellungen | None = None, fortschritt: Fortschritt | None = None,
                       schritt: int = 1, gesamt: int = 1) -> Pruefbericht:
    """Deep research over the conspicuous parts of a report; never raises (except the job's own
    ``AnalyseAbgebrochen`` from a progress call).

    ``aufruf`` replaces the Claude call (tests); then the provider check is skipped. ``fortschritt``
    (#165) is the background job's progress; research reports as step ``schritt`` of ``gesamt``. Progress
    is only reported when research actually runs, so the caller counts the step only then (``aktiv()``)."""
    if aufruf is None:
        laeuft, grund = aktiv()
        if not laeuft:
            if grund is None:
                return bericht
            return _mit_recherche(bericht, Recherche(status="aus", meldung=grund))
    cfg = einstellungen or Einstellungen.aus_env()
    try:
        plan = plane([gruppen_positionen(bericht, cfg.max_items), gruppen_preise(bericht, cfg.max_items),
                      gruppen_berichte(bericht, cfg.max_items)], cfg.max_calls)
    except Exception:
        log.exception("Deep research: selecting groups failed")
        return _mit_recherche(bericht, Recherche(
            status="fehler", meldung="Deep research could not select items; report shown without it."))
    if not plan:
        return _mit_recherche(bericht, Recherche(
            status="ok", meldung="Nothing conspicuous to research (no medium-or-higher, risk, Nachtrag, price or "
                                 "report items)."))
    aufruf = aufruf or claude_recherche
    melde = teilschritt(fortschritt, schritt, gesamt)
    melde(f"Web research: {len(plan)} group(s) (findings, prices, reports) …", 0.0)
    budget = Budget(cfg.budget)
    frist = time.monotonic() + cfg.timeout
    fehler: list[str] = []
    ausgelassen = 0

    def eine(gruppe: Gruppe):
        reserviert = budget.reserviere(cfg.max_uses)
        if reserviert == 0:
            return gruppe, None, "budget"
        rest = frist - time.monotonic()
        if rest <= 1:
            budget.abrechnen(reserviert, 0)
            return gruppe, None, "time"
        try:
            antwort = aufruf(_prompt(gruppe), system=SYSTEM, max_uses=reserviert,
                             max_tokens=MAX_TOKENS, timeout=rest)
        except Exception:
            budget.abrechnen(reserviert, reserviert)
            raise
        budget.abrechnen(reserviert, reserviert if antwort.suchen is None else antwort.suchen)
        return gruppe, antwort, None

    pool = ThreadPoolExecutor(max_workers=min(cfg.parallel, len(plan)), thread_name_prefix="deep-research")
    paare, aufrufe = [], 0
    try:
        futures = [pool.submit(contextvars.copy_context().run, eine, g) for g in plan]  # #196: keep answer language
        fertig = set()
        try:
            for future in as_completed(futures, timeout=cfg.timeout + 1):
                fertig.add(future)
                gruppe = plan[futures.index(future)]
                melde(f"Web research: {gruppe.schritt} · {gruppe.name} done ({len(fertig)}/{len(plan)}).",
                      len(fertig) / len(plan))
        except FutureTimeout:
            fehler.append(f"{len(plan) - len(fertig)} research call(s) did not finish within {cfg.timeout:g} s.")
        for future in futures:
            if future not in fertig:
                continue
            exc = future.exception()
            if exc is not None:
                text = str(exc) if isinstance(exc, llm.LLMError) else f"research call failed ({type(exc).__name__})."
                aufrufe += 1
                if text not in fehler:
                    fehler.append(text)
                continue
            gruppe, antwort, grund = future.result()
            if antwort is None:
                ausgelassen += 1
                continue
            aufrufe += 1
            paare.extend((gruppe.schritt, e, r) for e, r in validiere(gruppe, antwort))
            if getattr(antwort, "unvollstaendig", False):
                hinweis = (f"anthropic stopped at max_tokens ({MAX_TOKENS}) for {gruppe.schritt} · "
                           f"{gruppe.name}; complete results from the cut-off answer were kept.")
                if hinweis not in fehler:
                    fehler.append(hinweis)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    ergebnisse = [r for _, _, r in paare]
    try:
        neuer = anwenden(bericht, paare)
    except Exception:
        log.exception("Deep research: applying results failed")
        neuer, ergebnisse = bericht, []
        fehler.append("Results could not be applied to the report.")
    teile = [f"{aufrufe} research call(s), {budget.verbraucht} web search(es), {len(ergebnisse)} sourced "
             f"result(s) for {len(plan)} group(s)."]
    if ausgelassen:
        teile.append(f"{ausgelassen} group(s) skipped (search budget or time limit).")
    teile.extend(fehler)
    status = "ok" if not fehler else "teilweise" if ergebnisse else "fehler"
    for text in fehler:
        if fortschritt is not None:
            fortschritt.fehler(f"Web research: {text}")
    melde(f"Web research: {teile[0]}", 1.0)
    return _mit_recherche(neuer, Recherche(
        status=status, meldung=" ".join(teile), aufrufe=aufrufe, suchen=budget.verbraucht,
        ergebnisse=sorted(ergebnisse, key=lambda r: ("positionen", "preise", "berichte").index(r.schritt))))


# ----------------------------------------------------------------------------------------------
# Price fallback (t237): research market prices for items that have no price at all
# ----------------------------------------------------------------------------------------------
FEHLENDE_PREISE_HINWEIS = (
    "These items have no unit price in the price list or price database. For every item give the current "
    "German market range marktpreis_von/marktpreis_bis (EUR net per the given unit, supply and installation) "
    "as stated in the sources; einschaetzung is 'unklar' when ep_lv is null.")
STANDARD_PREIS_TIMEOUT = 180.0
MAX_PREIS_GRUPPEN = 6


def gruppen_fehlende_preise(lv: LV, kalkulation: Kalkulation, max_items: int) -> list[Gruppe]:
    """Items still ``kein_treffer`` (with a unit), grouped by trade, at most ``max_items`` per group."""
    positionen = {p.oz: p for p in lv.positionen}
    gruppen: OrderedDict[str, list[dict]] = OrderedDict()
    for k in kalkulation.positionen:
        if k.treffer != "kein_treffer" or not k.einheit:
            continue
        p = positionen.get(k.oz)
        liste = gruppen.setdefault(_gewerk(p), [])
        if len(liste) < max_items and all(e["oz"] != k.oz for e in liste):
            liste.append({"oz": k.oz, "kurztext": k.kurztext or (p.kurztext if p else ""),
                          "langtext": _kurz(p.langtext, MAX_LANGTEXT) if p else "", "einheit": k.einheit,
                          "ep_lv": k.ep_lv, "ep_preisquelle": None})
    return [Gruppe("preise", name, eingabe, 1) for name, eingabe in gruppen.items()][:MAX_PREIS_GRUPPEN]


def recherchiere_fehlende_preise(lv: LV, kalkulation: Kalkulation, *, aufruf: Aufruf | None = None,
                                 einstellungen: Einstellungen | None = None,
                                 fortschritt: Fortschritt | None = None
                                 ) -> tuple[dict[str, RechercheErgebnis], list[str]]:
    """({oz: sourced result with marktpreis_von/bis}, warnings) for items without any price.

    Same helper, prompt shape and source validation as the ``preise`` step of the deep research
    (``validiere``: only URLs seen in this call count). Off (no warning) when deep research is off or the
    mock runs; ``aufruf`` replaces the Claude call in tests. Never raises."""
    if aufruf is None:
        laeuft, grund = aktiv()
        if not laeuft:
            return {}, ([f"Web price research skipped: {grund}"] if grund else [])
    cfg = einstellungen or Einstellungen.aus_env()
    gruppen = gruppen_fehlende_preise(lv, kalkulation, cfg.max_items)
    if not gruppen:
        return {}, []
    aufruf = aufruf or claude_recherche
    timeout = llm.seconds("PREIS_RECHERCHE_TIMEOUT", STANDARD_PREIS_TIMEOUT)
    frist = time.monotonic() + timeout

    def eine(gruppe: Gruppe):
        rest = max(1.0, frist - time.monotonic())
        return gruppe, aufruf(f"{FEHLENDE_PREISE_HINWEIS}\n{_prompt(gruppe)}", system=SYSTEM,
                              max_uses=cfg.max_uses, max_tokens=MAX_TOKENS, timeout=rest)

    ergebnisse: dict[str, RechercheErgebnis] = {}
    fehler: list[str] = []
    pool = ThreadPoolExecutor(max_workers=min(cfg.parallel, len(gruppen)), thread_name_prefix="preis-recherche")
    try:
        futures = [pool.submit(contextvars.copy_context().run, eine, g) for g in gruppen]
        try:
            for future in as_completed(futures, timeout=timeout + 1):
                try:
                    gruppe, antwort = future.result()
                except Exception as exc:  # noqa: BLE001
                    text = str(exc) if isinstance(exc, llm.LLMError) else f"call failed ({type(exc).__name__})"
                    fehler.append(f"Web price research: {text}")
                    continue
                for _, ergebnis in validiere(gruppe, antwort):
                    if ergebnis.oz and (ergebnis.marktpreis_von or ergebnis.marktpreis_bis):
                        ergebnisse.setdefault(ergebnis.oz, ergebnis)
        except FutureTimeout:
            fehler.append(f"Web price research did not finish within {timeout:g} s.")
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    return ergebnisse, list(dict.fromkeys(fehler))

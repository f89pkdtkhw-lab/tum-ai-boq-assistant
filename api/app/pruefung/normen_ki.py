"""Norm check, part 5 (N5): AI research for standards the rule-based pass may have missed.

Bonus feature "norm check" (Normpruefung), purely additive. After N1 (extraction) and N2/N3
(register findings), the configured model reads the LV positions together with the standards N1
already found and proposes **additional** German standards (implicit by trade, behind blanket
"nach DIN" references, or families the extractor skips such as DGUV or guidelines).

Anti-hallucination rules:
- Every suggestion is looked up in the curated register `data/normen/register.json`. A register
  hit is labelled `im Register bestätigt`; anything else stays `KI-Hinweis, unbestätigt – bitte
  prüfen` and is never treated as a register fact.
- Suggestions already found by N1 (same designation or family), unknown OZ and invalid or
  partial JSON are dropped silently, never raised.
- No standard text is quoted or invented; model text is shortened and dropped when it claims a
  breach. Every finding carries the "kein Normgutachten" note and names its source.

Real research (#166, package A): with Claude the pass runs `llm.research()`, i.e. the server tool
`web_search`, in several rounds (one per trade = top-level LV title, at most `NORM_KI_RUNDEN`, default
10, up to 6 in parallel; `NORM_KI_MAX_SEARCHES` searches per round, default 8). Every hint names its web
sources (URL, title and the passage Claude quoted). A web source is only shown when the search really
returned it: URLs the model names but never retrieved are dropped. Other providers answer without web
search and therefore without web sources.

Switch `NORM_KI_RECHERCHE` (`0`/`off`/`false`/`no` = off). Otherwise the pass runs only when the
existing client in `app.ai.llm` is a real provider with a key; in mock/offline mode it returns no
findings and makes no call, so the report stays identical. The whole research is bounded by
`NORM_KI_TIMEOUT` (seconds, default 360); rounds that fail or time out are logged and skipped, the
others still count. It runs in a background thread pool: `starte_recherche(lv)` starts it early
(the review calls it before the item review, so both run at the same time) and the result is cached
per LV hash, so a second review of the same LV makes no new call.
"""
import hashlib
import json
import logging
import os
import re
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
import contextvars
from concurrent.futures import Future, ThreadPoolExecutor, wait
from concurrent.futures import TimeoutError as FutureTimeout

from ..ai import ki_status, llm  # ki_status: D #168
from ..ai import sprache  # #196
from ..modelle import LV, Finding
from .normen import (
    AUS_WERTE, KEIN_NORMGUTACHTEN, NORM_MUSTER, Register, RegisterEintrag, _Ids, _normalisiere, _quelle,
    extrahiere_normverweise, lade_register, normpruefung_aktiv,
)

logger = logging.getLogger(__name__)

NORM_KI_HINWEIS = "NORM_KI_HINWEIS"
BESTAETIGT = "im Register bestätigt"
UNBESTAETIGT = "KI-Hinweis, unbestätigt – bitte prüfen"
STANDARD_TIMEOUT = 360.0  # whole research, all rounds (NORM_KI_TIMEOUT)
STANDARD_SUCHEN = 8  # web searches per round (NORM_KI_MAX_SEARCHES)
STANDARD_RUNDEN = 10  # research rounds, one per trade, small trades merged (NORM_KI_RUNDEN)
PARALLEL = 6  # rounds running at the same time
MAX_TOKENS = 16000
MAX_VORSCHLAEGE = 15  # per round
MAX_HINWEISE = 40  # per LV, all rounds
MAX_QUELLEN = 3  # web sources shown per hint
MAX_ZITAT = 240
CACHE_GROESSE = 32
MAX_LANGTEXT = 600
MAX_EINGABE = 60_000  # characters of position data sent to the model
MAX_MODELLTEXT = 300
STATUS_TEXT = {"gueltig": "valid", "zurueckgezogen": "withdrawn", "teilweise_ersetzt": "partly replaced",
               "unklar": "unclear"}
# Model text that claims a breach is never shown (wording rule of the norm check).
ANSPRUCH_WORTE = re.compile(r"violat|breach|verstoß|verstoss|verstöß|non-?complian|infring|unzulässig|rechtswidrig",
                            re.IGNORECASE)
_SONSTIGE_ID = re.compile(r"[A-Za-zÄÖÜ][A-Za-z0-9ÄÖÜäöüß .,:/()\-–]{2,79}")
_KONFIDENZ_TEXT = {"hoch": "high", "high": "high", "mittel": "medium", "medium": "medium", "niedrig": "low",
                   "low": "low", "gering": "low"}

Client = Callable[..., object]  # (prompt, system=..., max_tokens=...) -> llm.Answer or str

SYSTEM = (
    "You support a construction cost estimator reviewing a German bill of quantities (LV). The rule-based "
    "pass already found the standards listed under 'bereits_gefunden'. Propose only ADDITIONAL German "
    "standards or technical rules (DIN, DIN EN, DIN EN ISO, DIN VDE, VOB/C ATV, DGUV, VDI or similar "
    "guidelines) that typically apply to the described work but are not referenced. If you can search the "
    "web, research the current edition and status of each candidate first (for example on din.de, "
    "dinmedia.de, dguv.de, vdi.de or official building authority pages) and name the pages you used. Use "
    "only designations you are certain exist; never quote or paraphrase standard text; never call anything "
    "a violation. Only use OZ values from the input. End your answer with JSON only, no prose after it: "
    '{"vorschlaege": [{"norm_id": "DIN 4109", "titel": "short title", "oz": ["01.02"], '
    '"begruendung": "one short sentence why it may apply", "konfidenz": 0.0, '
    '"quellen": [{"url": "https://…", "titel": "page title"}]}]}. '
    "List under 'quellen' only URLs that your web search actually returned; leave it empty without search. "
    f"At most {MAX_VORSCHLAEGE} suggestions; an empty list is a valid answer."
)


def norm_ki_aktiv() -> bool:
    """Switch NORM_KI_RECHERCHE: 0/off/false/no switch the AI research off."""
    return os.environ.get("NORM_KI_RECHERCHE", "").strip().lower() not in AUS_WERTE


def _client_verfuegbar() -> bool:
    """True only for a real provider with its key; mock or misconfiguration means no call."""
    try:
        konfiguration = llm.config()
    except llm.LLMError:
        return False
    return not konfiguration["mock"] and bool(konfiguration["keys"].get(konfiguration["provider"]))


def _zahl(name: str, standard: float, art=float):
    """Positive number from an environment variable; invalid or non-positive values use the default."""
    try:
        wert = art(os.environ.get(name, "") or standard)
    except ValueError:
        return standard
    return wert if wert > 0 else standard


def _timeout() -> float:
    return _zahl("NORM_KI_TIMEOUT", STANDARD_TIMEOUT)


def _max_suchen() -> int:
    return _zahl("NORM_KI_MAX_SEARCHES", STANDARD_SUCHEN, int)


def _max_runden() -> int:
    return _zahl("NORM_KI_RUNDEN", STANDARD_RUNDEN, int)


def _runden(lv: LV, anzahl: int) -> list[list]:
    """Positions grouped by trade (top-level title), in LV order; neighbouring trades are merged so
    there are at most `anzahl` rounds of roughly equal size."""
    gruppen: dict[str, list] = {}
    for position in lv.positionen:
        gruppen.setdefault(position.titel_pfad[0] if position.titel_pfad else "", []).append(position)
    gruppen_liste = list(gruppen.values())
    if len(gruppen_liste) <= anzahl:
        return gruppen_liste
    ziel = -(-len(lv.positionen) // anzahl)  # ceiling: positions per round
    runden: list[list] = []
    for gruppe in gruppen_liste:
        if runden and (len(runden) >= anzahl or len(runden[-1]) + len(gruppe) <= ziel):
            runden[-1].extend(gruppe)
        else:
            runden.append(list(gruppe))
    return runden


def _eingabe(positionen_lv, gefunden: list[str]) -> str:
    positionen, laenge = [], 0
    for position in positionen_lv:
        eintrag = {"oz": position.oz, "abschnitt": " / ".join(position.titel_pfad),
                   "kurztext": position.kurztext, "langtext": position.langtext[:MAX_LANGTEXT]}
        laenge += len(json.dumps(eintrag, ensure_ascii=False))
        if laenge > MAX_EINGABE:
            break
        positionen.append(eintrag)
    return json.dumps({"bereits_gefunden": gefunden, "positionen": positionen}, ensure_ascii=False)


def _antwort_objekt(text: str):
    """The JSON object or list in the answer, also inside ``` fences; None when there is none."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[A-Za-z]*\s*|\s*```$", "", text)
    for anfang, ende in (("{", "}"), ("[", "]")):
        start, stop = text.find(anfang), text.rfind(ende)
        if start != -1 and stop > start:
            try:
                return json.loads(text[start:stop + 1])
            except ValueError:
                continue
    return None


def _vorschlagsliste(daten) -> list:
    if isinstance(daten, list):
        return daten
    if isinstance(daten, dict):
        for schluessel in ("vorschlaege", "suggestions"):
            if isinstance(daten.get(schluessel), list):
                return daten[schluessel]
    return []


def _norm_bezeichnung(roh) -> tuple[str, str] | None:
    """(norm_id, familie) in the N1 spelling; other rule sets (DGUV, VDI, …) are kept as written."""
    if not isinstance(roh, str):
        return None
    text = re.sub(r"\s+", " ", roh).strip()
    treffer = NORM_MUSTER.match(text)
    if treffer and treffer.group(0).strip() == text:
        norm_id, familie, _, _ = _normalisiere(treffer)
        return norm_id, familie
    if _SONSTIGE_ID.fullmatch(text) and re.search(r"\d", text):
        return text, text
    return None


def _modelltext(roh, laenge: int = MAX_MODELLTEXT) -> str | None:
    if not isinstance(roh, str):
        return None
    text = re.sub(r"\s+", " ", roh).strip()
    if not text or ANSPRUCH_WORTE.search(text):
        return None
    return text if len(text) <= laenge else text[:laenge - 1].rstrip() + "…"


def _konfidenz(roh) -> str:
    if isinstance(roh, (int, float)) and not isinstance(roh, bool) and 0 <= roh <= 1:
        stufe = "high" if roh >= 0.75 else "medium" if roh >= 0.4 else "low"
        return f"{stufe} ({roh:.2f})"
    if isinstance(roh, str) and roh.strip().lower() in _KONFIDENZ_TEXT:
        return _KONFIDENZ_TEXT[roh.strip().lower()]
    return "not stated"


def _vergleichstext(text: str) -> str:
    return re.sub(r"[\s\-–]+", "", text).lower()


def _quellen(roh, norm_id: str, belege: dict) -> list:
    """Web sources of one suggestion, only from what the search really returned (`belege`: url ->
    llm.Citation list, quoted passages first). The model's URLs count only when retrieved; passages
    that name the designation are added. Without web evidence (other providers, plain fakes): []."""
    if not belege:
        return []
    urls = []
    for eintrag in roh if isinstance(roh, list) else []:
        url = eintrag.get("url") if isinstance(eintrag, dict) else eintrag if isinstance(eintrag, str) else None
        if isinstance(url, str) and url.strip() in belege:
            urls.append(url.strip())
    gesucht = _vergleichstext(norm_id)
    for url, zitate in belege.items():
        if any(gesucht in _vergleichstext(f"{z.title} {z.cited_text}") for z in zitate):
            urls.append(url)
    return [belege[url][0] for url in dict.fromkeys(urls)][:MAX_QUELLEN]


def vorschlaege_aus_antwort(text: str, lv: LV, bekannt: set[str], belege: dict | None = None) -> list[dict]:
    """Validated, deduplicated suggestions; invalid entries are dropped, never raised.

    `bekannt` holds the designations and families N1 already found. A suggestion is dropped when its
    designation or family is among them, when it names no OZ of this LV, or when it is malformed.
    `belege` (url -> llm.Citation list) is the web evidence of the answer; see `_quellen`.
    """
    reihenfolge = {p.oz: i for i, p in enumerate(lv.positionen)}
    vorschlaege: dict[str, dict] = {}
    for roh in _vorschlagsliste(_antwort_objekt(text) if isinstance(text, str) else None):
        if not isinstance(roh, dict):
            continue
        bezeichnung = _norm_bezeichnung(roh.get("norm_id"))
        oz_roh = roh.get("oz")
        oz_liste = [oz_roh] if isinstance(oz_roh, str) else oz_roh if isinstance(oz_roh, list) else []
        oz_liste = [oz for oz in oz_liste if isinstance(oz, str) and oz in reihenfolge]
        if bezeichnung is None or not oz_liste:
            continue
        norm_id, familie = bezeichnung
        if norm_id in bekannt or familie in bekannt:
            continue
        vorschlag = vorschlaege.setdefault(norm_id, {
            "norm_id": norm_id, "familie": familie, "oz": [], "titel": _modelltext(roh.get("titel"), 120),
            "begruendung": _modelltext(roh.get("begruendung")), "konfidenz": _konfidenz(roh.get("konfidenz")),
            "quellen": [],
        })
        vorschlag["oz"] = sorted(set(vorschlag["oz"]) | set(oz_liste), key=reihenfolge.__getitem__)
        vorschlag["quellen"] = _quellen_vereinen(vorschlag["quellen"], _quellen(roh.get("quellen"), norm_id, belege))
    ergebnis = sorted(vorschlaege.values(), key=lambda v: reihenfolge[v["oz"][0]])
    return ergebnis[:MAX_VORSCHLAEGE]


def _quellen_vereinen(alt: list, neu: list) -> list:
    bekannt = {q.url for q in alt}
    return (alt + [q for q in neu if q.url not in bekannt])[:MAX_QUELLEN]


def _quellentext(quellen: list) -> str | None:
    if not quellen:
        return None
    teile = []
    for nummer, q in enumerate(quellen, 1):
        titel = _modelltext(q.title, 120) if q.title else None
        zitat = re.sub(r"\s+", " ", q.cited_text).strip()
        zitat = zitat if len(zitat) <= MAX_ZITAT else zitat[:MAX_ZITAT - 1].rstrip() + "…"
        teile.append(f"[{nummer}] {titel + ', ' if titel else ''}{q.url}" + (f", quoted: “{zitat}”" if zitat else ""))
    text = "Web sources (found by the web search, please verify): " + "; ".join(teile)
    return text if text.endswith("”") else text + "."


def _finding(vorschlag: dict, eintrag: RegisterEintrag | None, register: Register, quelle: str,
             ids: _Ids) -> Finding:
    norm_id, oz_text = vorschlag["norm_id"], ", ".join(vorschlag["oz"])
    label = BESTAETIGT if eintrag else UNBESTAETIGT
    teile = [f"{label}."]
    if eintrag:
        teile.append(f"The AI research suggests {norm_id} ({eintrag.titel}) for OZ {oz_text}; the LV does not "
                     f"reference it. The norm register lists {eintrag.norm_id} with status "
                     f"{STATUS_TEXT.get(eintrag.status, eintrag.status)}.")
    else:
        titel = f" (title as named by the model: {vorschlag['titel']})" if vorschlag["titel"] else ""
        teile.append(f"The AI research suggests {norm_id}{titel} for OZ {oz_text}; the LV does not reference "
                     f"it. The norm register (as of {register.stand}) has no entry for it, so neither the "
                     f"designation nor its status is confirmed.")
    if vorschlag["begruendung"]:
        teile.append(f"Model reasoning: {vorschlag['begruendung'].rstrip('.')}.")
    teile.append(f"Model confidence: {vorschlag['konfidenz']}.")
    teile.append(f"Source: model ({quelle}), second pass after the rule-based norm check.")
    web = _quellentext(vorschlag.get("quellen") or [])
    if web:
        teile.append(web)
    if eintrag:
        teile.append(_quelle(eintrag))
    teile.append(KEIN_NORMGUTACHTEN)
    return Finding(
        id=ids(NORM_KI_HINWEIS, vorschlag["oz"][0]), oz=vorschlag["oz"][0], kategorie="risiko", schwere="niedrig",
        titel=f"Standard possibly relevant but not referenced: {norm_id} ({label})",
        begruendung=" ".join(teile),
        vorschlag=f"OZ {oz_text}: Does {norm_id} apply to these items? Please confirm, or name the applicable "
                  f"standards and editions.",
        quelle="modell", regel_id=NORM_KI_HINWEIS, euro_wirkung=None,
    )


def _antworttext(antwort) -> tuple[str, str, dict]:
    """(text, source label, web evidence url -> Citation list with quoted passages first)."""
    if isinstance(antwort, llm.ResearchAnswer):
        belege: dict[str, list] = {}
        for zitat in antwort.citations + antwort.sources:
            belege.setdefault(zitat.url, []).append(zitat)
        art = f", web search: {antwort.searches} searches" if antwort.web_search else ""
        return antwort.text, f"{antwort.provider}/{antwort.model}{art}", belege
    if isinstance(antwort, llm.Answer):
        return antwort.text, f"{antwort.provider}/{antwort.model}", {}
    return (antwort if isinstance(antwort, str) else ""), "AI research", {}


def _standard_client(frist: float) -> Client:
    """`llm.research` with the remaining time of the whole research as its timeout."""
    def client(prompt, system="", max_tokens=MAX_TOKENS):
        rest = frist - time.monotonic()
        if rest <= 0:
            raise FutureTimeout()
        return llm.research(prompt, system, max_tokens, max_searches=_max_suchen(), timeout=rest)
    return client


def recherchiere_normen(lv: LV, register: Register | None = None, client: Client | None = None,
                        timeout: float | None = None, melde=None) -> list[Finding]:
    """N5 findings for one LV, one research round per trade. Rounds that fail or time out are logged and
    skipped; when no round succeeds, the first error (or the timeout) is raised, and callers use the
    guarded variant. `melde(meldung, anteil)`: optional progress per round (#165 job progress)."""
    hinweise, _ = _recherche(lv, register, client, timeout, melde)
    return hinweise


def _melden(melde, meldung: str, anteil: float | None = None) -> None:
    """Progress never stops the research: a failing or aborting callback is ignored here."""
    if melde is not None:
        try:
            melde(meldung, anteil)
        except Exception:  # e.g. AnalyseAbgebrochen of one job; the shared research goes on
            pass


def _rundentitel(runde: list) -> str:
    titel = ", ".join(dict.fromkeys(p.titel_pfad[0] for p in runde if p.titel_pfad)) or "items without a title"
    return titel if len(titel) <= 80 else titel[:79].rstrip() + "…"


def _recherche(lv: LV, register: Register | None, client: Client | None,
               timeout: float | None, melde=None) -> tuple[list[Finding], bool]:
    """(findings, complete): `complete` is False when a round failed or timed out (not cached)."""
    register = register or lade_register()
    verweise = [v for v in extrahiere_normverweise(lv) if not v.pauschal]
    gefunden = list(dict.fromkeys(v.norm_id for v in verweise))
    bekannt = set(gefunden) | {v.familie for v in verweise}
    limit = timeout or _timeout()
    frist = time.monotonic() + limit
    aufruf = client or _standard_client(frist)
    runden = _runden(lv, _max_runden())
    fertig, zaehler = [0], threading.Lock()

    def runde_ausfuehren(nummer: int, runde: list):
        _melden(melde, f"Researching standards for {_rundentitel(runde)} … (round {nummer} of {len(runden)})",
                fertig[0] / len(runden))
        try:
            return aufruf(_eingabe(runde, gefunden), system=SYSTEM, max_tokens=MAX_TOKENS)
        finally:
            with zaehler:
                fertig[0] += 1
                stand = fertig[0]
            _melden(melde, f"Standards research: {stand} of {len(runden)} rounds done.", stand / len(runden))

    ausfuehrer = ThreadPoolExecutor(max_workers=PARALLEL, thread_name_prefix="norm-ki")
    try:
        auftraege = [ausfuehrer.submit(contextvars.copy_context().run, runde_ausfuehren, nummer, runde)  # #196
                     for nummer, runde in enumerate(runden, 1)]
        wait(auftraege, timeout=limit)
    finally:
        ausfuehrer.shutdown(wait=False, cancel_futures=True)
    reihenfolge = {p.oz: i for i, p in enumerate(lv.positionen)}
    vorschlaege: dict[str, dict] = {}
    quellen_label, fehler = [], []
    for nummer, (runde, auftrag) in enumerate(zip(runden, auftraege), 1):
        if not auftrag.done() or auftrag.cancelled():
            fehler.append(FutureTimeout())
            logger.warning("Norm check N5: research round %d of %d timed out after %g s; its hints are missing.",
                           nummer, len(runden), limit)
            continue
        if auftrag.exception() is not None:
            fehler.append(auftrag.exception())
            logger.warning("Norm check N5: research round %d of %d failed (%s); its hints are missing.",
                           nummer, len(runden), auftrag.exception())
            continue
        text, quelle, belege = _antworttext(auftrag.result())
        quellen_label.append(quelle)
        teil_lv = lv.model_copy(update={"positionen": runde})
        for vorschlag in vorschlaege_aus_antwort(text, teil_lv, bekannt, belege):
            alt = vorschlaege.setdefault(vorschlag["norm_id"], vorschlag)
            if alt is not vorschlag:
                alt["oz"] = sorted(set(alt["oz"]) | set(vorschlag["oz"]), key=reihenfolge.__getitem__)
                alt["quellen"] = _quellen_vereinen(alt["quellen"], vorschlag["quellen"])
    if fehler and not quellen_label:
        raise fehler[0]
    quelle = quellen_label[0] if len(set(quellen_label)) == 1 else "AI research"
    if len(runden) > 1 and quellen_label:
        quelle += f", {len(quellen_label)} of {len(runden)} research rounds"
    ids = _Ids()
    geordnet = sorted(vorschlaege.values(), key=lambda v: reihenfolge[v["oz"][0]])[:MAX_HINWEISE]
    return ([_finding(v, register.suche(v["norm_id"], v["familie"]), register, quelle, ids) for v in geordnet],
            not fehler)


# --- Background run and cache per LV hash (#166) -------------------------------------------------
_HINTERGRUND = ThreadPoolExecutor(max_workers=2, thread_name_prefix="norm-ki-lv")
_SPERRE = threading.Lock()
_CACHE: "OrderedDict[str, list[Finding]]" = OrderedDict()
_LAUFEND: dict[str, Future] = {}
_ZUHOERER: dict[str, list] = {}  # progress callbacks of the jobs waiting for a running research
_LETZTE: dict[str, tuple] = {}  # last progress message of a running research, replayed to late listeners


def _schluessel(lv: LV) -> str:
    """LV content plus everything that changes the research (model, search budget, rounds, answer language)."""
    konfiguration = llm.config()
    kennung = json.dumps([konfiguration["provider"], konfiguration["model"], _max_suchen(), _max_runden(),
                      sprache.aktuell() or ""])  # #196: German and English results are cached separately
    return hashlib.sha256((kennung + lv.model_dump_json()).encode("utf-8")).hexdigest()


def cache_leeren() -> None:
    """Forget cached research results (tests, or after a model change)."""
    with _SPERRE:
        _CACHE.clear()


def _lauf(lv: LV, schluessel: str) -> list[Finding]:
    def verteile(meldung: str, anteil: float | None = None) -> None:
        with _SPERRE:
            _LETZTE[schluessel] = (meldung, anteil)
            zuhoerer = list(_ZUHOERER.get(schluessel, ()))
        for melde in zuhoerer:
            _melden(melde, meldung, anteil)

    try:
        hinweise, vollstaendig = _recherche(lv, None, None, None, verteile)
        if vollstaendig:  # a partial result is used once, but researched again next time
            with _SPERRE:
                _CACHE[schluessel] = hinweise
                while len(_CACHE) > CACHE_GROESSE:
                    _CACHE.popitem(last=False)
        return hinweise
    finally:
        with _SPERRE:
            _LAUFEND.pop(schluessel, None)
            _LETZTE.pop(schluessel, None)


def _auftrag(lv: LV) -> tuple[list[Finding] | None, Future | None]:
    """The cached findings, or the running (or newly started) background research of this LV."""
    schluessel = _schluessel(lv)
    with _SPERRE:
        if schluessel in _CACHE:
            _CACHE.move_to_end(schluessel)
            return [f.model_copy() for f in _CACHE[schluessel]], None
        if schluessel not in _LAUFEND:
            _LAUFEND[schluessel] = _HINTERGRUND.submit(contextvars.copy_context().run, _lauf,  # #196
                                                       lv.model_copy(deep=True), schluessel)
        return None, _LAUFEND[schluessel]


def starte_recherche(lv: LV) -> None:
    """Start the N5 research for `lv` in the background (no wait); `recherchiere_normen_sicher` then
    picks up the running result. Does nothing when switched off or in mock/offline mode; never raises."""
    try:
        if normpruefung_aktiv() and norm_ki_aktiv() and _client_verfuegbar():
            _auftrag(lv)
    except Exception:
        logger.exception("Norm check N5 could not be started in the background.")


def _warte(lv: LV, melde) -> list[Finding]:
    """Findings from the cache or the running background research; `melde` follows its rounds meanwhile."""
    schluessel = _schluessel(lv)
    treffer, auftrag = _auftrag(lv)
    if auftrag is None:
        _melden(melde, "Standards research: result ready (researched in the background or cached for this BoQ).", 1.0)
        return treffer
    if melde is not None:
        with _SPERRE:
            _ZUHOERER.setdefault(schluessel, []).append(melde)
            letzte = _LETZTE.get(schluessel)
        if letzte:
            _melden(melde, *letzte)
    try:
        return [f.model_copy() for f in auftrag.result(timeout=_timeout() + 15)]
    finally:
        if melde is not None:
            with _SPERRE:
                liste = _ZUHOERER.get(schluessel, [])
                if melde in liste:
                    liste.remove(melde)
                if not liste:
                    _ZUHOERER.pop(schluessel, None)


def recherchiere_normen_sicher(lv: LV, client: Client | None = None, melde=None) -> list[Finding]:
    """Hook called by `pruefe_normen_sicher()`: [] when switched off, in mock/offline mode, on error
    or on timeout (logged). With an injected `client` the provider check and cache are skipped (tests).
    `melde(meldung, anteil)`: optional progress of the research rounds (#165 job progress, step 5)."""
    if not norm_ki_aktiv() or (client is None and not _client_verfuegbar()):
        return []  # switched off or mock by configuration: deliberate, so no step status (report unchanged)
    try:
        findings = recherchiere_normen(lv, client=client, melde=melde) if client is not None else _warte(lv, melde)
    except FutureTimeout:
        logger.exception("Norm check N5 (AI research) timed out; the report is returned without N5 hints.")
        ki_status.melde("normrecherche", "fehler", f"No answer within {_timeout():g} s (NORM_KI_TIMEOUT); "
                                                   "the report has no AI norm hints.")
    except Exception as exc:
        logger.exception("Norm check N5 (AI research) failed; the report is returned without N5 hints.")
        text = str(exc) if isinstance(exc, llm.LLMError) else f"The model call failed ({type(exc).__name__})."
        ki_status.melde("normrecherche", "fehler", f"{text} The report has no AI norm hints.")
    else:
        ki_status.melde("normrecherche", "ok", f"{len(findings)} additional standard(s) suggested.",
                        modell=_modellname() if client is None else None)
        return findings
    return []


def _modellname() -> str | None:
    zustand = llm.status()
    return None if zustand["mock"] else f"{zustand['provider']}/{zustand['model']}"

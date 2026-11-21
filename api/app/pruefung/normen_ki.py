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

Switch `NORM_KI_RECHERCHE` (`0`/`off`/`false`/`no` = off). Otherwise the pass runs only when the
existing client in `app.ai.llm` is a real provider with a key; in mock/offline mode it returns no
findings and makes no call, so the report stays identical. The model call runs with a timeout
(`NORM_KI_TIMEOUT`, seconds, default 30); errors and timeouts are logged and skipped.
"""
import json
import logging
import os
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

from ..ai import llm
from ..modelle import LV, Finding
from .normen import (
    AUS_WERTE, KEIN_NORMGUTACHTEN, NORM_MUSTER, Register, RegisterEintrag, _Ids, _normalisiere, _quelle,
    extrahiere_normverweise, lade_register,
)

logger = logging.getLogger(__name__)

NORM_KI_HINWEIS = "NORM_KI_HINWEIS"
BESTAETIGT = "im Register bestätigt"
UNBESTAETIGT = "KI-Hinweis, unbestätigt – bitte prüfen"
STANDARD_TIMEOUT = 30.0
MAX_TOKENS = 2000
MAX_VORSCHLAEGE = 15
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
    "guidelines) that typically apply to the described work but are not referenced. Use only designations "
    "you are certain exist; never quote or paraphrase standard text; never call anything a violation. Only "
    "use OZ values from the input. Answer with JSON only, no prose: "
    '{"vorschlaege": [{"norm_id": "DIN 4109", "titel": "short title", "oz": ["01.02"], '
    '"begruendung": "one short sentence why it may apply", "konfidenz": 0.0}]}. '
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


def _timeout() -> float:
    try:
        wert = float(os.environ.get("NORM_KI_TIMEOUT", STANDARD_TIMEOUT))
    except ValueError:
        return STANDARD_TIMEOUT
    return wert if wert > 0 else STANDARD_TIMEOUT


def _eingabe(lv: LV, gefunden: list[str]) -> str:
    positionen, laenge = [], 0
    for position in lv.positionen:
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


def vorschlaege_aus_antwort(text: str, lv: LV, bekannt: set[str]) -> list[dict]:
    """Validated, deduplicated suggestions; invalid entries are dropped, never raised.

    `bekannt` holds the designations and families N1 already found. A suggestion is dropped when its
    designation or family is among them, when it names no OZ of this LV, or when it is malformed.
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
        })
        vorschlag["oz"] = sorted(set(vorschlag["oz"]) | set(oz_liste), key=reihenfolge.__getitem__)
    ergebnis = sorted(vorschlaege.values(), key=lambda v: reihenfolge[v["oz"][0]])
    return ergebnis[:MAX_VORSCHLAEGE]


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


def _antworttext(antwort) -> tuple[str, str]:
    if isinstance(antwort, llm.Answer):
        return antwort.text, f"{antwort.provider}/{antwort.model}"
    return (antwort if isinstance(antwort, str) else ""), "AI research"


def recherchiere_normen(lv: LV, register: Register | None = None, client: Client | None = None,
                        timeout: float | None = None) -> list[Finding]:
    """N5 findings for one LV. Raises on model errors and timeouts; callers use the guarded variant."""
    register = register or lade_register()
    verweise = [v for v in extrahiere_normverweise(lv) if not v.pauschal]
    gefunden = list(dict.fromkeys(v.norm_id for v in verweise))
    bekannt = set(gefunden) | {v.familie for v in verweise}
    prompt = _eingabe(lv, gefunden)
    aufruf = client or llm.complete
    ausfuehrer = ThreadPoolExecutor(max_workers=1, thread_name_prefix="norm-ki")
    try:
        antwort = ausfuehrer.submit(aufruf, prompt, system=SYSTEM, max_tokens=MAX_TOKENS).result(
            timeout=timeout or _timeout())
    finally:
        ausfuehrer.shutdown(wait=False, cancel_futures=True)
    text, quelle = _antworttext(antwort)
    ids = _Ids()
    return [_finding(v, register.suche(v["norm_id"], v["familie"]), register, quelle, ids)
            for v in vorschlaege_aus_antwort(text, lv, bekannt)]


def recherchiere_normen_sicher(lv: LV, client: Client | None = None) -> list[Finding]:
    """Hook called by `pruefe_normen_sicher()`: [] when switched off, in mock/offline mode, on error
    or on timeout (logged). With an injected `client` the provider check is skipped (tests)."""
    if not norm_ki_aktiv() or (client is None and not _client_verfuegbar()):
        return []
    try:
        return recherchiere_normen(lv, client=client)
    except FutureTimeout:
        logger.exception("Norm check N5 (AI research) timed out; the report is returned without N5 hints.")
    except Exception:
        logger.exception("Norm check N5 (AI research) failed; the report is returned without N5 hints.")
    return []

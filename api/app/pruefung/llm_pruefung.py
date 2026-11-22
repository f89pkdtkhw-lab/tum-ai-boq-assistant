"""Structured LLM review of BoQ items, with an offline mock and a guarded real-model path.

A "model" is any callable ``(batch of Position) -> raw JSON text``. Its raw answer is validated
strictly before it becomes a ``Finding``: only OZ from the batch, source ``modell``, no euro amount,
standard references only with catalogue evidence.

- Mock mode (no key, ``LLM_PROVIDER=mock``): the offline mock runs over the first batch only and every
  accepted finding is an explicit demonstration (``regel_id`` starts with ``MOCK_``).
- Real mode (a provider with a key, e.g. Claude via ANTHROPIC_API_KEY, or Gemini): every item is reviewed, in batches of
  ``LLM_BATCH_SIZE`` items, through ``app.ai.llm.complete``. Findings carry ``regel_id`` ``LLM_*``.
  Every batch call is bounded by ``LLM_BATCH_TIMEOUT`` seconds, the whole review by the generous
  ``LLM_REVIEW_TIMEOUT`` (#167). A failing or unfinished batch never discards the others: partial
  results are kept and the failed batches are named in ``reason`` (no silent mock fallback). Only a
  run without a single readable answer falls back to the mock result with ``mock=True`` and a reason,
  so the report is always returned. An optional ``fortschritt(done, total)`` callback reports each
  finished batch (progress for the analysis job, #165).
"""
import contextvars
import json
import os
import re
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeout
from dataclasses import dataclass, field

from pydantic import ValidationError

from ..ai import llm
from ..fortschritt import AnalyseAbgebrochen
from ..modelle import Finding, LV, Position

DEFAULT_BATCH_SIZE = 20
DEFAULT_REVIEW_TIMEOUT = 600.0  # seconds for the whole real-model review (#167: all batches of a large LV; < job's 2400 s)
DEFAULT_BATCH_TIMEOUT = 90.0    # seconds per batch call (#167: instead of one tight global deadline)
DEFAULT_PARALLEL = 3           # concurrent batch calls (low enough for small rate limits)
DEFAULT_EFFORT = "low"         # Claude effort for the item review: short, consistent answers, fast
MAX_TOKENS = 8192
MAX_LANGTEXT = 1500
MOCK_PREFIX = "MOCK_"
LLM_PREFIX = "LLM_"
DEMO_MARKER = "Demonstration"
ALLOWED_KATEGORIEN = frozenset({"fehler", "risiko", "nachtrag"})
ALLOWED_SCHWEREN = frozenset({"kritisch", "hoch", "mittel", "niedrig"})

MockModel = Callable[[list[Position]], str]
Fortschritt = Callable[[int, int], None]  # (finished batches, total batches); main.py maps it to #165 step 3


@dataclass
class BatchResult:
    findings: list[Finding] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)  # reasons, for diagnostics/tests


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower() or "x"


def stable_id(oz: str, regel_id: str, real: bool = False) -> str:
    """Depends only on OZ and rule, so it is identical however the BoQ is split into batches."""
    return f"{'llm' if real else 'mock'}-modell-{_slug(oz)}-{_slug(regel_id)}"


_FINDING_KEYS = frozenset(Finding.model_fields) | {"norm_ref"}


def _normalise_real(item: dict) -> dict:
    """Real-model answers: fixed source, no euro amount, ``LLM_`` rule prefix, unknown keys dropped."""
    item = {key: value for key, value in item.items() if key in _FINDING_KEYS}
    item["quelle"] = "modell"
    item["euro_wirkung"] = None  # the model never estimates money; prices come from rules and data
    regel_id = item.get("regel_id")
    regel_id = re.sub(r"[^A-Z0-9_]+", "_", str(regel_id).upper()).strip("_") if regel_id else "REVIEW"
    item["regel_id"] = regel_id if regel_id.startswith(LLM_PREFIX) else f"{LLM_PREFIX}{regel_id}"
    for key in ("kategorie", "schwere"):
        if isinstance(item.get(key), str):
            item[key] = item[key].strip().lower()
    return item


def validiere_antwort(
    raw: str,
    batch: list[Position],
    normkatalog: Mapping[str, str] | None = None,
    *,
    real: bool = False,
) -> BatchResult:
    """Validate one raw JSON answer against the batch. Invalid parts are rejected, never raised.

    ``real=False`` (mock): strict, ``MOCK_`` rule ids, every text marked as demonstration.
    ``real=True``: answers of a real model, normalised first (see ``_normalise_real``), not marked.
    Fenced JSON or JSON with prose around it is accepted in both modes.
    """
    result = BatchResult()
    try:
        data = llm.parse_json(raw)
    except (TypeError, ValueError):
        result.rejected.append("invalid JSON")
        return result
    items = data.get("findings") if isinstance(data, dict) else None
    if not isinstance(items, list):
        result.rejected.append("missing findings list")
        return result
    present = {p.oz for p in batch}
    katalog = normkatalog or {}
    for item in items:
        if not isinstance(item, dict):
            result.rejected.append("finding is not an object")
            continue
        item = _normalise_real(item) if real else dict(item)
        oz, regel_id = item.get("oz"), item.get("regel_id")
        if isinstance(oz, (int, float)) and not isinstance(oz, bool):
            oz = item["oz"] = str(oz)
        norm_ref = item.pop("norm_ref", None)
        if oz not in present:
            result.rejected.append(f"invented or out-of-batch OZ: {oz!r}")
        elif item.get("quelle") != "modell":
            result.rejected.append(f"OZ {oz}: source must be 'modell'")
        elif item.get("kategorie") not in ALLOWED_KATEGORIEN:
            result.rejected.append(f"OZ {oz}: category not allowed")
        elif item.get("schwere") not in ALLOWED_SCHWEREN:
            result.rejected.append(f"OZ {oz}: severity not allowed")
        elif not (isinstance(regel_id, str) and regel_id.startswith(LLM_PREFIX if real else MOCK_PREFIX)):
            result.rejected.append(f"OZ {oz}: regel_id must start with {LLM_PREFIX if real else MOCK_PREFIX}")
        elif item.get("euro_wirkung") is not None:
            result.rejected.append(f"OZ {oz}: euro estimate not allowed")
        elif norm_ref is not None and norm_ref not in katalog:
            result.rejected.append(f"OZ {oz}: standard reference {norm_ref!r} not in catalogue")
        else:
            if norm_ref is not None:
                item["begruendung"] = f"{item.get('begruendung', '')} [Catalogue: {norm_ref} – {katalog[norm_ref]}]"
            for key in ("titel", "begruendung") if not real else ():
                if isinstance(item.get(key), str) and item[key].strip() and DEMO_MARKER not in item[key]:
                    item[key] = f"{DEMO_MARKER}: {item[key]}"
            item["id"] = stable_id(oz, regel_id, real)
            try:
                result.findings.append(Finding(**item))
            except (ValidationError, TypeError) as exc:
                result.rejected.append(f"OZ {oz}: invalid finding ({type(exc).__name__})")
    return result


def mock_modell(batch: list[Position]) -> str:
    """Default offline mock: one fixed demonstration finding for the first item of the batch."""
    if not batch:
        return json.dumps({"findings": []})
    return json.dumps({"findings": [{
        "oz": batch[0].oz, "kategorie": "risiko", "schwere": "niedrig",
        "titel": f"{DEMO_MARKER} (Mock) – no domain review",
        "begruendung": f"{DEMO_MARKER}: offline mock showing the report contract. "
                       "No actual finding or model request.",
        "vorschlag": "Implement and validate fixed review rules; do not count the mock as a finding.",
        "quelle": "modell", "regel_id": "MOCK_LLM", "euro_wirkung": None,
    }]})


def pruefe_in_batches(
    lv: LV,
    modell: MockModel = mock_modell,
    batch_size: int = DEFAULT_BATCH_SIZE,
    normkatalog: Mapping[str, str] | None = None,
    max_batches: int | None = None,
) -> BatchResult:
    """Run the mock model over the BoQ in batches of at most ``batch_size`` items."""
    total = BatchResult()
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    seen: set[str] = set()
    for run, start in enumerate(range(0, len(lv.positionen), batch_size)):
        if max_batches is not None and run >= max_batches:
            break
        batch = lv.positionen[start:start + batch_size]
        try:
            raw = modell(batch)
        except Exception as exc:  # a failing mock model must not break the review
            total.rejected.append(f"model call failed ({type(exc).__name__})")
            continue
        part = validiere_antwort(raw, batch, normkatalog)
        total.rejected.extend(part.rejected)
        for finding in part.findings:
            if finding.id not in seen:
                seen.add(finding.id)
                total.findings.append(finding)
    return total


SYSTEM = (
    "You review items (positions) of a German bill of quantities (Leistungsverzeichnis, LV) for a "
    "construction contractor before pricing. For each item, look for real problems only: vague or open "
    "wording (e.g. 'nach Erfordernis', 'nach Wahl des AN'), contradictions between short and long text, "
    "quantity or unit that does not fit the described work, missing information needed to price the item "
    "(material, dimensions, class, thickness), and scope that is likely to cause a Nachtrag (change order). "
    "Answer with JSON only, no prose, exactly in this shape: "
    '{"findings": [{"oz": "<OZ from the input>", "kategorie": "fehler|risiko|nachtrag", '
    '"schwere": "kritisch|hoch|mittel|niedrig", "titel": "short title", '
    '"begruendung": "evidence quoted from the item text", "vorschlag": "concrete clarification question or fix", '
    '"regel_id": "LLM_<SHORT_UPPERCASE_TOPIC>"}]}. '
    "Rules: use only OZ values from the input; at most two findings per item; no finding for unremarkable "
    "items; never state euro amounts or prices; never cite standards (DIN, VOB) by number; write titel, "
    "begruendung and vorschlag in English and keep German domain terms. If nothing is wrong, answer "
    '{"findings": []}.'
)


@dataclass
class LlmPruefung:
    """Result of the LLM review including how it was produced (for ``kennzahlen.modell_mock``)."""

    findings: list[Finding]
    mock: bool
    reason: str | None = None
    provider: str = "mock"
    model: str = "mock"
    batches: int = 0
    rejected: list[str] = field(default_factory=list)
    fehlgeschlagen: int = 0  # #167: batches without a readable answer (their items were not reviewed)


def _int_env(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, "") or default)
    except ValueError:
        return default
    return value if value >= 1 else default


def _prompt(batch: list[Position]) -> str:
    items = [{"oz": p.oz, "abschnitt": " / ".join(p.titel_pfad), "kurztext": p.kurztext,
              "langtext": p.langtext[:MAX_LANGTEXT], "menge": p.menge, "einheit": p.einheit,
              "typ": p.typ} for p in batch]
    return ("Review these LV items and answer with the JSON object described in the instructions.\n"
            f"Items:\n{json.dumps(items, ensure_ascii=False)}")


def llm_modell(timeout: float) -> MockModel:
    """The real model as a batch callable: one ``llm.complete`` call per batch (raises LLMError)."""
    def call(batch: list[Position]) -> str:
        return llm.complete(_prompt(batch), system=SYSTEM, max_tokens=MAX_TOKENS, timeout=timeout, json_mode=True,
                            effort=os.environ.get("LLM_REVIEW_EFFORT", "").strip().lower() or DEFAULT_EFFORT).text
    return call


def mock_pruefung(lv: LV, reason: str | None = None, fortschritt: "Fortschritt | None" = None) -> LlmPruefung:
    """The offline mock review (first batch only), as used without a key and on a full fallback.
    `fortschritt` keeps the signature interchangeable with `pruefe_mit_llm_status` (one step, at once)."""
    _melde(fortschritt, 1, 1)
    return LlmPruefung(pruefe_in_batches(lv, max_batches=1).findings, mock=True, reason=reason,
                       provider="mock", model=llm.DEFAULT_MODELS["mock"])


def _melde(fortschritt: Fortschritt | None, fertig: int, gesamt: int) -> None:
    if fortschritt is None:
        return
    try:
        fortschritt(fertig, gesamt)
    except AnalyseAbgebrochen:  # #165: the job passed its own timeout; stop the review cleanly
        raise
    except Exception:  # a broken progress listener must never break the review
        pass


def _bereich(batch: list[Position]) -> str:
    return batch[0].oz if len(batch) == 1 else f"{batch[0].oz}–{batch[-1].oz}"


def _fehler_text(exc: BaseException, name: str) -> str:
    return str(exc) if isinstance(exc, llm.LLMError) else f"{name} call failed ({type(exc).__name__})."


def pruefe_mit_llm_status(
    lv: LV,
    modell: MockModel | None = None,
    batch_size: int | None = None,
    timeout: float | None = None,
    parallel: int | None = None,
    fortschritt: Fortschritt | None = None,
) -> LlmPruefung:
    """Review all items with the configured model; never raises.

    Without a usable provider (or ``modell``), the offline mock result is returned unchanged
    (``mock=True``). With a provider, every batch is sent, each bounded by ``LLM_BATCH_TIMEOUT``
    and all together by ``timeout`` (default ``LLM_REVIEW_TIMEOUT``). Failed or unfinished batches
    are reported in ``reason`` while the findings of the other batches are kept (``mock=False``).
    Only when no batch gave a readable answer is the mock result returned with ``mock=True`` and a
    readable ``reason``. ``modell`` is a test seam that replaces the provider call; ``fortschritt``
    is called with ``(finished, total)`` after every batch.
    """
    state = llm.status()
    if modell is None and state["mock"]:
        return mock_pruefung(lv, state["reason"], fortschritt)
    limit = timeout if timeout and timeout > 0 else llm.seconds("LLM_REVIEW_TIMEOUT", DEFAULT_REVIEW_TIMEOUT)
    pro_batch = min(limit, llm.seconds("LLM_BATCH_TIMEOUT", DEFAULT_BATCH_TIMEOUT))
    size = batch_size or _int_env("LLM_BATCH_SIZE", DEFAULT_BATCH_SIZE)
    workers = parallel or _int_env("LLM_PARALLEL", DEFAULT_PARALLEL)
    call = modell or llm_modell(pro_batch)
    name = state["provider"] if modell is None else "model"
    batches = [lv.positionen[start:start + size] for start in range(0, len(lv.positionen), size)]
    if not batches:
        return LlmPruefung([], mock=False, provider=state["provider"], model=state["model"])

    answers: list[str | None] = [None] * len(batches)
    fehler: dict[int, str] = {}
    pool = ThreadPoolExecutor(max_workers=max(1, min(workers, len(batches))), thread_name_prefix="llm-review")
    try:
        futures = {pool.submit(contextvars.copy_context().run, call, batch): index  # #196: keep answer language
                   for index, batch in enumerate(batches)}
        fertig = 0
        try:
            for future in as_completed(futures, timeout=limit + 1):
                index = futures[future]
                exc = future.exception()
                if exc is not None:
                    fehler[index] = _fehler_text(exc, name)
                else:
                    answers[index] = future.result()
                fertig += 1
                _melde(fortschritt, fertig, len(batches))
        except FuturesTimeout:
            for future, index in futures.items():
                if not future.done() or (answers[index] is None and index not in fehler):
                    fehler[index] = f"{name} did not finish the review within {limit:g} s."
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    total, seen = BatchResult(), set()
    for index, (batch, raw) in enumerate(zip(batches, answers)):
        if raw is None:
            continue
        part = validiere_antwort(raw, batch, real=True)
        if part.rejected and part.rejected[0] in ("invalid JSON", "missing findings list"):
            fehler[index] = f"{name} answered without readable JSON."
        total.rejected.extend(part.rejected)
        for finding in part.findings:
            if finding.id not in seen:
                seen.add(finding.id)
                total.findings.append(finding)
    if len(fehler) == len(batches):
        erster = fehler[min(fehler)]
        if all(text == erster for text in fehler.values()) and "within" in erster and "finish" in erster:
            return mock_pruefung(lv, f"{erster.rstrip('.')}; no AI findings in this run.")
        prefix = f"Batch 1/1: " if len(batches) == 1 else f"All {len(batches)} batches failed; first: "
        return mock_pruefung(lv, f"{prefix}{erster} No AI findings in this run.")
    reason = None
    if fehler:
        teile = [f"batch {i + 1} (OZ {_bereich(batches[i])}): {fehler[i]}" for i in sorted(fehler)[:5]]
        mehr = f" … and {len(fehler) - 5} more" if len(fehler) > 5 else ""
        reason = (f"{len(fehler)}/{len(batches)} model batch(es) failed, their items were not reviewed by the "
                  f"model; findings of the other {len(batches) - len(fehler)} batch(es) are kept. "
                  + "; ".join(teile) + mehr)
    return LlmPruefung(total.findings, mock=False, reason=reason, provider=state["provider"], model=state["model"],
                       batches=len(batches), rejected=total.rejected, fehlgeschlagen=len(fehler))


def pruefe_mit_llm(lv: LV) -> list[Finding]:
    """Findings only (see ``pruefe_mit_llm_status``); offline mock over the first batch without a key."""
    return pruefe_mit_llm_status(lv).findings

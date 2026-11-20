"""Offline mock of the structured LLM review; never imports or calls a model provider.

A mock "model" is any callable ``(batch of Position) -> raw JSON text``. Its raw answer is
validated strictly before it becomes a ``Finding``. Every accepted finding is an explicit
demonstration (``regel_id`` starts with ``MOCK_``) and is not a real domain finding.
"""
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from pydantic import ValidationError

from ..modelle import Finding, LV, Position

DEFAULT_BATCH_SIZE = 20
MOCK_PREFIX = "MOCK_"
DEMO_MARKER = "Demonstration"
ALLOWED_KATEGORIEN = frozenset({"fehler", "risiko", "nachtrag"})
ALLOWED_SCHWEREN = frozenset({"kritisch", "hoch", "mittel", "niedrig"})

MockModel = Callable[[list[Position]], str]


@dataclass
class BatchResult:
    findings: list[Finding] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)  # reasons, for diagnostics/tests


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower() or "x"


def stable_id(oz: str, regel_id: str) -> str:
    """Depends only on OZ and rule, so it is identical however the BoQ is split into batches."""
    return f"mock-modell-{_slug(oz)}-{_slug(regel_id)}"


def validiere_antwort(
    raw: str,
    batch: list[Position],
    normkatalog: Mapping[str, str] | None = None,
) -> BatchResult:
    """Validate one raw JSON answer against the batch. Invalid parts are rejected, never raised."""
    result = BatchResult()
    try:
        data = json.loads(raw)
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
        item = dict(item)
        oz, regel_id = item.get("oz"), item.get("regel_id")
        norm_ref = item.pop("norm_ref", None)
        if oz not in present:
            result.rejected.append(f"invented or out-of-batch OZ: {oz!r}")
        elif item.get("quelle") != "modell":
            result.rejected.append(f"OZ {oz}: source must be 'modell'")
        elif item.get("kategorie") not in ALLOWED_KATEGORIEN:
            result.rejected.append(f"OZ {oz}: category not allowed")
        elif item.get("schwere") not in ALLOWED_SCHWEREN:
            result.rejected.append(f"OZ {oz}: severity not allowed")
        elif not (isinstance(regel_id, str) and regel_id.startswith(MOCK_PREFIX)):
            result.rejected.append(f"OZ {oz}: regel_id must start with {MOCK_PREFIX}")
        elif item.get("euro_wirkung") is not None:
            result.rejected.append(f"OZ {oz}: euro estimate not allowed")
        elif norm_ref is not None and norm_ref not in katalog:
            result.rejected.append(f"OZ {oz}: standard reference {norm_ref!r} not in catalogue")
        else:
            if norm_ref is not None:
                item["begruendung"] = f"{item.get('begruendung', '')} [Catalogue: {norm_ref} – {katalog[norm_ref]}]"
            for key in ("titel", "begruendung"):
                if isinstance(item.get(key), str) and item[key].strip() and DEMO_MARKER not in item[key]:
                    item[key] = f"{DEMO_MARKER}: {item[key]}"
            item["id"] = stable_id(oz, regel_id)
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


def pruefe_mit_llm(lv: LV) -> list[Finding]:
    """Default entry point: a single offline mock run over the first batch only."""
    return pruefe_in_batches(lv, max_batches=1).findings

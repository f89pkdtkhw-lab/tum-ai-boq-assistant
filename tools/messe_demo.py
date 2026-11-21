"""Measure the offline review against the 25 documented findings of the structural works single-family house.

    .venv/bin/python tools/messe_demo.py                 # Markdown report on stdout
    .venv/bin/python tools/messe_demo.py --json          # same result as JSON
    .venv/bin/python tools/messe_demo.py --runs 5        # more timing runs (default 3)

The run uses the real product path: PDF import (`app.lv.importer.importiere`) followed by the
review route function (`app.main.pruefen`: fixed rules, quantity plausibility, risk hints, offline
model mock). It therefore needs the API dependencies (`api/requirements.txt`); the measurement
logic below uses only the standard library and is covered by `tests/test_messe_demo.py`.

Definitions, fixed before the run:
- Gold standard: the table in `data/testfaelle/rohbau_efh/erwartung.md`, read in place and never changed.
- Findings with a `MOCK_` rule ID are model demonstrations. They are excluded from every count.
- A gold entry is a HIT when at least one non-mock finding sits on one of its OZs (or inside its
  title) and carries a rule ID listed for that entry in `ACCEPTED`. Otherwise it is MISSED.
- A FALSE ALARM is a non-mock finding that matches no gold entry. The gold list is a manual review,
  so an unmatched finding may be true but unlisted; it is still counted as a false alarm.
- No rate is computed without its denominator; nothing is extrapolated beyond this single LV.
"""
import argparse
import hashlib
import json
import re
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLD_FILE = ROOT / "data/testfaelle/rohbau_efh/erwartung.md"
PDF_FILE = ROOT / "data/testfaelle/rohbau_efh/lv_rohbau_efh.pdf"
EXPECTED_ENTRIES = 25
MOCK_PREFIX = "MOCK_"

# Gold entry number -> (rule IDs that count as a hit, generic?, short label of the finding type).
# Hand-fixed from the rule catalogue; an empty set means no fixed rule implements this finding type
# (the gold entry then stays missed until one exists). `generic=True` marks a hit where the rule only
# covers the position type, not the specific point of the gold entry. Extend only together with a
# new rule, never to turn a miss into a hit.
ACCEPTED: dict[int, tuple[frozenset[str], bool, str]] = {
    1: (frozenset({"EINHEIT_FEHLT"}), False, "quantity without unit"),
    2: (frozenset({"EINHEIT_FEHLT", "MENGE_FEHLT", "LANGTEXT_FEHLT"}), False, "item without quantity, unit, long text"),
    3: (frozenset({"EINHEIT_FEHLT", "MENGE_FEHLT"}), False, "missing quantity/unit (standard citation needs the model)"),
    4: (frozenset({"TEXT_WIDERSPRUCH"}), False, "short text contradicts long text"),
    5: (frozenset({"TEXT_WIDERSPRUCH"}), False, "short text contradicts long text"),
    6: (frozenset(), False, "implausible dimension / unit error"),
    7: (frozenset({"NORM_KLASSE_UNGUELTIG"}), False, "typo in exposure classes"),
    8: (frozenset(), False, "contradictory manufacturer (model)"),
    9: (frozenset({"NORM_PRODUKTNORM_WIDERSPRUCH"}), False, "wrong standard for material"),
    10: (frozenset({"BEZEICHNUNG_ABWEICHUNG"}), False, "deviating insulation grade"),
    11: (frozenset({"MENGE_SCHICHTEN_ABWEICHUNG"}), False, "inconsistent layer areas"),
    12: (frozenset({"MENGE_SCHICHTEN_ABWEICHUNG"}), False, "implausibly small quantity"),
    13: (frozenset(), False, "possible double earthing (model)"),
    14: (frozenset({"NORM_ZURUECKGEZOGEN"}), False, "withdrawn standard (catalogue)"),
    15: (frozenset(), False, "date before tender date (model)"),
    16: (frozenset({"RISK_BEDARF"}), False, "contingency items"),
    17: (frozenset({"RISK_STUNDENLOHN"}), False, "open hourly-wage budget"),
    18: (frozenset({"RISK_PAUSCHAL"}), True, "lump-sum item with open scope (model for the specifics)"),
    19: (frozenset(), False, "scope undetermined at bid time (model)"),
    20: (frozenset(), False, "approximate dimensions, interface (model)"),
    21: (frozenset(), False, "deviation from VOB/B in preamble (model)"),
    22: (frozenset(), False, "fixed prices without price escalation (model)"),
    23: (frozenset(), False, "risk shift in preamble (model)"),
    24: (frozenset(), False, "missing positions (model)"),
    25: (frozenset(), False, "spelling errors"),
}

_OZ = re.compile(r"\d+(?:\.\.\.\d+)+")


@dataclass(frozen=True)
class GoldEntry:
    nr: int
    oz_cell: str
    kategorie: str
    rule_findable: bool  # gold column "Regel?" starts with "ja"
    oz: tuple[str, ...]  # exact OZs
    titel: tuple[str, ...]  # title prefixes, e.g. "7" matches every "7...n"


def expand_oz(cell: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """OZs and title prefixes named in a gold OZ cell; preamble pages and "div." name none."""
    cell = cell.replace("`", "").strip()
    exact: list[str] = []
    for part in re.split(r"[,/]", cell):
        part = part.strip()
        bounds = [t.strip() for t in re.split(r"[–—]", part)]
        if len(bounds) == 2 and all(_OZ.fullmatch(b) for b in bounds):
            head_a, _, tail_a = bounds[0].rpartition("...")
            head_b, _, tail_b = bounds[1].rpartition("...")
            if head_a != head_b or not (tail_a.isdigit() and tail_b.isdigit()) or int(tail_a) > int(tail_b):
                raise ValueError(f"Cannot expand OZ range {part!r}")
            exact.extend(f"{head_a}...{n}" for n in range(int(tail_a), int(tail_b) + 1))
        elif _OZ.fullmatch(part):
            exact.append(part)
    titles = [m.group(1) for m in re.finditer(r"\bTitel\s+(\d+)\b", cell)]
    return tuple(dict.fromkeys(exact)), tuple(titles)


def parse_gold(text: str) -> list[GoldEntry]:
    """Read the numbered table rows `| nr | OZ | Kat. | Befund | Regel? |` of the gold standard."""
    entries = []
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 5 or not cells[0].isdigit():
            continue
        exact, titles = expand_oz(cells[1])
        entries.append(GoldEntry(int(cells[0]), cells[1], cells[2], cells[-1].lower().startswith("ja"), exact, titles))
    return entries


def _is_mock(finding: dict) -> bool:
    return str(finding.get("regel_id", "")).startswith(MOCK_PREFIX)


def _on_entry(finding: dict, entry: GoldEntry) -> bool:
    oz = finding["oz"]
    return oz in entry.oz or any(oz.startswith(f"{t}...") for t in entry.titel)


def measure(entries: list[GoldEntry], accepted: dict[int, tuple[frozenset[str], bool, str]], findings: list[dict]) -> dict:
    """Pure comparison of reported findings against the gold entries (no I/O, no model)."""
    considered = [f for f in findings if not _is_mock(f)]
    rows = []
    matched_ids: set[str] = set()
    for entry in entries:
        rules, generic, label = accepted[entry.nr]
        hits = [f for f in considered if f["regel_id"] in rules and _on_entry(f, entry)]
        matched_ids.update(f["id"] for f in hits)
        if hits:
            reason = ""
        elif not rules:
            reason = "no fixed rule implements this finding type"
            if not entry.oz and not entry.titel:
                reason += "; the gold entry names no item OZ (preamble or general)"
        elif not entry.oz and not entry.titel:
            reason = "the gold entry names no item OZ (preamble or general); item-level rules cannot cite it"
        else:
            reason = "rule exists but did not fire on the cited OZ"
        rows.append({
            "nr": entry.nr, "kategorie": entry.kategorie, "oz": entry.oz_cell, "label": label,
            "rule_findable": entry.rule_findable, "hit": bool(hits), "generic": generic and bool(hits),
            "matched": sorted({f"{f['oz']} {f['regel_id']}" for f in hits}), "reason": reason,
        })
    false_alarms = [f for f in considered if f["id"] not in matched_ids]
    hits_n = sum(r["hit"] for r in rows)
    by_category = {}
    for kat in sorted({e.kategorie for e in entries}):
        sub = [r for r in rows if r["kategorie"] == kat]
        by_category[kat] = {"hits": sum(r["hit"] for r in sub), "total": len(sub)}
    findable = [r for r in rows if r["rule_findable"]]
    return {
        "gold_total": len(entries), "hits": hits_n, "missed": len(entries) - hits_n,
        "generic_hits": sum(r["generic"] for r in rows),
        "rule_findable_total": len(findable), "rule_findable_hits": sum(r["hit"] for r in findable),
        "by_category": by_category, "entries": rows,
        "findings_considered": len(considered), "findings_mock_excluded": len(findings) - len(considered),
        "findings_matched": len(considered) - len(false_alarms), "false_alarms": len(false_alarms),
        "false_alarm_list": sorted(({"oz": f["oz"], "regel_id": f["regel_id"]} for f in false_alarms),
                                   key=lambda f: (f["regel_id"], f["oz"])),
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _commit() -> str:
    try:
        out = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True)
        dirty = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--", "api"], capture_output=True, text=True).stdout.strip()
        return out.stdout.strip() + (" (+uncommitted api changes)" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def run_pipeline(pdf: Path, runs: int) -> dict:
    """Import the PDF and review it `runs` times through the real route function; return findings + timings."""
    sys.path.insert(0, str(ROOT / "api"))
    try:
        from app.lv.importer import importiere
        from app.main import pruefen
    except ModuleNotFoundError as exc:
        sys.exit(f"✗ Missing API dependency ({exc.name}). Install it first: python3 -m venv .venv && "
                 ".venv/bin/python -m pip install -r api/requirements.txt, then run with .venv/bin/python.")
    data = pdf.read_bytes()
    import_s, review_s, finding_sets, positions = [], [], [], 0
    for _ in range(runs):
        t0 = time.perf_counter()
        lv = importiere(pdf.name, data)
        t1 = time.perf_counter()
        bericht = pruefen(lv)
        t2 = time.perf_counter()
        import_s.append(t1 - t0)
        review_s.append(t2 - t1)
        positions = len(lv.positionen)
        finding_sets.append([f.model_dump() for f in bericht.findings])
    if any(s != finding_sets[0] for s in finding_sets[1:]):
        sys.exit("✗ The findings differ between runs; the measurement is not reproducible.")
    return {"positions": positions, "findings": finding_sets[0], "import_s": import_s, "review_s": review_s}


def _timing(values: list[float]) -> dict:
    return {"min": min(values), "median": statistics.median(values), "max": max(values)}


def build_result(pdf: Path, runs: int) -> dict:
    entries = parse_gold(GOLD_FILE.read_text(encoding="utf-8"))
    if len(entries) != EXPECTED_ENTRIES or {e.nr for e in entries} != set(ACCEPTED):
        sys.exit(f"✗ The gold standard now has {len(entries)} entries with numbers "
                 f"{sorted(e.nr for e in entries)}; this tool expects {EXPECTED_ENTRIES} (1..{EXPECTED_ENTRIES}). Update ACCEPTED deliberately.")
    run = run_pipeline(pdf, runs)
    result = measure(entries, ACCEPTED, run["findings"])
    total = [a + b for a, b in zip(run["import_s"], run["review_s"])]
    result["run"] = {
        "command": "python tools/messe_demo.py" + ("" if runs == 3 else f" --runs {runs}"),
        "commit": _commit(), "python": sys.version.split()[0], "runs": runs, "positions": run["positions"],
        "findings_total": len(run["findings"]),
        "pdf_sha256": _sha256(pdf)[:16], "gold_sha256": _sha256(GOLD_FILE)[:16],
        "seconds": {"import": _timing(run["import_s"]), "review": _timing(run["review_s"]), "total": _timing(total)},
    }
    return result


def render_markdown(result: dict) -> str:
    run = result["run"]
    sec = run["seconds"]
    lines = [
        "| Metric | Value |", "| --- | --- |",
        f"| Gold entries hit | {result['hits']} of {result['gold_total']} |",
        f"| Gold entries missed | {result['missed']} of {result['gold_total']} |",
        f"| Hits only by a generic rule (position type, not the specific point) | {result['generic_hits']} |",
        f"| Entries the gold marks as fixed-rule findable, hit | {result['rule_findable_hits']} of {result['rule_findable_total']} |",
        "| Hits by gold category | " + ", ".join(f"{k} {v['hits']}/{v['total']}" for k, v in result["by_category"].items()) + " |",
        f"| Findings considered (MOCK_* excluded: {result['findings_mock_excluded']}) | {result['findings_considered']} |",
        f"| Findings matching a gold entry | {result['findings_matched']} |",
        f"| False alarms (findings matching no gold entry) | {result['false_alarms']} |",
        f"| Items imported from the PDF | {run['positions']} |",
        f"| Runtime, median of {run['runs']} runs (min–max) | import {sec['import']['median']:.2f} s, review {sec['review']['median']:.3f} s, "
        f"total {sec['total']['median']:.2f} s ({sec['total']['min']:.2f}–{sec['total']['max']:.2f} s) |",
        "", "| # | Cat. | Gold OZ | Finding type | Result | Matched findings (OZ rule) / why missed |", "| --- | --- | --- | --- | --- | --- |",
    ]
    for r in result["entries"]:
        detail = "; ".join(r["matched"]) if r["hit"] else r["reason"]
        status = ("HIT (generic)" if r["generic"] else "HIT") if r["hit"] else "missed"
        lines.append(f"| {r['nr']} | {r['kategorie']} | {r['oz']} | {r['label']} | {status} | {detail} |")
    counts: dict[str, list[str]] = {}
    for f in result["false_alarm_list"]:
        counts.setdefault(f["regel_id"], []).append(f["oz"])
    lines += ["", "False alarms by rule:", ""]
    lines += [f"- `{rule}` × {len(ozs)}: {', '.join(ozs)}" for rule, ozs in counts.items()] or ["- none"]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pdf", type=Path, default=PDF_FILE, help="LV PDF to import (default: the gold-standard LV)")
    parser.add_argument("--runs", type=int, default=3, help="timing runs; findings must be identical in every run")
    parser.add_argument("--json", action="store_true", help="print JSON instead of Markdown")
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be at least 1")
    result = build_result(args.pdf, args.runs)
    print(json.dumps(result, indent=2, ensure_ascii=False) if args.json else render_markdown(result), end="")


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    main()

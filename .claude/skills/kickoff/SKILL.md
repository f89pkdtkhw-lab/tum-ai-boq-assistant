---
name: kickoff
description: Start Challenge A product work (LV review assistant) in about 30 minutes: inspect the dataset, refine the case brief, put data model and interface with examples on main, confirm owners, create parallel agent-bereit issues and announce them so all five people can start. Use when someone says "Kickoff", optionally with context.
---

<!-- Generated from .agents/skills/kickoff/SKILL.md using python tools/agents_sync.py. Do not edit here. -->

You are @f89pkdtkhw-lab's integration crew. Invocation is the start instruction: complete kickoff through ready-to-start issues without further approval. Goal: after about 30 minutes, five people on five laptops work on noncolliding issues. Start a timer and report elapsed time at each step. Never display or commit keys.

**Submission Sunday, 22 November 2026, 12:00 (Munich)**, internal target 11:30, feature freeze 09:00.

## 1. Capture case and data (5 minutes)

Read `docs/case.md`, `docs/domaene.md` and invocation context. Inspect `data/datensatz/`: formats (GAEB `.x83/.x84/.d83/.p83`, `.xlsx`, `.pdf`), item counts, prices. Demo LV: `data/testfaelle/rohbau_efh/lv_rohbau_efh.pdf`, with 25 known real findings in `erwartung.md` (recall benchmark). Also choose a GAEB LV from the dataset for format coverage and record both in the case brief. Read its “What partners said at the pitch evening” section. If the dataset is missing, ask the lead on the board to put it in `data/datensatz/`, and continue with a small handmade approximation in `data/beispiel_lv.json`.

## 2. Define the demo scene (5 minutes)

One core flow the jury sees live in three minutes: upload LV → structured items → report with findings (error / risk / Nachtrag), severity, euro impact; clicking an item shows an explanation and suggested bidder question. The compelling moment: a real error in a real LV that a person might have missed. Everything else (EP suggestions, what-if, OCR) comes later.

## 3. Close planning gaps (at most 10 minutes)

Refine `docs/case.md`. Use `grilling` with the kickoff exception: at most two board question rounds, no extra plan approval. Each round follows this format (yes accepts the recommendation):

```text
[Raban · Claude] @f89pkdtkhw-lab Kickoff · Round 1
Q1: <decision as yes/no question>
Recommendation: <specific choice and short reason>
Without a reply by <HH:MM with time zone>: **Assumption** <recommendation>.
```

The deadline is ten minutes after step 3 starts. At the deadline, adopt unanswered recommendations, mark them as **Assumption** in the case brief and post them on the board.

## 4. Interface first (10 minutes, branch `kickoff-schnittstelle`)

Define what everyone builds on:

- `api/app/modelle.py`: Pydantic models `Position` (oz, kurztext, langtext, menge, einheit, ep, gp, typ, titel_pfad), `LV` (name, quelle, positionen, summen), `Finding` (id, oz, kategorie `fehler|risiko|nachtrag`, schwere `kritisch|hoch|mittel|niedrig`, titel, begruendung, vorschlag, quelle `regel|modell`, regel_id, optional euro_wirkung), `Pruefbericht` (lv, findings, kennzahlen)
- `api/app/main.py`: `POST /api/lv/import` (file upload → `LV`), `POST /api/lv/pruefen` (`LV` → `Pruefbericht`), `GET /api/beispiele` (example LVs from `data/`), `GET /health`
- One placeholder module per logic issue with a fixed contract and example data: `api/app/lv/importer.py` (`importiere(dateiname, bytes) -> LV`), `api/app/pruefung/regeln.py` (`pruefe_regeln(lv) -> list[Finding]`), `api/app/pruefung/llm_pruefung.py` (`pruefe_mit_llm(lv) -> list[Finding]`, mock without keys), `api/app/risiko/scoring.py` (`bewerte(lv, findings) -> list[Finding]`), optional `api/app/kalkulation/preise.py`; `main.py` already calls them
- `web/lib/api.ts`: matching types and calls
- `data/beispiel_lv.json`: realistic small LV (about 30 items, 3 sections) with 5 introduced errors; expected findings in `data/beispiel_erwartung.json`
- One test file per module, e.g. `api/tests/test_import_gaeb.py`, `api/tests/test_pruefung_regeln.py`, `api/tests/test_risiko_scoring.py`, `api/tests/test_schnittstelle.py`

For this one-time PR, the integration crew may create files across owner areas; announce them with `@all` beforehand. `cd api && python -m pytest -q`, `cd web && npm run build` and `python -m unittest discover -s tests -v` must pass. Open a PR, merge after green checks, post with `@all`. Only then start follow-up issues.

## 5. Owners and issues (5 minutes)

Confirm `AGENTS.md` section 3 ownership. Use `auftrag-schneiden` to create eight to twelve issues: vertical slices, each with one primary owner, acceptance test, target branch `main`, exactly one model label and an assignee. Include at least:

- @Anatomik5: GAEB XML import (X83/X84) for the selected real LV; then Excel import; then PDF import (text + tables, OCR only if needed)
- @Bartuan3600: fixed rules (arithmetic, totals, OZ, missing quantity/unit, short text ≠ long text, dimensional/unit errors, typos, duplicates); then quantity ratios between related items (“400 chairs / 50 tables”); then batched LLM checks for vague text, contradictions and outdated standards with structured JSON output
- @Secret-Sebi: risk/Nachtrag scoring with signal-word catalogue and item types (provisional, lump sum, hourly, specialist trade); aggregation by material/trade (concrete m³, steel kg) and **top-100 ranking** by euro impact × uncertainty; bidder-question generator; estimator-perspective pitch in `pitch/`
- @Zukipany: upload page with progress; report dashboard (metrics, filtered findings, item detail); PDF/Excel export
- @f89pkdtkhw-lab: LLM access and cost controls (batching, caching), deployment and demo script in `docs/demo.md`, evaluation against `data/testfaelle/rohbau_efh/erwartung.md` (recall, false alarms) in `data/vergleich.md`

Every reference to a future file names its supplying issue as a blocker. Only issues with no open blockers receive `agent-bereit` immediately.

## 6. Start signal

Post with `@all`: the core flow in one sentence, issue numbers per person, open blockers, and: “Process all agent-bereit issues assigned to you; release follow-up issues after their blockers merge.” Report elapsed time and assumptions to the lead.

# Case brief · Challenge A: AI review and estimation assistant for bills of quantities

TUM.ai Construction Hackathon, 20–22 November 2026. **Submission Sunday 12:00**, internal target 11:30. Domain knowledge and team notes: [domain guide](domaene.md).

Architecture draft, issue mapping and later history/what-if loop: [architecture](architektur.md).

## The challenge (translated)

**Problem.** Bills of quantities (LV, English: BoQ) often have several thousand items across many cost groups, with dependencies across trades. Companies lack time and staff to review LVs thoroughly, identify risks and systematically learn from earlier projects. Typical errors include typos, incorrect calculations and missed Nachtrag potential, each with potentially significant financial consequences.

**Goal.** A prototype that analyzes and structures LVs:

1. Automatically import and parse long LVs (PDF, GAEB, Excel)
2. **Error detection comes first:** formal and content gaps such as missing items, unclear descriptions, contradictions and typos
3. Assess risk: flag typical high-risk items, such as vague specifications or unusual quantities
4. Identify Nachtrag potential and likely disputes during construction
5. Optionally suggest unit prices or markups from historical project data

**Dataset:** [Example LVs on Google Drive](https://drive.google.com/drive/folders/1wS4UMVghBL8T5opmZ2UBmBu0kr6U8zIB), locally in `data/datensatz/`.

**Planned milestones** (challenge documents): 1. LV parsing and structured extraction · 2. Error detection and plausibility checks · 3. Risk scoring and Nachtrag detection · 4. Historical project data integration (optional) · 5. What-if analysis, e.g. material prices or execution alternatives.

**Expected result:** web app or assistant with uploads · clear risk/review report · pitch from an estimator's perspective.

## What partners said at the pitch evening

Source: [transcript](quellen/Challenge_A_Beyond_the_Line_Item_Transcription.pdf) (European Hackathon League, Friday 20 November).

- **Dominik, CFO of a Luxembourg construction company (infrastructure).** Bidders have little time; prices come from subcontractor inquiries and experience, combined in estimation software. Awards are usually price-based: **too high loses the job; too low because something was missed means a loss.** Order: **error detection first**, then risk, optionally prices and what-if.
- **Data:** **9 anonymized LVs** (small bridge repairs to major projects), **2 with actual execution data** (actual hours, billed quantities, Nachtrag list). **Confidential: never in public repositories.**
- **Christian, estimator for 10 years (“Excel is my best friend”):**
  - **Quantity ratios:** 400 chairs but only 50 tables signals a problem.
  - **Aggregation:** combine “2 blue, 2 red, 88 green tables”; “concrete is concrete”: total volume across concrete grades instead of manually summing 9,000 items.
  - Detect **duplicates**.
  - **Difficult items:** little detail, specialist trades (audio system: €50,000 or €200,000?), often hidden in small entries.
  - **“The real task is not processing 9,000 items, but finding the 100 most important ones.”**
- **Desired demo:** upload an LV and receive the risk/error report. **Pitch from an estimator's perspective:** how does the tool change bid preparation?

## Product implications (priority)

1. **Errors** with OZ and explanation: arithmetic, missing quantity/unit, short text ≠ long text, typos, dimensional/unit errors, outdated standards.
2. **Cross-item plausibility:** ratios between related items (waterproofing ↔ insulation ↔ membrane, formwork ↔ concrete, concrete ↔ reinforcement kg/m³), duplicates.
3. **Aggregation:** material/trade totals (concrete m³, steel kg, masonry m²) as metric tiles.
4. **Top 100 instead of 9,000:** rank by euro impact × uncertainty; prioritize difficult items (vague, specialist, lump sum, provisional, hourly).
5. **Nachtrag and dispute potential**, turned into **bidder clarification questions**.
6. Optional: EP suggestions from the 2 projects with actual data, material-price what-if.

The [capability list](quellen/Skills%20der%20KI.pdf) also requires the AI to label every estimate and never issue a price without the estimator's approval.

## Test cases

- `data/testfaelle/rohbau_efh/`: sample structural-shell LV for a detached house (40-page PDF), with **25 manually identified real findings** in [erwartung.md](../data/testfaelle/rohbau_efh/erwartung.md). Useful as demo LV and benchmark (recall, false alarms).

## Team decisions

| Decision | Team answer |
| --- | --- |
| Who has which problem? | A construction-company estimator/bid preparer receives an LV (often GAEB) from a client or architect with a few days until submission. They cannot read 3,000 items. |
| How does the partner recognize a good solution? | Finds real errors and risks within minutes that would otherwise be missed, each with item number and explanation; fewer false alarms than hits. |
| First real input | Demo: `data/testfaelle/rohbau_efh/lv_rohbau_efh.pdf` (25 known findings). Format coverage: `data/datensatz/501-24-01_GAEB-XML_sas.x83` (GAEB DA XML 3.1, 296 items); confirm at kickoff |
| Expected verifiable output | Structured item list + review report: findings with OZ, category (error / risk / Nachtrag), severity, explanation, source (rule/model), euro impact where estimable |
| Data, tools, submission requirements | Confidential dataset; LLM exclusively offline mock without keys; submission format to clarify |
| Simplest comparison and metric | **Deliberately introduced errors** in test cases (`data/testfaelle/`): recall and false alarms; manual vs. tool time per LV |
| What do we show live in three minutes? | Upload LV → items → report with real findings, OZ and explanations; no invented counts or euro values. Click shows item and bidder question. |
| Who raises blockers? | Everyone immediately on the board with `@f89pkdtkhw-lab` |

## Dataset contents

44 files, about 25 MB, in `data/datensatz/` (as of Friday 20 November, anonymized with placeholders such as `[FIRMA_096]`):

| Format | Files | Notes |
| --- | --- | --- |
| GAEB DA XML (`.X83`/`.x83`) | 4: `501-24-01_GAEB-XML_sas.x83` (296 items), `[NUMMER_001]_leer.X83` (248), `8209.003_Leistungsverzeichnis_leer.X83` (159), `GAEB-[PROJEKT_004].X83` (50) | DA XML 3.1 (`200407`) and 3.2 (`DA83/3.2`) namespaces; long texts contain HTML-like markup |
| GAEB 90 flat file (`.D83`/`.D84`/`.D86`) | 5, including `Angebot AN24-0305.D84` **with prices** and matching `Angebot AN24-0305.pdf` | Fixed 80-character lines, record types `00`–`99`, CP850 encoding |
| PDF | 34, including `LV_00` through `LV_23` by trade, `HEM2301-2_Gesamt-LV.pdf` | Text PDFs from AVA software; check for scans |
| Word | `LV-Positionen.docx` | |

Matching GAEB/PDF pairs (e.g. `GAEB-[PROJEKT_004].X83` + `LV-Ausdruck-[PROJEKT_004].pdf`) can validate PDF import against GAEB import. Priced `.D84`/`.D86` files provide the basis for EP suggestions from “historical” data.

## Core flow (kickoff, 20 November 2026)

```text
Upload (GAEB .x83/.x84/.d83, .xlsx, .pdf)
  → Import: unified model LV → lots/sections → items (OZ, short text, long text, quantity, unit, EP, GP, type)
  → Review engine
       Fixed rules: quantity × EP ≠ GP, section totals, duplicate/gapped OZ, missing unit/quantity,
                    unit/text mismatch (m² vs. m³), quantity outliers, typos
       LLM (initially mock only): vague/unclear long texts, contradictions, missing trade items,
                    provisional items, client-provided work, lump sums, references to unattached drawings
  → Risk and Nachtrag scoring per item (0–100, euro impact)
  → Report: web dashboard + PDF/Excel export + bidder questions
  → Optional: EP suggestion from labor/material/equipment/markups + what-if
```

## Roles and first deliverable

| Person | Focus | First deliverable |
| --- | --- | --- |
| @f89pkdtkhw-lab | Integration, AI access, deployment, demo | Interface + model on `main`, demo starts on presentation laptop |
| @Anatomik5 | Import and parsing | One real GAEB LV imported completely as a JSON item list |
| @Bartuan3600 | Review engine | Five fixed rules with tests producing real findings on the example LV |
| @Zukipany | UI | Upload, item table, filtered findings and detail view |
| @Secret-Sebi | Risk, Nachtrag, estimation, pitch | Risk catalogue (signal words, item types) + seeded-error test cases + estimator-perspective pitch story |

## Open questions

- How and where do we submit (repository link, video, form)? Pitch length and judging criteria?
- Which formats are actually present (GAEB version, Excel layout, scanned PDFs)?
- Are historical prices available for optional EP estimation?
- Which API access and limits are provided?

## Binding kickoff scope (20 November 2026)

Priority: **1. Parsing/import (GAEB X83/X84 → Excel → PDF), 2. fixed error detection, 3. clear review report.** Risk, Nachtrag, prices, what-if and pitch follow the core flow. Domain modules are placeholders; a successful interface call is not yet a domain review.

- First real GAEB import: `data/datensatz/501-24-01_GAEB-XML_sas.x83`, DA XML 3.1, **296 items**, no price fields. Three other X83s use DA XML 3.2: 248, 159 and 50 items. No X84 or Excel in partner files; additionally test both with synthetic fixtures. GAEB 90 D83/D84/D86 comes later; do not claim unsupported formats.
- Target demo and benchmark: `data/testfaelle/rohbau_efh/lv_rohbau_efh.pdf`, 40 pages, 25 manually documented findings in `erwartung.md`. Usable live only after PDF import. Until then, real GAEB import is the first milestone and synthetic JSON is the offline contract demo.
- **Assumption (board round 1, deadline 19:36 CET):** `data/beispiel_lv.json` (30 items, 3 sections, 5 introduced errors) powers the immediately runnable interface; `data/beispiel_erwartung.json` defines acceptance for the fixed-rules follow-up. Placeholders do not yet report those five errors.
- Already decided by the start instruction: LLM remains mock (`pruefe_mit_llm` without keys, network or provider). Default worker Codex; Claude only for `modell:ui` and `modell:schwer`. Live enablement requires a later explicitly authorized task.
- Unknown quantities/prices stay `null`, absent totals `{}`. An unpriced X83 cannot yield a reliable euro risk amount. Model mocks do not count as real hits. Preserve sources and original OZ, including duplicates during import.
- Three-minute scene: choose file → item count and import errors → filter fixed findings by severity → open an item with original text, explanation and action. Publish actual measurements only after the demo/comparison issue.

Ownership in AGENTS.md §3 is confirmed for this scope: @Anatomik5 `api/app/lv/`, @Bartuan3600 `api/app/pruefung/`, @Secret-Sebi `api/app/risiko/` and `pitch/`, @Zukipany `web/`, @f89pkdtkhw-lab integration, AI access, data and documentation. The one-time interface PR jointly defines `api/app/modelle.py`, `main.py`, `web/lib/api.ts`. Follow-up issues change separate domain modules and tests; announce contract changes with @all beforehand.

Schedule: working core flow before optional risk/pitch; feature freeze Sunday 22 November **09:00 Europe/Berlin**, internal acceptance 11:30, submission 12:00. Submission format remains a question for the lead and does not block local product work.

# User stories: the estimator's bid preparation

Broader stories behind the pitch in [pitch-en.md](pitch-en.md). Each epic describes what an estimator needs over a bid week, then lists the stories. Every story states what the demo does today, with evidence in the repository, and what it does not do. A story marked **Not built** is not claimed in the pitch.

Status labels:
- **Works** - runs in the demo on `main` and was checked against the benchmark LV or the synthetic example.
- **Mock** - runs, but the content comes from the offline model mock and is labelled as a demonstration.
- **Not built** - no working path; not claimed.

## Epic 1: Get the bill of quantities into the tool

The estimator receives an LV from a client or architect, often as a GAEB file or a PDF, a few days before the deadline. Getting it in must take seconds and must fail clearly.

- **1.1 Upload a text PDF and see its items.** As an estimator, I drop the PDF of an LV and see how many items the tool found, so that I know the import worked before I read anything. *Works.* Benchmark: 100 items from the 40-page PDF in about 3 s (`data/vergleich.md`). Evidence: `api/app/lv/pdf.py`, `api/tests/test_import_pdf.py`.
- **1.2 Upload a GAEB file.** As an estimator, I upload the X83 or X84 file my client sent, so that I need no manual retyping. *Works* for X83/X84 (`api/app/lv/gaeb.py`). Not demonstrated live in the pitch.
- **1.3 Upload an Excel LV.** As an estimator, I upload my own spreadsheet. *Not built:* the backend answers "Excel XLSX import is not implemented yet" (`api/app/lv/excel.py`). The pitch does not claim it.
- **1.4 Know why a file was refused.** As an estimator, a scanned PDF, an empty file or a file over 10 MiB gets a plain message and a next step. *Works* (`docs/demo.md`, section 4). Scanned PDFs are rejected because there is no OCR.
- **1.5 Use an example when the upload fails.** As an estimator on a bad connection, I still review a complete LV, so that the demo never stops. *Works* as the synthetic example; *plan C* shows a saved report when the backend is down (`web/public/offline/`).

## Epic 2: Find the items that matter

The core promise: finding the 100 most important items among thousands. The estimator must see the most important findings first, not a long list.

- **2.1 See the most important items first.** As an estimator, the report opens with the few items that matter most, so that I start there and not at item 1. *Works* as the "Look at these first" panel (`docs/demo.md`, scene at 0:50).
- **2.2 Filter findings.** As an estimator, I filter by category (error, risk, Nachtrag) and severity, so that I can work through one kind of issue at a time. *Works* (`web/lib/FindingFilter`, `web/components/Pruefbericht.tsx`).
- **2.3 Page through long lists.** As an estimator with a 9,000-item LV, the tables show 50, 100 or 250 rows per page, after filters, so that the browser stays responsive. *Works* (PR #70, `web/lib/seiten.ts`).
- **2.4 Search by item number or text.** As an estimator, I search by OZ or words to jump to an item. *Works* (`web/components/suche/`, PR #50).
- **2.5 Spot duplicates and wrong totals.** As an estimator, a repeated item number or a wrong section total is flagged. *Works* for duplicate OZ, section totals and arithmetic (`api/app/pruefung/regeln.py`).

## Epic 3: Understand every finding

A finding is only useful if the estimator can check it. Each one must say where it came from and how sure the tool is.

- **3.1 See the item and the reason.** As an estimator, each finding shows its OZ, the reason in plain words and a suggested action. *Works* (scene at 1:00 in the pitch).
- **3.2 See the source of a finding.** As an estimator, I see whether a fixed rule or the model produced the finding, so that I weigh it correctly. *Works*: rule findings are labelled "rule"; model entries are labelled "Demonstration" (`web/components/Pruefbericht.tsx`).
- **3.3 Recognise demonstration entries.** As an estimator, the report says that model entries are a mock, so that nobody mistakes them for expert judgement. *Works* ("Demo mode" banner, `kennzahlen.modell_mock`).
- **3.4 Review and comment each finding.** As an estimator, I mark a finding as reviewed, add my comment and export the list, so that the review is documented. *Works* in the browser only: the status and comment are kept on the device and included in the export (commit 449d08c). Not stored on the server.

## Epic 4: Turn risks into questions before bidding

Risks that the client can clarify, such as optional work or hourly work without a budget, become questions sent before the price is submitted.

- **4.1 Get bidder questions from risk findings.** As an estimator, the risk findings become questions for the client, each with its OZ. *Works*: for example OZ 5...3 gives "Under which conditions will this optional work be instructed, and what quantity is expected?" (`web/components/bieterfragen/Bieterfragen.tsx`).
- **4.2 Copy all questions at once.** As an estimator, I copy every question as "OZ – question" lines for my email. *Works* ("Copy all").
- **4.3 Find Nachtrag potential.** As an estimator, I see which items could later become a change order. *Partly works* as risk hints (e.g. `RISK_ZULAGE` on OZ 5...2). The pitch does not claim a Nachtrag amount.

## Epic 5: Quantities and totals

- **5.1 See totals per material or trade.** As an estimator, I see concrete volume or steel weight across items as tiles, so that I can compare with my own experience. *Works* as quantity totals in the report and export (commit 35d6993, `web/lib/Mengensumme`). The pitch does not quote a total.
- **5.2 Spot quantity ratios that do not fit.** As an estimator, 400 chairs with 50 tables is flagged. *Works* for the rule-based ratio check (`api/app/pruefung/mengen.py`). Not shown in the pitch scenes.

## Epic 6: Export and hand over

- **6.1 Export the report.** As an estimator, I export the report as PDF (print) or XLSX for my colleagues. *Works* (`web/app/export/`, `web/lib/export.ts`).
- **6.2 Keep the item reference.** As an estimator, each exported finding still names its OZ, so that a colleague can find the item in the LV. *Works* (same export). Whether the export also prints the source label was not checked; the pitch does not claim it.

## Epic 7: Specifications, history and what-if (not in the pitch)

These stories exist in the product, but the pitch does not show them as evidence.

- **7.1 Enter specification sources.** As an estimator, I record which standard or product sheet applies. *Works* as data entry on `/schritte` (commit cbdfdb0). The check of a standard against its text is not claimed.
- **7.2 Compare with past projects.** As an estimator, I see how a finding compares with earlier projects. *Partly*: history screen and UI API exist (PR #59); the estimates are synthetic. No real history is claimed.
- **7.3 Price suggestions and what-if.** As an estimator, I get price suggestions from history and test alternatives. *Not built as evidence.* Price suggestions remain future options; the tool never issues a price without the estimator's approval (`docs/case.md`).

## Epic 8: Trust, limits and measurement

The partner will trust the tool only if it says what it cannot do.

- **8.1 Show the measured result.** As a partner, I see how many documented findings the tool finds and how many findings match nothing. *Works*: 6 of 25 hits and 18 of 34 unmatched, from `tools/messe_demo.py` (`data/vergleich.md`).
- **8.2 Reproduce the measurement.** As a reviewer, I can rerun the measurement on my laptop, so that I do not depend on the presenter. *Works*: `python3 tools/messe_demo.py`, offline and free.
- **8.3 See known rule limits.** As a reviewer, I see where rules are weak. *Works*: the limits are written in `data/vergleich.md` (for example `TEXT_WIDERSPRUCH` compares only quantity and unit).
- **8.4 No invented money.** As an estimator, I never see a euro value without a basis. *Works*: findings show "unknown" euro impact. *Not built*: any savings calculation. The pitch claims none.
- **8.5 Keep the dataset private.** As the partner, my confidential LVs stay in the private repository. *Works* by policy (`AGENTS.md`, section 5); the demo runs with no keys and no network.

## What the pitch leaves out on purpose

- Excel import (1.3), time savings against manual work (no manual baseline exists), price suggestions (7.3), and any hit rate beyond the one benchmark LV.

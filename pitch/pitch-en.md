# Pitch script: three minutes, plus two minutes of Q&A

Perspective: a cost estimator preparing a bid. Every scene was run on `main` (`953fa5f`, 21 November 2026) against the benchmark LV (`data/testfaelle/rohbau_efh/lv_rohbau_efh.pdf`) in the browser, with the offline model mock. Every number comes from [data/vergleich.md](../data/vergleich.md). The user stories behind these scenes are in [user-stories.md](user-stories.md).

## Timing estimate

- Script: about 350 spoken words. At 140 words per minute that is about 2 min 30 s, plus about 25 s for clicks and the 3 s import: about 2 min 55 s. If the stopwatch run is over 3:00, cut the "[2:20 · Limits]" scene to its first sentence.
- Q&A: about 270 words of prepared answers; each answer is under 20 s.
- **Human speaking rehearsal pending.** This is a word-count estimate, not a stopwatch run. Record the stopwatch time in issue #17 after the first full run with the live demo.

## Click sequence

1. Open `/` (start page, "New evaluation"). Drag `lv_rohbau_efh.pdf` in, press **Evaluate**.
2. Report header: score **9.0 / 10**, price cards show "–" (no prices in this file), counters **Issues 3**.
3. **Show details**. Top of the list: three **ISSUE** rows "Withdrawn standard referenced: DIN 18195-4" (OZ 3...2, 3...4, 3...5). Open **3...2**.
4. Scroll to **Optional work, OZ 5...3** and open it: source "page 14 · line 11", **Open PDF at page 14**, **Suggestion** with the question to the client.
5. Optional, only if ahead of time: **Export report** (PDF or Excel).

## Script (about 2 min 50 s)

**[0:00 · Hook]**
I prepare bids for construction work. A bill of quantities arrives, I have a few days and hundreds or thousands of items. If I miss an error, I lose money after I win the job. If I price too high, I lose the job.

**[0:20 · The real problem]**
At our pitch evening, a partner said it plainly: "The real task is not processing 9,000 items, but finding the 100 most important ones."

**[0:35 · Scene 1: upload]** *(click 1)*
This is a real 40-page PDF: the structural works for a single-family house. I drag it in and press Evaluate. In about three seconds the tool has read 100 items and scored the bill: 9 out of 10, with three issues to fix before I price it.

**[0:55 · Scene 2: what matters first]** *(clicks 2–3)*
The list starts with those three issues, not with 100 rows. Items 3...2, 3...4 and 3...5 still cite DIN 18195, a waterproofing standard withdrawn in 2017. The tool names the replacement family, DIN 18531 to 18535, links the source, and says whether a fixed rule or the model found it. It is a hint, not a legal opinion: a person decides.

**[1:25 · Scene 3: from finding to bidder question]** *(click 4)*
Item 5...3 is optional work, a contingency. The tool shows where it is, page 14, line 11, opens the PDF right there, and turns it into a question for the client: "Under which conditions will this optional work be instructed, and what quantity is expected?" I send that before I submit my price.

**[1:50 · What we measured]**
On this one benchmark we compared against the 25 findings a reviewer listed by hand. The fixed rules alone find 16 of them, and 12 of the 13 the reviewer marked as rule-findable. Only 1 of its 34 counted findings matches nothing on that list. We have not timed a manual review, so I will not claim a time saving.

**[2:20 · Limits, said openly]**
The model part runs as an offline mock here, and the report labels it as a demonstration. This file has no prices, so the price cards show a dash, not a guess.

**[2:35 · Close]**
The result is not a price. It is a short, sourced list of what to check before I bid. If the upload fails, the bundled examples run offline.

## Q&A (two minutes)

**Q1. Is this just a mock?**
In this demo the model review is an offline mock, and the report marks those entries as demonstrations. The 16 hits come from fixed rules and are labelled as such.

**Q2. Does it set our prices?**
No. If you load a price list or the price database has matching prices, it totals the bill and builds an estimated bill next to yours. The benchmark file has no prices, so it shows none. The price stays with the estimator.

**Q3. How do we know it is right?**
On one LV it finds 16 of the 25 hand-listed findings, and 1 of its 34 counted findings matches nothing on that list. That is one document, so it proves nothing about other LVs. The run is in `data/vergleich.md` and can be reproduced with `tools/messe_demo.py`.

**Q4. Why does it miss findings?**
Eight of the nine misses are marked in the hand-written list as model work, for example preamble clauses and missing positions. The model is a mock here, so the offline run cannot find them. The ninth is spelling errors, for which we have no rule.

**Q5. Which files does it read?**
Text PDFs, GAEB XML (X83, X84) and GAEB 90 (D83, D86), Excel and our JSON format. Scanned PDFs are rejected with a clear message, because we do no OCR.

**Q6. Is our data safe?**
The demo runs offline with no API keys. The partner dataset stays in our private repository and is never published. A real LV would go only to the configured model provider, from the server, never from the browser.

## Sources (real files)

- `data/vergleich.md`: all measured numbers (16 of 25 hit, 12 of 13 rule-findable, 1 of 34 findings unmatched, total runtime median 2.70 s). Manual time: not measured.
- `data/testfaelle/rohbau_efh/erwartung.md`: the 25 hand-listed findings and the OZs used in the scenes.
- `docs/case.md`: challenge brief and partner quotes, including the "9,000 items" and "100 most important" wording.
- `docs/demo.md`: startup, offline fallback (plans B and C) and the error messages.
- `api/app/main.py` (`_analyse`): the review, score and price calculation behind the report.
- `api/app/pruefung/`: the fixed rules, e.g. `NORM_ZURUECKGEZOGEN` (withdrawn standard, scene 2), `MASS_EINHEIT_UNPLAUSIBEL`, `FABRIKAT_WIDERSPRUCH`.
- `api/app/risiko/scoring.py`: the risk findings, e.g. `RISK_BEDARF` for optional items behind OZ 5...3 (scene 3).
- `web/components/bericht/Bericht.tsx`: the report (score, price cards, findings list with source location and suggestion).

## Offline fallback

If the upload fails, press one of the example buttons on the start page ("Synthetic structural works BoQ · 30 items" and others); they run offline. If the backend is unreachable, use plan C from [docs/demo.md](../docs/demo.md): "Show offline example report" loads a saved snapshot, and you say aloud that it is a saved report, not a live analysis.

## Open items before the pitch

- Human speaking rehearsal with a stopwatch against the live demo; record the time in issue #17.
- Re-run `tools/messe_demo.py` after the last rule merge and check the numbers above still equal `data/vergleich.md`.

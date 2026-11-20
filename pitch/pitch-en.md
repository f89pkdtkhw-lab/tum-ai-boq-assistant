# Pitch script: three minutes, plus two minutes of Q&A

Draft for issue #17. Perspective: a cost estimator preparing a bid. Numbers marked as placeholders come from `data/vergleich.md` and are filled in after #16 lands. Scenes are taken from the current demo; `docs/demo.md` will confirm them.

## Timing estimate

- Script: about 315 words including stage markers. At about 130 words per minute that is roughly 2 min 25 s, leaving margin for the demo clicks.
- Q&A: about 200 words for five questions, roughly 1 min 30 s at the same pace, within the two-minute budget.
- Stopwatch rehearsal: not yet done. Record the result in issue #17 after #16 is merged.

## Script (about 2 min 25 s)

**[0:00 · Hook]**
I prepare bids for construction work. When a bill of quantities arrives, I have a few days and three thousand items, and nobody can read all of them properly. If I miss an error, I lose money after I win the job. If I price too high, I lose the job.

**[0:25 · The real problem]**
At our partner evening, an estimator with ten years of experience said it plainly: the real task is not processing nine thousand items, but finding the hundred that matter.

**[0:40 · The path, live]**
This is our assistant. I load a structured bill of quantities. Every item becomes a row with its item number, the OZ. The review runs fixed rules first, then the model.

Here is an example from our synthetic test LV, item OZ 02.00.0001. Its quantity is missing. The tool does not treat that as zero. It reports a high-severity finding: the item number, the reason, and a suggested action. That suggestion becomes a bidder question, which I can copy and send to the client before I submit my price.

**[1:50 · What this is not]**
Three limits, stated openly. The model review runs as an offline mock, and the report labels those entries as demonstrations. The example LV is synthetic. The tool does not price anything; where we have no basis for a euro value, it shows none.

**[2:05 · What we measured]**
On our benchmark, a house-building shell LV with 25 findings identified by hand, the tool finds [recall from data/vergleich.md after #16] of them, with [false alarms from data/vergleich.md after #16] false alarms. Manual versus tool time per LV: [from data/vergleich.md after #16].

**[2:25 · Close]**
The result is not a price. It is a shorter list of what to check before I bid. If an upload fails, the same review runs on the bundled example, offline, with no keys.

## Q&A (two minutes)

**Q1. Is this just a mock?**
The review of the model part is a mock today, and the report marks those entries as demonstrations. The rule-based findings come from fixed rules and are labelled as such. Our benchmark numbers are shown separately, with their limits.

**Q2. Does it set our prices?**
No. It flags items and suggests questions. Any price stays with the estimator. We show no euro values without a basis.

**Q3. How do we know it is right?**
We check it against the 25 findings we identified by hand on one test LV. That is one document, so it does not prove the tool works on all LVs. Our measurements are in `data/vergleich.md`.

**Q4. Does it read PDF, GAEB or Excel?**
[Confirm at rehearsal, status after #16.] In this build, GAEB, Excel and PDF import raise "not implemented" errors. The demo loads the structured example LV instead. We will not claim a file format that does not import yet.

**Q5. Is our data safe?**
The demo runs offline with no API keys. The partner dataset stays in our private repository and is never published. A real LV would go only to the configured model provider.

## Sources (real files)

- `docs/case.md`: challenge brief, partner quotes, error priorities. Source of the "100 most important" quote and the "no price without estimator approval" rule.
- `data/testfaelle/rohbau_efh/erwartung.md`: the 25 hand-identified findings used as the benchmark. The PDF itself is `data/testfaelle/rohbau_efh/lv_rohbau_efh.pdf`.
- `data/beispiel_lv.json`: the synthetic example LV. Item OZ 02.00.0001 (missing quantity) comes from the rule engine run on this file. Its bidder question is the rule's suggestion text, not new wording.
- `api/app/pruefung/regeln.py`: the fixed rules, including the missing-quantity rule (`MENGE_FEHLT`).
- `web/components/Pruefbericht.tsx`: report, including the "Demonstration" labels for mock entries.
- `web/components/bieterfragen/Bieterfragen.tsx`: bidder questions and the copy function.
- `README.md`: offline mock, JSON example and `/api/beispiele`.
- `docs/demo.md` and `data/vergleich.md`: do not exist yet (#16). Every number that depends on them is a placeholder.

## Offline fallback

If the upload or network fails, present from the bundled example: load the synthetic LV from the examples (`/api/beispiele`) and show the same report, bidder questions and export. The model part still runs offline as a mock.

## Open items before "finalize"

- Fill the placeholders from `data/vergleich.md` after #16.
- Confirm the demo scenes against `docs/demo.md`.
- Confirm the import status for Q4 at rehearsal.
- Rehearse with a stopwatch and record the result in issue #17.

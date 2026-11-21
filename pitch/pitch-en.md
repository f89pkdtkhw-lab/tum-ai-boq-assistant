# Pitch script: three minutes, plus two minutes of Q&A

Perspective: a cost estimator preparing a bid. Every scene was run on `main` against the benchmark LV (`data/testfaelle/rohbau_efh/lv_rohbau_efh.pdf`) and matches [docs/demo.md](../docs/demo.md). Every number comes from [data/vergleich.md](../data/vergleich.md). The user stories behind these scenes are in [user-stories.md](user-stories.md).

## Timing estimate

- Script: about 380 words including stage markers. At about 130 words per minute that is roughly 2 min 50 s, leaving about 10 s under three minutes.
- Q&A: about 220 words, roughly 1 min 40 s at the same pace.
- Stopwatch rehearsal: not yet done. Record the result in issue #17 before the pitch.

## Script (about 2 min 50 s)

**[0:00 · Hook]**
I prepare bids for construction work. When a bill of quantities arrives, I have a few days and thousands of items, and I cannot read all of them properly. If I miss an error, I lose money after I win the job. If I price too high, I lose the job.

**[0:25 · The real problem]**
At our pitch evening, a partner said it plainly: "The real task is not processing 9,000 items, but finding the 100 most important ones."

**[0:40 · Scene 1: upload]**
This is a real 40-page PDF: the structural works for a single-family house. I drag it in and press Review. In about three seconds the tool has imported 100 items and built a report.

**[1:00 · Scene 2: the important items first]**
The report starts with the items that matter most, not with 100 rows. Each finding names its item number, the OZ, the reason, a suggested action, and whether a fixed rule or the model produced it. Take OZ 9...1: it has no quantity, no unit and no long text. The tool does not treat a missing quantity as zero, and it rates it high.

**[1:25 · Scene 3: from error to bidder question]**
OZ 5...3 is an optional item, a contingency. The tool treats it as a risk and turns it into a question for the client: "Under which conditions will this optional work be instructed, and what quantity is expected?" I copy it and send it before I submit my price.

**[1:50 · Limits, said openly]**
The model part runs as an offline mock, and the report labels it as a demonstration. The tool prices nothing: where we have no basis for a euro value, it shows none.

**[2:05 · What we measured]**
On this one benchmark, the 25 findings a reviewer listed by hand, the tool finds [final recall from data/vergleich.md after the lead's rerun]. [Final false-alarm count from data/vergleich.md after the rerun] of its findings match nothing on that list. We have not timed a manual review, so I will not claim a time saving.

**[2:25 · Close]**
The result is not a price. It is a shorter list of what to check before I bid. If the upload fails, the bundled example runs offline, and the report says it is a saved example.

## Q&A (two minutes)

**Q1. Is this just a mock?**
The model review is a mock today, and the report marks those entries as demonstrations. The rule-based findings come from fixed rules and are labelled as such.

**Q2. Does it set our prices?**
No. It flags items and suggests questions. The price stays with the estimator, and we show no euro values without a basis.

**Q3. How do we know it is right?**
On one LV it finds [final recall from data/vergleich.md after the lead's rerun] of the 25 hand-listed findings, and [final false-alarm count from data/vergleich.md after the rerun] of its findings match nothing on that list. That is one document, so it does not prove the tool works on other LVs. The full run is in `data/vergleich.md` and can be reproduced with `tools/messe_demo.py`.

**Q4. Which files does it read?**
Text PDFs, GAEB X83 and X84, and our JSON format. Scanned PDFs are rejected with a clear message, because we do no OCR. Excel is not implemented yet and returns "not implemented", so we do not claim it.

**Q5. Why does it miss findings?**
Eleven of the 25 entries are marked in the gold list as needing the model or a catalogue. The model is a mock here, so the offline run cannot find them. The other misses are rules we have not written yet, or rules that do not fire on the cited item. The known limits are listed in `data/vergleich.md`.

**Q6. Is our data safe?**
The demo runs offline with no API keys. The partner dataset stays in our private repository and is never published. A real LV would go only to the configured model provider.

## Sources (real files)

- `docs/demo.md`: the three-minute flow, the scenes above, the offline fallback (plans B and C) and the error messages.
- `data/vergleich.md`: all measured numbers. The script's recall and false-alarm figures are placeholders until the lead's rerun is merged (main measured 9 of 25 with 18 false alarms; the file still shows 6 of 25 until updated). Manual time: not measured.
- `data/testfaelle/rohbau_efh/erwartung.md`: the 25 hand-listed findings and the OZs used in the scenes.
- `docs/case.md`: challenge brief and partner quotes, including the "9,000 items" and "100 most important" wording.
- `api/app/main.py` (`pruefen`): the review that builds the report.
- `api/app/pruefung/regeln.py`: the fixed rules (`MENGE_FEHLT`, `EINHEIT_FEHLT`).
- `api/app/risiko/scoring.py`: the risk findings (`RISK_<position type>`, e.g. `RISK_BEDARF` for optional items behind OZ 5...3).
- `web/components/bieterfragen/Bieterfragen.tsx`: the bidder questions and the "Copy all" button.
- `web/components/Pruefbericht.tsx`: the report, including the "Demonstration" labels for mock entries.

## Offline fallback

If the upload or the backend fails, use plan B from [docs/demo.md](../docs/demo.md): press "Review synthetic example", which runs the bundled example offline. If the backend is unreachable, use plan C: "Show offline example report" loads the saved snapshot, and you say aloud that it is a saved report, not a live analysis.

## Open items before the pitch

- Stopwatch rehearsal of the script against the live demo; record the time in issue #17.
- Confirm the scenes still match `docs/demo.md` on the day.

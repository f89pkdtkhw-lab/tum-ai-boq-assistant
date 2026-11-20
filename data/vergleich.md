# Measurement: offline review against the 25 documented findings

One reproducible run of the product path on the structural works LV for a single-family house (`data/testfaelle/rohbau_efh/lv_rohbau_efh.pdf`, 40 pages). The gold standard is the manual list in [erwartung.md](testfaelle/rohbau_efh/erwartung.md); it is unchanged. Numbers below come only from the command in this file. Nothing is rounded up, extrapolated or estimated.

## Reproduce

```sh
# once, from the repository root (see README): .venv with api/requirements.txt installed
.venv/bin/python tools/messe_demo.py            # Markdown report (this file's tables)
.venv/bin/python tools/messe_demo.py --json     # same result as JSON
```

The tool imports the PDF with `app.lv.importer.importiere` and reviews it with `app.main.pruefen`, the functions behind `POST /api/lv/import` and `POST /api/lv/pruefen`. It runs offline and free of charge: the model is the offline mock, no key and no network are used. It runs the pipeline three times (`--runs`), stops if the findings differ between runs, and reports min/median/max time. Measurement logic is tested in `tests/test_messe_demo.py` with a small fixed example containing a false alarm, a missed finding and an excluded `MOCK_` finding.

| | |
| --- | --- |
| Run on | 21 November 2026, Python 3.13.5, `main` at `38decd8` plus the `tools/messe_demo.py` commit of this change (`7752e70`) |
| LV file | `lv_rohbau_efh.pdf`, SHA-256 prefix `959ef674843a484d` |
| Gold file | `erwartung.md`, SHA-256 prefix `ed098fba8aa4f274` |
| Repeatability | Three separate invocations (three timing runs each) gave identical hits and findings; only the timing varies |

## Definitions (fixed before the run)

- **Hit:** a gold entry counts as found when at least one finding sits on one of its OZs (or inside the named title) and carries a rule ID that the tool lists for that entry (`ACCEPTED` in `tools/messe_demo.py`, derived from the rule catalogue, not tuned to the result). One hit per gold entry, however many findings support it.
- **Missed:** no such finding. The table says why.
- **False alarm:** a finding that matches no gold entry. The gold list is a manual review, so an unmatched finding can be true but unlisted; it is counted as a false alarm anyway.
- **Excluded:** every finding whose rule ID starts with `MOCK_`. These are model demonstrations, not findings.
- **Generic hit:** the rule covers the position type but not the specific point of the gold entry; counted as a hit and shown separately.

## Result

| Metric | Value |
| --- | --- |
| Gold entries hit | 6 of 25 |
| Gold entries missed | 19 of 25 |
| Hits only by a generic rule (position type, not the specific point) | 1 |
| Entries the gold marks as fixed-rule findable, hit | 5 of 13 |
| Hits by gold category | F 3/11, N 0/2, P 0/4, R 3/8 |
| Findings considered (MOCK_* excluded: 1) | 34 |
| Findings matching a gold entry | 16 |
| False alarms (findings matching no gold entry) | 18 |
| Items imported from the PDF | 100 |
| Runtime, median of 3 runs (min–max) | import 2.87 s, review 0.002 s, total 2.87 s (2.77–2.92 s) |

| # | Cat. | Gold OZ | Finding type | Result | Matched findings (OZ rule) / why missed |
| --- | --- | --- | --- | --- | --- |
| 1 | F | 8...3 | quantity without unit | HIT | 8...3 EINHEIT_FEHLT |
| 2 | F | 9...1 | item without quantity, unit, long text | HIT | 9...1 EINHEIT_FEHLT; 9...1 LANGTEXT_FEHLT; 9...1 MENGE_FEHLT |
| 3 | F | 9...3 | missing quantity/unit (standard citation needs the model) | HIT | 9...3 EINHEIT_FEHLT; 9...3 MENGE_FEHLT |
| 4 | F | 6...39 | short text contradicts long text | missed | rule exists but did not fire on the cited OZ |
| 5 | F | 6...40 | short text contradicts long text | missed | rule exists but did not fire on the cited OZ |
| 6 | F | 5...15, 5...16 | implausible dimension / unit error | missed | no fixed rule implements this finding type |
| 7 | F | 6...21 | typo in exposure classes | missed | no fixed rule implements this finding type |
| 8 | F | 4...3 | contradictory manufacturer (model) | missed | no fixed rule implements this finding type |
| 9 | F | 4...1–4...4 | wrong standard for material (model) | missed | no fixed rule implements this finding type |
| 10 | P | 4...4 | deviating insulation grade | missed | no fixed rule implements this finding type |
| 11 | P | 3...1 / 3...2 / 4...4 / 4...5 | inconsistent layer areas | missed | rule exists but did not fire on the cited OZ |
| 12 | P | 4...2 | implausibly small quantity | missed | rule exists but did not fire on the cited OZ |
| 13 | P | 6...1 / 6...2 | possible double earthing (model) | missed | no fixed rule implements this finding type |
| 14 | R | 3...2, 3...4, 3...5 | withdrawn standard (model/catalogue) | missed | no fixed rule implements this finding type |
| 15 | F | Vorbem. S. 1 | date before tender date (model) | missed | no fixed rule implements this finding type; the gold entry names no item OZ (preamble or general) |
| 16 | R | 5...3, 6...22 | contingency items | HIT | 5...3 RISK_BEDARF; 6...22 RISK_BEDARF |
| 17 | R | Titel 7 | open hourly-wage budget | HIT | 7...1 RISK_STUNDENLOHN; 7...2 RISK_STUNDENLOHN; 7...3 RISK_STUNDENLOHN; 7...4 RISK_STUNDENLOHN; 7...5 RISK_STUNDENLOHN; 7...6 RISK_STUNDENLOHN; 7...7 RISK_STUNDENLOHN |
| 18 | R | 1...1 | lump-sum item with open scope (model for the specifics) | HIT (generic) | 1...1 RISK_PAUSCHAL |
| 19 | N | 6...14 | scope undetermined at bid time (model) | missed | no fixed rule implements this finding type |
| 20 | R | 6...43 | approximate dimensions, interface (model) | missed | no fixed rule implements this finding type |
| 21 | R | Vorbem. S. 2 | deviation from VOB/B in preamble (model) | missed | no fixed rule implements this finding type; the gold entry names no item OZ (preamble or general) |
| 22 | R | Vorbem. S. 3 | fixed prices without price escalation (model) | missed | no fixed rule implements this finding type; the gold entry names no item OZ (preamble or general) |
| 23 | R | Vorbem. S. 3 | risk shift in preamble (model) | missed | no fixed rule implements this finding type; the gold entry names no item OZ (preamble or general) |
| 24 | N | Titel 8 | missing positions (model) | missed | no fixed rule implements this finding type |
| 25 | F | div. | spelling errors | missed | no fixed rule implements this finding type; the gold entry names no item OZ (preamble or general) |

False alarms by rule:

- `EINHEIT_TIPPFEHLER` × 16: 1...3, 1...4, 1...5, 2...3, 2...4, 2...6, 5...13, 5...14, 5...15, 5...16, 6...3, 6...39, 6...43, 6...44, 6...45, 9...2
- `RISK_ZULAGE` × 1: 5...2
- `TEXT_WIDERSPRUCH` × 1: 5...4

## What this says

- The fixed rules find **6 of 25** documented findings and **5 of the 13** that the gold list itself marks as findable by a fixed rule. That is not a 100 % result and is not presented as one.
- **18 of 34** non-mock findings match no gold entry (false alarms by the definition above). 16 of them are `EINHEIT_TIPPFEHLER` (variant unit spellings, a real formal rule that the gold list does not contain).
- **11** of the 19 missed entries are marked in the gold list as needing the model or a catalogue (four of them concern the preamble, which has no item OZ). The model review is an offline mock here, so the tool cannot find them in this setup; this run says nothing about how a live model would do.
- Runtime: import of the 40-page PDF dominates (median 2.9 s); the review itself takes milliseconds. Total median 2.9 s on this machine (one VM, no GPU).

## Why the rule-findable entries were still missed

Verified in the code and the imported items (item numbers and counts only):

- **#4, #5 (short text ≠ long text):** `TEXT_WIDERSPRUCH` only compares *quantity + unit* expressions between short and long text. The contradictions in 6...39 and 6...40 concern designations, not quantities, so the rule does not fire. Its only finding in this LV (5...4) is not in the gold list.
- **#11 (inconsistent floor slab areas):** `MENGE_SCHICHTEN_ABWEICHUNG` searches only the short text (`kurztext`) for the component name ("Bodenplatte"). In this LV the component is named in the long text, so the rule never groups the layers. It also groups per title, while the four areas of #11 lie in titles 3 and 4.
- **#12 (implausibly small quantity):** the item names no component and no rule compares a single quantity against a minimum, so nothing is grouped with it.
- **#6, #7, #10, #25:** no rule exists for dimension/unit plausibility, typos in exposure classes, deviating insulation grades or spelling.

These are findings for the owners of `api/app/pruefung/`; this change does not touch them. After a rule changes, rerun the command and update this file; extend `ACCEPTED` only together with a new rule.

## Limits

- **One LV, one reviewer.** The gold list is a single manual review of one document. It proves nothing about other LVs, and it may miss true findings (which then count as false alarms).
- **Mapping is by OZ and rule ID.** A hit means "the right kind of finding on the right item", not that the explanation text is correct. Entry 3 contains a part (standard citation, typo) that only the model could find; the hit covers the missing quantity/unit part.
- **Model excluded.** `MOCK_LLM` findings are demonstrations and are not counted. The offline run therefore cannot cover the 12 of 25 gold entries that the gold list marks as model or catalogue work (entry 18 is hit only by a generic rule).
- **No manual baseline.** Nobody timed a manual review of this LV, so there is **no manual-versus-tool time comparison**. The tool's runtime is measured; a comparison number would be invented. The pitch must not quote one.
- **No prices, no what-if.** Euro impact stays unknown for every finding, as in the product.
- **Timing is machine-specific.** One virtual machine. Each of the three runs times import plus review of the file already in memory; loading the Python modules is not included. A presentation laptop will differ.
- **PDF import is heuristic.** 100 items were imported; the gold standard names about 95 items (`erwartung.md`). The difference was not analysed, so the hit/miss result also depends on the import quality.

## Numbers the pitch may quote (issue #17)

| Placeholder in `pitch/pitch-en.md` | Value from this run |
| --- | --- |
| recall from `data/vergleich.md` | 6 of 25 documented findings (5 of 13 rule-findable) |
| false alarms from `data/vergleich.md` | 18 of 34 non-mock findings match no documented finding |
| manual versus tool time per LV | not measured; tool total median 2.9 s for import plus review, no manual figure |

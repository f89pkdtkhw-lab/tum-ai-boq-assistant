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
| Run on | 21 November 2026, Python 3.12.0, `main` at `9c83448` plus the `ACCEPTED` update of this change (#89–#92 rule IDs for gold #7, #9, #10, #14) |
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
| Gold entries hit | 14 of 25 |
| Gold entries missed | 11 of 25 |
| Hits only by a generic rule (position type, not the specific point) | 1 |
| Entries the gold marks as fixed-rule findable, hit | 11 of 13 |
| Hits by gold category | F 7/11, N 0/2, P 3/4, R 4/8 |
| Findings considered (MOCK_* excluded: 1) | 31 |
| Findings matching a gold entry | 30 |
| False alarms (findings matching no gold entry) | 1 |
| Items imported from the PDF | 100 |
| Runtime, median of 3 runs (min–max) | import 2.72 s, review 0.020 s, total 2.75 s (2.74–2.80 s) |

| # | Cat. | Gold OZ | Finding type | Result | Matched findings (OZ rule) / why missed |
| --- | --- | --- | --- | --- | --- |
| 1 | F | 8...3 | quantity without unit | HIT | 8...3 EINHEIT_FEHLT |
| 2 | F | 9...1 | item without quantity, unit, long text | HIT | 9...1 EINHEIT_FEHLT; 9...1 LANGTEXT_FEHLT; 9...1 MENGE_FEHLT |
| 3 | F | 9...3 | missing quantity/unit (standard citation needs the model) | HIT | 9...3 EINHEIT_FEHLT; 9...3 MENGE_FEHLT |
| 4 | F | 6...39 | short text contradicts long text | HIT | 6...39 TEXT_WIDERSPRUCH |
| 5 | F | 6...40 | short text contradicts long text | HIT | 6...40 TEXT_WIDERSPRUCH |
| 6 | F | 5...15, 5...16 | implausible dimension / unit error | missed | no fixed rule implements this finding type |
| 7 | F | 6...21 | typo in exposure classes | HIT | 6...21 NORM_KLASSE_UNGUELTIG |
| 8 | F | 4...3 | contradictory manufacturer (model) | missed | no fixed rule implements this finding type |
| 9 | F | 4...1–4...4 | wrong standard for material | HIT | 4...1 NORM_PRODUKTNORM_WIDERSPRUCH; 4...2 NORM_PRODUKTNORM_WIDERSPRUCH; 4...3 NORM_PRODUKTNORM_WIDERSPRUCH; 4...4 NORM_PRODUKTNORM_WIDERSPRUCH |
| 10 | P | 4...4 | deviating insulation grade | HIT | 4...4 BEZEICHNUNG_ABWEICHUNG |
| 11 | P | 3...1 / 3...2 / 4...4 / 4...5 | inconsistent layer areas | HIT | 3...1 MENGE_SCHICHTEN_ABWEICHUNG; 4...4 MENGE_SCHICHTEN_ABWEICHUNG |
| 12 | P | 4...2 | implausibly small quantity | HIT | 4...2 MENGE_SCHICHTEN_ABWEICHUNG |
| 13 | P | 6...1 / 6...2 | possible double earthing (model) | missed | no fixed rule implements this finding type |
| 14 | R | 3...2, 3...4, 3...5 | withdrawn standard (catalogue) | HIT | 3...2 NORM_ZURUECKGEZOGEN; 3...4 NORM_ZURUECKGEZOGEN; 3...5 NORM_ZURUECKGEZOGEN |
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

- `RISK_ZULAGE` × 1: 5...2

## What this says

- The fixed rules find **14 of 25** documented findings and **11 of the 13** that the gold list itself marks as findable by a fixed rule. That is not a 100 % result and is not presented as one.
- **1 of 31** non-mock findings matches no gold entry (false alarm by the definition above): `RISK_ZULAGE` on 5...2. The 16 `EINHEIT_TIPPFEHLER` false alarms of the first run are gone since #89 reports unit spellings only on mixed spellings.
- **9** of the 11 missed entries are marked in the gold list as needing the model (four of them concern the preamble, which has no item OZ). The model review is an offline mock here, so the tool cannot find them in this run.
- Runtime: import of the 40-page PDF dominates (median 2.7 s); the review itself takes about 20 ms. Total median 2.75 s on this machine.

## Change since the first run (6 of 25, 18 false alarms)

Every gain comes from a new or changed rule on `main`; `ACCEPTED` was extended only for the rule IDs those changes introduced:

- **#4, #5:** `TEXT_WIDERSPRUCH` now also compares designations (#73).
- **#11, #12:** `MENGE_SCHICHTEN_ABWEICHUNG` takes the component from the long text and covers small layer areas (#74, #91).
- **#7:** `NORM_KLASSE_UNGUELTIG` (#90). **#9:** `NORM_PRODUKTNORM_WIDERSPRUCH` (#90). **#10:** `BEZEICHNUNG_ABWEICHUNG` (#91). **#14:** `NORM_ZURUECKGEZOGEN` (#92).
- False alarms 18 → 1: `EINHEIT_TIPPFEHLER` no longer fires on single consistent spellings (#89).

## Why the rule-findable entries are still missed

- **#6 (implausible dimension / unit error)** and **#25 (spelling errors):** no rule exists for dimension/unit plausibility or spelling.

After a rule changes, rerun the command and update this file; extend `ACCEPTED` only together with a new rule.

## Limits

- **One LV, one reviewer.** The gold list is a single manual review of one document. It proves nothing about other LVs, and it may miss true findings (which then count as false alarms).
- **Mapping is by OZ and rule ID.** A hit means "the right kind of finding on the right item", not that the explanation text is correct. Entry 3 contains a part (standard citation, typo) that only the model could find; the hit covers the missing quantity/unit part.
- **Model excluded.** `MOCK_LLM` findings are demonstrations and are not counted. The offline run therefore cannot cover the gold entries that the gold list marks as model or catalogue work (entry 18 is hit only by a generic rule).
- **No manual baseline.** Nobody timed a manual review of this LV, so there is **no manual-versus-tool time comparison**. The tool's runtime is measured; a comparison number would be invented. The pitch must not quote one.
- **No prices, no what-if.** Euro impact stays unknown for every finding, as in the product.
- **Timing is machine-specific.** One virtual machine. Each of the three runs times import plus review of the file already in memory; loading the Python modules is not included. A presentation laptop will differ.
- **PDF import is heuristic.** 100 items were imported; the gold standard names about 95 items (`erwartung.md`). The difference was not analysed, so the hit/miss result also depends on the import quality.

## Numbers the pitch may quote (issue #17)

| Placeholder in `pitch/pitch-en.md` | Value from this run |
| --- | --- |
| recall from `data/vergleich.md` | 14 of 25 documented findings (11 of 13 rule-findable) |
| false alarms from `data/vergleich.md` | 1 of 31 non-mock findings matches no documented finding |
| manual versus tool time per LV | not measured; tool total median 2.75 s for import plus review, no manual figure |

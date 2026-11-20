# Historical estimate adjustment (Note 3) and what-if (Note 4)

Issue #20 · domain owner @Secret-Sebi (specified by @Bartuan3600 while he is unavailable) · status: **contract proposal**. Nothing in this document is implemented yet. The executable modules will be assigned as a separate task. This document starts from the boxes "Claude retrieves 10–20 comparable historical cases (or 3) … Note 3" and "… 10–20 arbitrary historical cases (or 3) … Note 4 What if" in [architektur.md](architektur.md). It builds on the source and note contract for Notes 1/2 in [spezifikationen.md](spezifikationen.md).

Synthetic examples and expected results: [data/architektur/schaetzszenarien.json](../data/architektur/schaetzszenarien.json). Contract checks: `api/tests/test_estimation_scenarios.py`.

Boundaries of this contract:

- No changes to `api/app/risiko/`, `api/app/kalkulation/`, `web/`, `Finding`, the report contract (`Pruefbericht`), HTTP routes or the existing `Note`/`HistoryRecord` models in `api/app/ai/step_api.py`.
- No live LLM calls, no internet retrieval and no storage. The history store is #18 (@Anatomik5). This contract consumes the proposed history record from [architektur.md](architektur.md#history-record-proposal-for-confirmation-by-anatomik5) as already accepted by `HistoryRecord`. Case IDs, tags, date and description are kept.
- No partner data. Every case, date, value and description in the example is invented.
- **No universal factor and no model price.** A factor is applied only after the estimator has selected the ratio method. A euro amount appears only for an estimator-approved price. Every Note 3/4 states "Estimate – approval required".

## 1. Inputs

**`position`: the estimate target for one current LV item.**

| Field | Type | Meaning |
| --- | --- | --- |
| `oz` | string | Original OZ of the current item. Opaque, never renumbered. |
| `kurztext`, `title_path` | string, array of string | From the parsed item, for display only. |
| `work_tags` | array of string | Trade or work identity, e.g. `concrete_repair`. Confirmed by a person, or generated tags (#23) that a person accepted. Empty means "no stated work": nothing is comparable. |
| `metric` | string | What is estimated, e.g. `hours`. Matched exactly against `measurement.metric`. |
| `unit` | string | Unit of the estimate, e.g. `h`. Compared after alias normalization (§2). |

The LV quantity unit (`einheit`, e.g. `m2`) is not the estimate unit. Hours per item are estimated in `h`.

**`history`: a list of history records**, shaped as `HistoryRecord` (`case_id`, `date`, `description`, `tags`, `estimated_values`, `real_values`). Each measurement is `{oz, title_path, metric, value, unit}`, and its `oz` belongs to its own case, not to the current LV. Comments and marks from #18 are carried as evidence but are not used for the factor.

**`assumptions`: chosen by the estimator, never by the model.**

| Field | Type | Meaning |
| --- | --- | --- |
| `ratio_method` | `median` \| null | How case ratios are combined. Only `median` is defined. `null` means not selected yet. |
| `selected_by` | `estimator` \| null | Who selected the method. Any other value counts as not approved. |
| `baseline` | `{value, unit, source}` \| null | Current estimate before adjustment, e.g. 50 h from the estimator. |
| `unit_price` | `{value, currency, per_unit, source, approved}` \| null | Optional price per estimate unit. Used only if `source == "estimator"`, `approved == true`, `currency == "EUR"` and `per_unit` is compatible with `position.unit`. |

## 2. `select_cases(position, history, mode, limit) → CaseSelection`

The function is pure and deterministic: no I/O, no clock, no model call. `mode` is `comparable` (Note 3) or `what_if` (Note 4). `limit` is an integer from 3 to 20 (default 20). Any other value gives status `invalid_limit` with an empty selection.

**Per-case check.** Each record is tested in this order. The first reason that applies excludes the case:

| Reason | Condition |
| --- | --- |
| `work_mismatch` | `comparable`: the case `tags` do not contain every `position.work_tags` entry (trimmed, case-insensitive), or `work_tags` is empty. |
| `comparable_case` | `what_if`: the case would qualify as comparable. The what-if pool only holds broader cases, so Notes 3 and 4 never cite the same case. |
| `missing_estimated_value` | No estimated measurement with `position.metric`, or its `value` is null. |
| `ambiguous_measurement` | More than one estimated measurement with that metric, or more than one actual measurement for the same `oz`, `title_path` and metric. The selector never sums or picks one silently. |
| `missing_real_value` | No actual measurement for the same `oz`, `title_path` and metric, or its `value` is null. |
| `incompatible_unit` | The estimated or actual unit is not compatible with `position.unit`. |
| `zero_estimated_value` | The estimated value is 0, so no ratio exists. |
| `negative_value` | The estimated or actual value is negative. |
| `over_limit` | The case qualifies, but `limit` more recent qualifying cases were already selected. |

The null checks for estimated and actual values run after the actual measurement is found, as listed in [the oracle](../api/tests/test_estimation_scenarios.py) (`exclusion_reason`).

**Unit compatibility** is alias normalization only, never conversion: `h` = `Std`, `Std.`, `hour`, `hours`; `d` = `day`, `days`, `Tag`, `Tage`; `m2` = `m²`, `qm`; `m3` = `m³`, `cbm` (case-insensitive). Other units must match exactly after trimming. Hours and days are never converted, because the length of a working day is an assumption.

**Ordering and limit.** Qualifying cases are ordered by `date` descending, ties by `case_id` ascending. The first `limit` cases are selected. Excluded cases use the same order. Every input case appears exactly once, either in `selected` or in `excluded`. This holds for every status except `invalid_limit`.

**Description relevance.** Tags select the cases. The description is kept on every selected case so that a person, or a later model step, can check relevance. That later step may only drop a case with reason `description_mismatch` and model provenance. It never adds a case and never changes values.

**Status** (target 10–20 cases, minimum 3 for a small dataset):

| Status | Condition | Factor allowed |
| --- | --- | --- |
| `sufficient` | 10 or more cases selected | yes |
| `small_dataset` | 3–9 cases selected | yes, flagged `below_target_case_count` |
| `insufficient_cases` | 1–2 cases selected | no; the cases are still listed |
| `no_qualifying_cases` | history supplied, no case qualifies | no |
| `no_history` | empty history | no |
| `invalid_limit` | `limit` outside 3–20 or not an integer | no |

`CaseSelection`:

```json
{
  "mode": "comparable", "oz": "01.001", "limit": 20, "candidate_count": 6,
  "status": "small_dataset", "case_count": 3,
  "selected": [{"case_id": "H1", "date": "2026-10-01", "tags": ["bridge", "concrete_repair"],
                "description": "Synthetic: …", "case_oz": "01.001", "title_path": [],
                "estimated_value": 100, "real_value": 120, "unit": "h", "ratio": 1.2}],
  "excluded": [{"case_id": "W1", "date": "2026-11-10", "reason": "work_mismatch"}],
  "selection_reason": "3 most recent comparable cases of 6: tags include concrete_repair; …"
}
```

`ratio = real_value / estimated_value`, rounded to 4 decimals (half-even, decimal arithmetic).

## 3. `estimate_scenarios(position, cases, assumptions) → Note3 | Note4`

`cases` is one `CaseSelection`. The mode of the selection decides the note: `comparable` gives **Note 3** (`step: historical_adjustment`, id `Note3:<oz>`) and `what_if` gives **Note 4** (`step: what_if`, id `Note4:<oz>`). One call produces one note. The coordinator calls it twice with two selections.

1. **Factor.** Only with status `sufficient` or `small_dataset` and an estimator-selected `median`: the median of the selected case ratios (mean of the two middle values for an even count), rounded to 4 decimals. Otherwise `factor: null`.
2. **Estimate.** `estimated_value = baseline.value × factor`, rounded to 2 decimals. It needs a baseline with a unit compatible with `position.unit`. A missing baseline still reports the factor (`factor_only`).
3. **Euro amount.** `euro_amount = estimated_value × unit_price.value`, rounded to 2 decimals. It is computed only for an approved estimator price (§1). Otherwise `euro_amount: null`. The model never supplies a price.

**Missing evidence** is always listed, in this order: `invalid_limit`, `no_history`, `no_qualifying_cases`, `insufficient_cases`, `below_target_case_count`, `ratio_method_not_selected`, `unsupported_ratio_method`, `ratio_method_not_approved`, `missing_baseline`, `incompatible_baseline_unit`, `missing_price`, `price_not_approved`, `incompatible_price_unit`.

Internal result (`expected_estimate` in the example):

```json
{
  "note_id": "Note3:01.001", "step": "historical_adjustment", "scenario": "comparable", "oz": "01.001",
  "status": "estimated", "case_ids": ["H1", "H2", "H3"], "case_count": 3, "selection_status": "small_dataset",
  "ratio_method": "median", "factor": 1.2, "ratio_range": [1.2, 1.2],
  "base_value": 50, "estimated_value": 60, "unit": "h", "unit_price": null, "euro_amount": null,
  "missing_evidence": ["below_target_case_count", "missing_price"],
  "approval_required": true, "label": "Estimate – approval required"
}
```

`status` is `estimated`, `factor_only` or `no_factor`.

## 4. Projection to the existing `Note`

`POST /api/comparison/steps` and the `Note` model stay unchanged ([comparison-api.md](comparison-api.md)). The result maps onto existing fields:

| Note field | Value |
| --- | --- |
| `id`, `step`, `oz` | `note_id`, `step`, original `oz` |
| `text` | Starts with **"Estimate – approval required."**. It then names the OZ, case count and case IDs, the factor calculation or "no historical factor", the euro amount or "No euro amount", and every missing-evidence code. Note 4 adds "What-if (hypothetical):". |
| `case_ids`, `case_count` | Selected case IDs in selection order and their actual count, even below 3 |
| `selection_reason` | Mode, pool size, tag rule, metric/unit, ordering, limit, excluded counts per reason, status |
| `base_value`, `estimated_value`, `unit` | Baseline, estimate (or null), canonical unit |
| `assumption` | The estimator's choice in words. Note 4 always starts with "Hypothetical:". |
| `uncertainty` | Ratio range and case count, small-dataset flag, "Past ratios do not prove future effort". Note 4 always says "less certain than Note 3". |
| `evidence` | One entry per selected case: `reference_id = case_id`, current `oz`, `source: history`, detail with the case's own OZ, date, expected/actual value, ratio and tags |
| `manual_review`, `approval_required` | always `true` |

`Note` has no euro field. `euro_amount` stays an internal value and appears only in `text`, and only when approved. Adding a field needs a separate announced contract change. `source: model_mock` and `placeholder: true` remain fixed literals of today's `Note`. Changing them for the deterministic implementation is part of #23.

**Note 3 vs Note 4.** Note 3 uses the most recent comparable cases: same work, compatible unit. Note 4 uses the most recent broader cases: same metric and compatible unit, other work. It is an explicitly hypothetical, less certain what-if. Both use the same rules, the same estimator-selected method and their own case IDs.

## 5. Synthetic examples

All scenarios use `position` OZ `01.001`, `work_tags: ["concrete_repair"]`, metric `hours` and unit `h`. The baseline is 50 h unless stated otherwise.

| Scenario | Pool | Result |
| --- | --- | --- |
| `acceptance_note3_comparable` | H1–H3 (100 h → 120 h, concrete repair) plus W1–W3 (other work) | `small_dataset`, 3 cases H1, H2, H3; median 1.2 × 50 h = **60 h**; no euro amount (`missing_price`) |
| `acceptance_note4_what_if` | same pool, `what_if` | W1, W2, W3 (100 h → 140 h); median 1.4 × 50 h = **70 h**; H1–H3 excluded as `comparable_case` |
| `selection_25_cases_limit_20` | C01–C25, limit 20 | `sufficient`, the 20 most recent cases. C07, C10, C13 and C19 share the date at the cut-off, so C19 is 21st by `case_id` and excluded `over_limit` with four others. Median 1.185 × 50 h = 59.25 h |
| three cases | the acceptance scenario | `small_dataset`, `below_target_case_count` is visible |
| `selection_zero_cases` | empty | `no_history`, `case_count: 0`, no factor, no estimate |
| `excluded_values_and_units` | E01–E11 | zero, null and missing estimates, days vs hours, missing actual, other work, two hour estimates in one case and a negative actual are excluded. E08 (`Std`) counts as `h`. Two cases remain: `insufficient_cases`, no factor, both IDs still cited |
| `ratio_method_not_selected` | acceptance | `ratio_method_not_selected`, no factor |
| `price_not_approved` | acceptance, price 85 EUR/h from `model` | 60 h, no euro amount (`price_not_approved`) |
| `approved_price` | acceptance, 80 EUR/h from `estimator`, approved | 60 h, 4800 EUR, approval still required |
| `what_if_missing_baseline` | acceptance, `what_if`, no baseline | `factor_only`: factor 1.4, no hours estimate |

The acceptance pools agree with the existing offline step mock. The selected H or W records, posted to `/api/comparison/steps`, return the same OZ, case IDs, count, baseline, estimate and unit.

## 6. Handoff from Notes 1–4 to the report

1. **Order per OZ.** The coordinator (`api/app/ai/`, #23, @f89pkdtkhw-lab) runs `comparison` → `standards` → `historical_adjustment` → `what_if` and passes earlier notes as `previous_notes`, as today. Notes 1/2 come from [spezifikationen.md](spezifikationen.md) §5.
2. **Independence.** Notes 3/4 do not read, change or reinterpret Notes 1/2. When an OZ has an open Note 1/2 (manual review, conflict or deviation), the report shows a fixed caveat next to Note 3/4: "Estimate does not account for the open specification note". Specification conflicts are not turned into factors.
3. **Report.** Per OZ, the report shows Note 1, Note 2, Note 3 and Note 4, in that order. Note 4 is visually separated and labelled what-if. Each estimate keeps "Estimate – approval required", the case count and missing evidence. Rule-based risk per item (#14, `api/app/risiko/scoring.py`) stays unchanged. Notes 3/4 create no `Finding`, change no severity and add no `euro_wirkung`.
4. **Back to history.** When the estimator approves or rejects an estimate, that is a user mark (#18, #24) with the note ID and case IDs. A model estimate is never written into `estimated_values` or `real_values` of a case. Planned values, actual observations, user marks and model estimates stay separate.
5. **Errors stay visible.** A missing history service stays `history_unavailable` from the step API. Fewer than three cases stays a Note with `case_count` and missing evidence, not a silent omission.

## 7. Follow-ups (not in this issue)

- Implement `select_cases` and `estimate_scenarios` in `api/app/kalkulation/` (owner @Secret-Sebi), against the real #18 history API (`GET /history/records?tags=…`) once it lands.
- Wire them into the step API and the report with #23 (@f89pkdtkhw-lab). Decide there whether `Note.source` gets a deterministic value and whether a euro field is added (announce with `@all`).
- Display the what-if separation and the approval action in the UI with #24 (@Zukipany).
- Two contract choices for the owner to confirm: the what-if pool excludes comparable cases, so Notes 3 and 4 always cite different case IDs; and units are normalized by alias only, never converted.

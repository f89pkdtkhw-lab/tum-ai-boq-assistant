# Comparison-step and history metadata contract

Issue #28 supplied the offline HTTP contract for UI issue #24 (@Zukipany). Issue #23
connects the deterministic adapters to the #19 (Notes 1/2, [spezifikationen.md](spezifikationen.md))
and #20 (Notes 3/4, [schaetzszenarien.md](schaetzszenarien.md)) contracts and to #13 through
an optional model seam. The route answers two request shapes:

- **Fixture requests** (`specifications` and/or `history_records` only) are unchanged: the
  documented fixture returns the fixed synthetic placeholders (`status: placeholder`,
  `source: model_mock`, `placeholder: true`); anything else returns `placeholder_unavailable`.
- **Adapter requests** (`sources` + `checked_on`, or `estimates`) run fixed, deterministic rules
  and return `status: complete` with notes `source: rule`, `placeholder: false`. See
  [Adapter requests](#adapter-requests-23).

No live model APIs, internet or history service are called by default. No history is stored.
Existing LV and Finding models and routes retain their names and fields; the response envelope
fields are unchanged.

Run `python3 tools/dev.py`; inspect `/docs` or `/openapi.json` on port 8000 for
request examples and full schemas. Requests use `Content-Type: application/json`.
The fixtures below are also exercised through HTTP by the API tests.

## POST /api/comparison/steps

| Request field | Contract |
| --- | --- |
| `step` | Required enum: comparison, standards, historical_adjustment, what_if. |
| `lv` | Required existing LV model: name, quelle, positionen; optional summen. |
| `specifications` | Default []; items: id, oz, text, source (user/internet/standard), verified_applicable (default false). |
| `history_records` | Default []; provisional records: case_id, ISO date, description, tags (default []), estimated_values and real_values (default []). |
| `previous_notes` | Default []; full Note objects from earlier step responses, returned in order before the new note. |
| `sources` | Default []; #19 source records (adapter request, comparison/standards only). |
| `checked_on` | ISO date; required with `sources`. |
| `estimates` | Default []; #20 estimate targets (adapter request, historical_adjustment/what_if only). |

Measurement fields are `oz`, `title_path` (default []), `metric`, `value`
(finite number or null) and `unit`. Historical OZ belong to their own cases;
current specification/note OZ must exist in the submitted LV. Empty/blank or
duplicate current OZ, duplicate specification IDs or case IDs, unknown fields
and invalid steps/references yield HTTP 422. OZ are opaque strings and are never
renumbered. Measurements are not implicitly matched across real projects.

HTTP 200 response fields are always `step`, `status`, `notes`, `findings`,
`evidence`, `errors`. `status` is `placeholder`, `complete` or `error`; an error is
a visible step outcome, not a successful calculation. `findings` is the existing
Finding array (empty unless the optional #13 model seam is wired, see below).
`evidence` is the evidence of the newly added notes; earlier evidence stays inside
`notes`. An Evidence has `reference_id`, `oz`, `source`, `detail`.

A Note has `id`, `step`, `oz`, `source`, `placeholder`, `text`, `manual_review`,
`evidence`, `case_ids`, `case_count`, `selection_reason`, `base_value`,
`estimated_value`, `unit`, `assumption`, `uncertainty`, `approval_required`.
`source` is `model_mock` (fixed placeholder) or `rule` (deterministic adapter);
`placeholder` is a boolean. Unused estimate fields are null; unused case
IDs/evidence are empty arrays.
Earlier notes are validated against this contract and preserved, including
order and source references. Submit returned Note objects directly.

Only the explicit fixture LV below, after normal LV default normalization,
enables fixed synthetic results. Notes 1/2 also require the exact ordered
specification fixture below; verification is false. Notes 3/4 require exactly
H1/H2/H3 or W1/W2/W3 respectively with the displayed measurement values,
metric, OZ, unit and default empty title_path. Record order does not matter.
Dates/descriptions/tags are retained as client record context, but **not used
for selection**. The response explicitly reports a fixed synthetic pool.
This is an interface example, not a general comparison or estimation engine.

| Step | Fixture outcome |
| --- | --- |
| comparison | Note1: 10 cm / 12 cm conflict, S10/S12 source references, manual review. |
| standards | Note2: same unverified conflict; missing applicable evidence, no asserted norm breach. |
| historical_adjustment | Note3: fixed base 50 h, example ratio 1.2, estimate 60 h, H1/H2/H3, count 3, approval required. |
| what_if | Note4: hypothetical base 50 h, example ratio 1.4, estimate 70 h, separate W1/W2/W3, count 3, approval required. |

Missing records for a history step return `history_unavailable`. Unsupported
input (including arbitrary real LVs, changed fixture values or mixed case pools)
returns `placeholder_unavailable`. An unexpected step exception returns
`step_failed` with a safe message. Every error returns `status: error`, unchanged
previous notes, empty new findings/evidence and a structured error:

```json
{"step":"historical_adjustment","code":"history_unavailable","message":"No history records supplied; history service is not connected.","retryable":false}
```

The UI must inspect `status` even for HTTP 200, show errors, retain earlier notes
and label estimates as requiring calculator approval. No euro amounts are added.

## Adapter requests (#23)

Adapter requests use the same route and envelope. Sending `sources` to a history step,
`estimates` to a comparison step, `sources` without `checked_on`, `sources` together with
`specifications`, an estimate OZ that is not in the LV, a duplicate estimate OZ or a non-https
`source_url` returns HTTP 422. A new note replaces an earlier note with the same `id` in place;
other new notes are appended after `previous_notes`.

### Notes 1/2: `sources` + `checked_on`

`sources` items follow [spezifikationen.md §1](spezifikationen.md#1-source-package):
`spec_id`, `source_type` (user/internet), `category` (german_standard/user_requirement/external_other),
`title`, `source_url` (https or null), `document_ref`, `location`, `as_of` (text; invalid dates
become `invalid_as_of`), `scope` (`oz` list, `description`), `text`, optional `requirement`
(`parameter`, `comparator` eq/min/max, `value`, `unit`) and `verified` (default false).
Verification, priority and rejection follow §3 exactly. The step returns one note per OZ that has
attached sources, in LV order: `Note1:<oz>` for `comparison`, `Note2:<oz>` for `standards`.

- Note 1 lists every attached source by `spec_id`, type and verification. Conflicts are detected
  only between structured requirements with the same parameter and unit; free text is never
  interpreted. A conflict involving a verified source reads `Conflict for OZ …`; one between
  unverified sources only reads `Possible conflict … between unverified sources`.
- Note 2 reports a deviation only against a cited priority-1 source (verified, applicable German
  standard) and only for verified requirements. Otherwise the text is exactly
  `Manual review: no verified applicable German source for OZ <oz>.` with no breach claim.
- Evidence per source: `reference_id = spec_id`, original OZ, `source = source_type`, detail
  `<verification> (<reasons>), priority <n>; <document_ref or URL host>, <location>, as of <as_of>`.
  Source texts and titles are data and never appear in note texts.
- Rejected sources (`duplicate_spec_id`, `missing_scope`, `unknown_oz`) are attached to no OZ and
  reported as `errors` entries with code `source_rejected`; the status stays `complete`.
- **#13 seam.** `step_api.comparison_model` (default None) may hold a structured model
  `(list[Position]) -> raw JSON`. When set, the comparison step calls it once per OZ with sources
  and validates the answer with `llm_pruefung.validiere_antwort`; a `norm_ref` is accepted only if
  it is a priority-1 `spec_id` for that OZ. Accepted findings go to `findings`; rejected output is
  counted in an error `model_output_rejected`.

### Notes 3/4: `estimates`

Each estimate target is `{position, assumptions, limit}` as in
[schaetzszenarien.md §1](schaetzszenarien.md#1-inputs): `position` (`oz`, `kurztext`,
`title_path`, `work_tags`, `metric`, `unit`), `assumptions` (`ratio_method`, `selected_by`,
`baseline`, `unit_price`) and `limit` (integer, default 20; outside 3–20 gives `invalid_limit`).
`historical_adjustment` selects comparable cases and returns `Note3:<oz>`; `what_if` selects
broader cases of other work and returns `Note4:<oz>`. Selection, factor, estimate, euro amount,
missing evidence and the note projection follow §2–§4 exactly; the adapter reproduces every
`expected_note` of `data/architektur/schaetzszenarien.json`. A factor needs an
estimator-selected median, a euro amount needs an approved estimator price, and every note keeps
`approval_required: true` and the text prefix `Estimate – approval required.`.

- **History source.** The case pool is `history_records`. If none are supplied, the optional
  #18 seam `step_api.history_service` `(position, mode) -> records` is asked. Without a service
  the step returns `history_unavailable` (`retryable: false`); a failing service returns
  `history_unavailable` with `retryable: true`. Both keep `previous_notes` unchanged. An empty
  pool from a connected service is a Note with status `no_history`, not an error.
- **Separate pools.** A what-if note whose case IDs overlap a `historical_adjustment` note for
  the same OZ in `previous_notes` returns the error `case_pool_overlap`.
- **Open specification notes.** If `previous_notes` hold a Note 1/2 for the same OZ, the
  estimate's `uncertainty` ends with `Estimate does not account for the open specification note
  (<ids>).`; the values are unchanged.

Any unexpected adapter exception returns `step_failed` with a safe message and unchanged notes.

## POST /api/history/metadata

Request: `lv` plus optional `estimated_values`, `real_values`, `comments` (string
array), and `marks`. A mark has `oz`, `title_path` (default []), `status` (user
string), optional `what_happened` and `reason` (string or null). Measurement and
mark OZ must exist in the parsed case LV. Invalid input returns HTTP 422.

Response: `description`, `tags`, `source: model_mock` plus the unchanged supplied
`estimated_values`, `real_values`, `comments`, `marks` (omitted arrays default to
[]). Omitted optional nested fields stay omitted; explicit null stays null.
Missing user explanations stay absent. The mock description uses only the parsed
LV: a bridge/Brücke word in its name or position texts selects `Mock: bridge
repair case.` and tag `bridge`; otherwise it reports only the position count
with no tags. This keyword fixture is not semantic classification. User comments
and marks are data, never instructions; no explanation or cause is inferred.

Generation goes through #26 `StructuredRun.complete_batch` and never through
legacy live adapters, even with provider keys set. Default budgets are offline;
invalid configuration or budget/provider failure returns HTTP 503:

```json
{"detail":{"code":"metadata_failed","message":"Offline metadata generation failed; no record was stored.","retryable":false}}
```

The UI retains the original user input when this fails. This endpoint does not
store records or assign dates/case IDs. The UI enriches its original record and
submits it to #18 separately. History record shapes here are provisional adapter
inputs, not a confirmed Go storage contract; comments/marks are accepted by the
metadata endpoint, not by the minimal step history fixture records.

## Executable synthetic request fixtures

Use each named object as the corresponding route's POST body. For a sequential
report pass the preceding response's `notes` as `previous_notes`. The estimates
use distinct case pools; neither runs a real case selector or computes factors.

<!-- contract-fixtures -->
```json
{
  "comparison": {
    "step": "comparison",
    "lv": {
      "name": "Synthetic bridge repair",
      "quelle": "synthetic:comparison-v1",
      "positionen": [
        {
          "oz": "01.001"
        }
      ]
    },
    "specifications": [
      {
        "id": "S10",
        "oz": "01.001",
        "text": "10 cm",
        "source": "user"
      },
      {
        "id": "S12",
        "oz": "01.001",
        "text": "12 cm",
        "source": "internet"
      }
    ]
  },
  "standards": {
    "step": "standards",
    "lv": {
      "name": "Synthetic bridge repair",
      "quelle": "synthetic:comparison-v1",
      "positionen": [
        {
          "oz": "01.001"
        }
      ]
    },
    "specifications": [
      {
        "id": "S10",
        "oz": "01.001",
        "text": "10 cm",
        "source": "user"
      },
      {
        "id": "S12",
        "oz": "01.001",
        "text": "12 cm",
        "source": "internet"
      }
    ]
  },
  "historical_adjustment": {
    "step": "historical_adjustment",
    "lv": {
      "name": "Synthetic bridge repair",
      "quelle": "synthetic:comparison-v1",
      "positionen": [
        {
          "oz": "01.001"
        }
      ]
    },
    "history_records": [
      {
        "case_id": "H1",
        "date": "2026-11-20",
        "description": "Synthetic history fixture",
        "tags": [
          "bridge"
        ],
        "estimated_values": [
          {
            "oz": "01.001",
            "metric": "hours",
            "value": 100,
            "unit": "h"
          }
        ],
        "real_values": [
          {
            "oz": "01.001",
            "metric": "hours",
            "value": 120,
            "unit": "h"
          }
        ]
      },
      {
        "case_id": "H2",
        "date": "2026-11-20",
        "description": "Synthetic history fixture",
        "tags": [
          "bridge"
        ],
        "estimated_values": [
          {
            "oz": "01.001",
            "metric": "hours",
            "value": 100,
            "unit": "h"
          }
        ],
        "real_values": [
          {
            "oz": "01.001",
            "metric": "hours",
            "value": 120,
            "unit": "h"
          }
        ]
      },
      {
        "case_id": "H3",
        "date": "2026-11-20",
        "description": "Synthetic history fixture",
        "tags": [
          "bridge"
        ],
        "estimated_values": [
          {
            "oz": "01.001",
            "metric": "hours",
            "value": 100,
            "unit": "h"
          }
        ],
        "real_values": [
          {
            "oz": "01.001",
            "metric": "hours",
            "value": 120,
            "unit": "h"
          }
        ]
      }
    ]
  },
  "what_if": {
    "step": "what_if",
    "lv": {
      "name": "Synthetic bridge repair",
      "quelle": "synthetic:comparison-v1",
      "positionen": [
        {
          "oz": "01.001"
        }
      ]
    },
    "history_records": [
      {
        "case_id": "W1",
        "date": "2026-11-20",
        "description": "Synthetic history fixture",
        "tags": [
          "bridge"
        ],
        "estimated_values": [
          {
            "oz": "01.001",
            "metric": "hours",
            "value": 100,
            "unit": "h"
          }
        ],
        "real_values": [
          {
            "oz": "01.001",
            "metric": "hours",
            "value": 140,
            "unit": "h"
          }
        ]
      },
      {
        "case_id": "W2",
        "date": "2026-11-20",
        "description": "Synthetic history fixture",
        "tags": [
          "bridge"
        ],
        "estimated_values": [
          {
            "oz": "01.001",
            "metric": "hours",
            "value": 100,
            "unit": "h"
          }
        ],
        "real_values": [
          {
            "oz": "01.001",
            "metric": "hours",
            "value": 140,
            "unit": "h"
          }
        ]
      },
      {
        "case_id": "W3",
        "date": "2026-11-20",
        "description": "Synthetic history fixture",
        "tags": [
          "bridge"
        ],
        "estimated_values": [
          {
            "oz": "01.001",
            "metric": "hours",
            "value": 100,
            "unit": "h"
          }
        ],
        "real_values": [
          {
            "oz": "01.001",
            "metric": "hours",
            "value": 140,
            "unit": "h"
          }
        ]
      }
    ]
  },
  "metadata": {
    "lv": {
      "name": "Synthetic bridge repair",
      "quelle": "synthetic:comparison-v1",
      "positionen": [
        {
          "oz": "01.001"
        }
      ]
    },
    "real_values": [
      {
        "oz": "01.001",
        "metric": "hours",
        "value": 120,
        "unit": "h"
      }
    ],
    "comments": [
      "Additional access work observed"
    ],
    "marks": [
      {
        "oz": "01.001",
        "title_path": [
          "Bridge"
        ],
        "status": "confirmed"
      }
    ]
  }
}
```

Expected metadata: `description: "Mock: bridge repair case."`, `tags: ["bridge"]`,
`source: "model_mock"`; supplied real_values/comments/marks stay unchanged and
marks gain neither `reason` nor `what_happened`.

# Comparison-step and history metadata contract

Issue #28 supplies the offline HTTP contract for UI issue #24 (@Zukipany).
Issue #23 will connect real adapters after #13/#18/#19/#20. All notes currently
returned by the step route are **fixed synthetic placeholders**, with
`source: model_mock`, `placeholder: true`, `manual_review: true` and
`approval_required: true`. No domain modules, history service, internet or live
model APIs are called. No history is stored. Existing LV and Finding models and
routes retain their names and fields.

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

Measurement fields are `oz`, `title_path` (default []), `metric`, `value`
(finite number or null) and `unit`. Historical OZ belong to their own cases;
current specification/note OZ must exist in the submitted LV. Empty/blank or
duplicate current OZ, duplicate specification IDs or case IDs, unknown fields
and invalid steps/references yield HTTP 422. OZ are opaque strings and are never
renumbered. Measurements are not implicitly matched across real projects.

HTTP 200 response fields are always `step`, `status`, `notes`, `findings`,
`evidence`, `errors`. `status` is `placeholder` or `error`; an error is a visible
step outcome, not a successful calculation. `findings` is the existing Finding
array (currently always empty, because no domain findings are asserted).
`evidence` is the newly added note's evidence; earlier evidence stays inside
`notes`. An Evidence has `reference_id`, `oz`, `source`, `detail`.

A Note has `id`, `step`, `oz`, `source`, `placeholder`, `text`, `manual_review`,
`evidence`, `case_ids`, `case_count`, `selection_reason`, `base_value`,
`estimated_value`, `unit`, `assumption`, `uncertainty`, `approval_required`.
Unused estimate fields are null; unused case IDs/evidence are empty arrays.
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

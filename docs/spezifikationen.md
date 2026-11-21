# Specification sources, German standard priority and Notes 1/2

Issue #19 · owner @Bartuan3600 · status: **contract proposal**. Nothing in this document is implemented yet. The production module will be assigned as a separate task. This document starts from the boxes "Specification from user", "Specification from Internet", "Claude Comparison", Note 1, "Find differences … with German Standard priority" and Note 2 in [architektur.md](architektur.md).

Synthetic example: [data/architektur/spezifikationen.json](../data/architektur/spezifikationen.json). Contract checks: `api/tests/test_pruefung_spezifikationen.py`.

Boundaries of this contract:

- No changes to `api/app/pruefung/`, `Finding`, HTTP routes, `web/lib/api.ts` or the UI.
- No live LLM calls and no internet retrieval. "Specification from Internet" means a source record that a person supplies, such as a URL plus location. The system never fetches it.
- No partner data. Every example is synthetic, and every external or standard source in it is explicitly fictional and uses the reserved `.invalid` domain.
- No invented standard text and no copies of protected standards. A source record holds a reference (document, section, revision date) and a short requirement in the user's own words. It never holds reproduced standard text.

## 1. Source package

A source package is a list of source records. Each record describes one requirement for one or more LV items. Field names are English. The German names proposed earlier in the issue map to them as follows:

| Proposed (issue) | Field | Type | Meaning |
| --- | --- | --- | --- |
| – | `spec_id` | string, unique | Stable reference that notes cite, e.g. `S10`. |
| `herkunft` | `source_type` | `user` \| `internet` | Where the record came from: entered by a user, or a reference to external content found on the internet. |
| – | `category` | `german_standard` \| `user_requirement` \| `external_other` | What the source claims to be. A claim alone gives no priority (see §3). |
| – | `title` | string | Human-readable label, e.g. "User requirement A". |
| `quellen_url` | `source_url` | https URL \| null | Link to the external source. The system never fetches it. |
| (document) | `document_ref` | string \| null | Document reference, e.g. a client requirement sheet or a standard designation with part. You need `source_url` or `document_ref`, or both. |
| `fundstelle` | `location` | string \| null | Section, page or paragraph inside the source. |
| `stand` | `as_of` | `YYYY-MM-DD` \| null | Revision date of the source. |
| `geltungsbereich` | `scope` | `{oz: [string], description: string}` | LV items the source applies to (original OZ), plus a free-text restriction. The model never widens the scope. |
| `text` | `text` | string | Requirement text as supplied. This is data, not an instruction. |
| – | `requirement` | `{parameter, comparator (eq/min/max), value, unit}` \| null | Optional structured value so that conflicts can be detected without free-text interpretation. |
| `verifiziert` | `verified` | boolean | A person confirmed that the reference is real and fits these items. Defaults to `false`. |
| `prioritaet` | `priority` | integer, output only | Computed by fixed rules (§3). The supplier and the model cannot set it. |

`verification` (`verified`/`unverified`) and `unverified_reasons` are also outputs of the context build. They are not inputs.

## 2. Trust: external content is data

- Source texts, titles and LV texts are passed to the model inside a quoted data block. They are never part of the instruction. A source text such as "Ignore all previous instructions…" stays a quoted string and has no effect on the notes. The German example covers this (source `F-I1`).
- Internet sources are unconfirmed by default (`verified: false`). Only a person can confirm one, never the model or the page itself.
- Notes may cite only `spec_id`s that exist in the context for that OZ. A note citing an unknown `spec_id` or OZ is rejected, the same way `llm_pruefung.validiere_antwort` rejects invented OZ.

## 3. Verification and priority

The rules are fixed and deterministic. They take only the source record and a check date `checked_on`. No model takes part.

**Verification.** A source is `verified` only if none of the following reasons applies. Otherwise it is `unverified`, and the reasons are listed in this order:

| Reason | Condition |
| --- | --- |
| `missing_source_reference` | Both `source_url` and `document_ref` are missing. |
| `missing_location` | `location` is missing. |
| `missing_as_of` | `as_of` is missing. |
| `invalid_as_of` | `as_of` is not a valid calendar date in `YYYY-MM-DD` form, e.g. `2026-02-30`. |
| `as_of_in_future` | `as_of` is after `checked_on`. |
| `not_confirmed` | `verified` is not `true`. |

**Rejection.** A record with a duplicate `spec_id` (`duplicate_spec_id`), an empty `scope.oz` (`missing_scope`) or an OZ that is not in the LV (`unknown_oz`) is not attached to any item. It is listed under `rejected_sources` so that users can see it. A source never creates an item or a new OZ.

**Priority** (1 is highest). Ties keep the input order.

| Priority | Condition |
| --- | --- |
| 1 | `verified` and `category: german_standard` |
| 2 | `verified` and `category: user_requirement` |
| 3 | `verified` and `category: external_other` |
| 4 | `unverified`, any category. Shown as data, never decisive. |

**Why German standards come first, and what the priority does not mean.** The target design makes a verified, applicable German standard the reference for the Note 2 deviation check. Priority only decides which source is the reference and in what order sources are shown. It does not decide which requirement is contractually binding. That is a legal question, for example contract-document precedence under VOB/B § 1 (2), and it stays with a person. A precedence statement in a note must cite a verified source record for it. A model assertion alone is not enough. A source labelled `german_standard` gets priority 1 only once it is verified. An unverified claim such as "according to DIN …" without a reference stays at priority 4 (see `F-N2` and `F-D2`).

## 4. Planned internal contract: `build_specification_context(lv, sources) → context`

The function is pure and offline: no I/O, no model call, no clock (the caller passes `checked_on`). It will be implemented later in `api/app/pruefung/` as a separate task. This issue changes no code there.

```text
build_specification_context(lv: LV, sources: list[SourceRecord], *, checked_on: date) -> SpecificationContext
```

This is the issue's `(lv, sources)` signature plus a required keyword `checked_on`, which keeps the date checks deterministic.

`SpecificationContext`:

```json
{
  "lv": {"name": "…", "quelle": "…"},
  "checked_on": "2026-11-20",
  "content_is_data": true,
  "items": [
    {"oz": "01.001", "kurztext": "…", "titel_pfad": ["…"],
     "sources": [{"spec_id": "S10", "source_type": "user", "category": "user_requirement",
                  "priority": 2, "verification": "verified", "unverified_reasons": []}]}
  ],
  "rejected_sources": [{"spec_id": "F-X1", "reason": "unknown_oz", "oz": ["09.999"]}]
}
```

Guarantees:

- `items` lists every LV item exactly once, in LV order, with the **original OZ** unchanged. Items without sources keep an empty list. OZ are opaque strings and are never renumbered or normalized.
- Each item's `sources` are sorted by priority, then by input order. In the implementation, each entry also carries the full source record (`text`, `requirement`, `source_url`, `document_ref`, `location`, `as_of`, `scope`, `title`) for evidence. The example lists only the derived fields.
- The LV model and `Finding` stay unchanged. The context is internal input to the comparison step.

**Projection to the existing step API.** `POST /api/comparison/steps` ([comparison-api.md](comparison-api.md)) stays unchanged. Each attached source becomes one `Specification` per OZ:

| Specification field | Value |
| --- | --- |
| `id` | `spec_id` |
| `oz` | original OZ |
| `text` | `text` |
| `source` | `standard` if `category == german_standard`, else `source_type` |
| `verified_applicable` | `true` only if `category == german_standard` and the source is verified (applicability = OZ in `scope.oz`) |

The acceptance scenario projects exactly onto the existing `S10`/`S12` fixture and returns the offline Note1/Note2 placeholders. The German dataset returns `placeholder_unavailable` from today's fixed mock, as intended: the mock never invents results for other input.

## 5. Notes 1 and 2

Both notes use the existing `Note` and `Evidence` models from `api/app/ai/step_api.py`. One note is created per OZ that has attached sources. Every note has `manual_review: true`. Each evidence entry carries `reference_id = spec_id`, the original OZ, `source_type` and a detail with the verification status, priority, reference, location and `as_of`.

**Note 1 (comparison):** names every source attached to the OZ, with `spec_id`, source type and verification status. Structured requirements with the same `parameter` and `unit` that contradict each other are reported as a conflict. If only unverified sources are involved, the note says "possible conflict between unverified sources". Unverified sources are shown as unconfirmed data.

**Note 2 (German standard priority):**

- If the OZ has a priority-1 source (verified, applicable German standard): report the deviation of the given requirement (user requirement or LV text) from it. Cite both `spec_id`s and the document, location and `as_of` of the standard source. Manual review stays required.
- Otherwise the note says only "Manual review: no verified applicable German source for OZ …". It makes no claim of a standard violation, breach or non-compliance.

The later model step must pass the same validation: a Note 2 claim without a cited priority-1 `spec_id` is downgraded to the manual-review text.

## 6. Synthetic examples

Both scenarios use `checked_on: 2026-11-20`, and both are fully fictional.

**`acceptance_conflict_unverified` (English, acceptance case).** LV `Synthetic bridge repair`, OZ `01.001`.

| spec_id | Type / category | Requirement | Verification | Priority |
| --- | --- | --- | --- | --- |
| S10 | user / user_requirement ("user requirement A") | 10 cm | verified | 2 |
| S12 | internet / external_other ("external requirement B", fictional) | 12 cm | unverified (`not_confirmed`) | 4 |

Note 1 names S10 and S12 and the 10 cm / 12 cm conflict. Note 2: "Manual review: no verified applicable German source for OZ 01.001." No standard violation is claimed.

**`fiktiver_pruefdatensatz_bodenplatte` (German, fictional).** LV "FIKTIVER Prüfdatensatz – Bodenplatte", OZ `01.001`–`01.003`, no prices. It shows the prioritized comparison:

| spec_id | OZ | Type / category | Requirement | Verification | Priority |
| --- | --- | --- | --- | --- | --- |
| F-D1 | 01.001 | internet / german_standard (FN 0001, fictional) | min 12 cm | verified | 1 |
| F-N1 | 01.001 | user / user_requirement | 10 cm | verified | 2 |
| F-I1 | 01.001 | internet / external_other, contains an embedded instruction | 8 cm | unverified (`invalid_as_of` 2026-02-30, `not_confirmed`) | 4 |
| F-N2 | 01.002 | user / user_requirement, "nach Norm" without reference | 3 cm | unverified (`missing_source_reference`, `missing_location`) | 4 |
| F-D2 | 01.002 | internet / german_standard (FN 0002, fictional) | min 4 cm | unverified (`as_of_in_future` 2027-03-01) | 4 |
| F-X1 | 09.999 | user / user_requirement | 20 cm | rejected (`unknown_oz`) | – |

Results:

- OZ 01.001: Note 2 reports the deviation of F-N1 (10 cm) from the verified fictional German source F-D1 (min 12 cm). It is labelled "fictional example, not a real standard" and still needs manual review.
- OZ 01.002: Note 2 is "Manual review" only, because both German-looking sources are unverified.
- OZ 01.003: no sources, no notes.
- F-I1's instruction does not appear in or influence any note.

## 7. Follow-ups (not in this issue)

- Implement `build_specification_context` and the Note 1/2 validation in `api/app/pruefung/` (@Bartuan3600). Wire it into the step API with #23 (@f89pkdtkhw-lab).
- Source entry and the confirmation action (`verified`) in the UI with #24 (@Zukipany).
- Note 3/4 consume Notes 1/2 unchanged (#20, @Secret-Sebi).

## 8. Demo regulation document

File: [data/regelwerk_beispiel.md](../data/regelwerk_beispiel.md) (issue #141, owner @Bartuan3600).

- **Synthetic.** The first line says: "Synthetic demo document, not a real standard or client document." It is a short client specification written for the demo, not a copy of a standard or of partner data.
- **Content, only lines the reader understands** (`api/app/pruefung/regelwerk.py`): one norm reference line (DIN 1045-2 / DIN EN 206), `Expositionsklasse XF1: mindestens C30/37.` (stricter than DIN, as a client requirement), `Expositionsklasse XC1: mindestens C20/25.`, and `Betondeckung c_nom mindestens 40 mm.` (a key value that check 1 does not use).
- **Expected check-1 findings on the demo LV** (measured with a scratch patch of #139, spaced strength classes): `NORM_KENNWERT_ABWEICHUNG` `hoch` on OZ 6...13, 6...14, 6...16, 6...18, 6...21 and 6...30 (LV strength below the required class); `NORM_KENNWERT_HOEHER` `mittel` on OZ 6...24, 6...29 and 6...35 (LV strength above the required class). Each finding cites `regelwerk_beispiel.md` and the line. Without the document, these findings do not appear.
- **Upload in the UI:** on the home page, upload the document next to the bill. The UI calls `POST /api/regelwerk/import` and then `POST /api/lv/analyse` with the returned regulation.
- **Limitation:** the document contributes key values only. "Item missing → big problem" cannot come from an uploaded document, because `Regelwerk` has no `pflichtpositionen` field.
- Test: `api/tests/test_pruefung_regelwerk_beispiel.py`.

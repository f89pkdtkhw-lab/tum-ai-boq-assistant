# LV interface v0.2

Authoritative implementation: `api/app/modelle.py`; TypeScript mirror: `web/lib/api.ts`. Ownership is confirmed in `docs/case.md`. Announce route or field changes with @all on board #1 beforehand.

## HTTP

| Route | Input | Success | Error |
| --- | --- | --- | --- |
| `GET /health` | None | `{ok:true, provider:"mock", model:"offline-lv-mock", mock:true, keys:{…false}}` | — |
| `GET /api/beispiele` | None | `{items:[{id,titel,beschreibung,lv}]}` | — |
| `POST /api/lv/import` | multipart/form-data, field `datei`, max. 10 MiB | `LV` | 413 too large; 422 empty/invalid/unknown format; 501 known importer still a placeholder |
| `POST /api/lv/pruefen` | `LV` as application/json | `Pruefbericht` | 422 invalid contract |
| `POST /api/lv/analyse/start` (#165) | body of `/api/lv/analyse`, optional `nur_pruefen:true` (= `/api/lv/pruefen` pipeline) | 202 `{job_id}` at once; the analysis runs in a background thread | 422 invalid contract; 429 too many running jobs |
| `GET /api/lv/analyse/status/{job_id}` (#165) | None | `{job_id, status:"laeuft"\|"fertig"\|"fehler", schritt, schritte_gesamt, prozent, meldung, fertige_schritte:[{schritt,meldung,sekunden}], fehler:[], sekunden, ergebnis:Pruefbericht\|null}` | 404 unknown or expired job |

At kickoff, only JSON imports. X83/X84, XLSX and PDF are explicit placeholders; each assigned format issue replaces only its module. Files are not stored permanently. Error responses contain a readable `detail` string; FastAPI validation errors use the usual list, displayed by the client as a general input error.

`GET /api/beispiele` returns complete typed synthetic LVs, never partner files. `POST /api/ask` remains compatible with the starter page and always returns a mock; the LV pipeline uses no model provider. `/health` reports the product pipeline's actual offline mode, not its key inventory.

## Data and semantics

`Position`: `oz`, `kurztext`, `langtext`, `menge`, `einheit`, `ep`, `gp`, `typ`, `titel_pfad`. `oz` is a nonempty original value: never renumber or remove duplicate OZ. Quantities and prices are JSON numbers or `null`; `null` means unknown and `0` means a known zero. Preserve negatives for review rules. Reject nonfinite numbers. `titel_pfad` contains ordered section names; do not implicitly normalize units. `typ`: `normal|bedarf|alternativ|zulage|pauschal|stundenlohn`; do not invent unknown semantics.

`LV`: `name`, `quelle`, `positionen`, `summen`. `quelle` describes origin (filename/format), not a file URL. `summen` contains only stated section totals, keyed by section path joined with ` / `. Example: `{"01 Erdarbeiten": 1234.5}` (earthworks section). `{}` means no totals supplied. Never invent totals or calculate them from missing prices.

`Finding`: `id`, `oz`, `kategorie` (`fehler|risiko|nachtrag` = error/risk/Nachtrag), `schwere` (`kritisch|hoch|mittel|niedrig` = critical/high/medium/low), `titel`, `begruendung`, `vorschlag`, `quelle` (`regel|modell` = rule/model), `regel_id`, `euro_wirkung` (number or `null`). IDs are unique within a report and stable for identical input; OZ must come from the LV. For multiple affected items, create a finding for each OZ and explain the relationship. Attach LV/section-level findings to an actually affected OZ and explain their scope. Never invent standards or prices. Euro impact requires an evidenced basis; label estimates in the text.

`Pruefbericht`: unchanged input `lv`, `findings`, `kennzahlen` containing `positionen`, `findings`, `kritisch`, `modell_mock`. `findings` counts all displayed entries, including the clearly marked demo mock, without claiming they are real errors. Evaluation excludes `regel_id == "MOCK_LLM"`.

Optional AI step status (#168): `kennzahlen.modell_reason` and `kennzahlen.modell` (#147), and `ki_schritte`: a list of `{schritt, titel, status: "ok"|"mock"|"fehler"|"aus", grund?, modell?}` for the AI steps (`positionspruefung`, `normrecherche`, `evaluation`, `vergleich`, `was_wenn`, …). Steps report through `app.ai.ki_status.melde(...)`; the field is absent when every step ran as the configured mock (no key), so mock reports stay unchanged. `/api/lv/ai-evaluation` may carry an optional `reason` when a configured model did not answer. The UI shows every `mock`/`fehler` step as a notice in the report.

Kickoff example: `data/beispiel_lv.json` (30 items). POST `/api/lv/pruefen` returns those 30 items and one `MOCK_LLM` entry at OZ `01.00.0001`, no confirmed domain findings, `euro_wirkung:null`, `kennzahlen:{positionen:30,findings:1,kritisch:0,modell_mock:true}`. Five expected real rule findings for the follow-up task: `data/beispiel_erwartung.json`.

## Connected domain boundaries

| Module | Contract | Kickoff behavior |
| --- | --- | --- |
| `lv/importer.py` | `importiere(dateiname, inhalt: bytes) -> LV` | Validate JSON, dispatch formats |
| `lv/gaeb.py`, `lv/excel.py`, `lv/pdf.py` | Each: `importiere(dateiname, inhalt: bytes) -> LV` | `NotImplementedError` → HTTP 501 |
| `pruefung/regeln.py` | `pruefe_regeln(lv) -> list[Finding]` | Empty list |
| `pruefung/mengen.py` | `pruefe_mengen(lv) -> list[Finding]` | Empty list |
| `pruefung/llm_pruefung.py` | `pruefe_mit_llm(lv) -> list[Finding]` | Marked offline mock on first actual OZ; empty LV → [] |
| `risiko/scoring.py` | `bewerte(lv, findings) -> list[Finding]` | Preserve existing findings |

`main.py` already calls all boundaries. Every logic task owns a separate test file. Report import errors through `ValueError` with a safe message; parsers must never expose confidential file contents in errors. The fixed rule set uses `RECHENFEHLER`, `EINHEIT_FEHLT`, `MENGE_FEHLT`, `LANGTEXT_FEHLT`, `OZ_DUPLIKAT` for the five synthetic acceptance criteria; additional rules need their own stable IDs.

<!-- BEGIN:nextjs-agent-rules -->

## This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

## UI structure (read before changing the web app)

Target concept: Epic #93 (`workflow-final.drawio`) and the team sketches. The UI is **simple first; more detail only on request**.

### Flow and pages
| Step | Page / component | Notes |
| --- | --- | --- |
| UI 1 upload | `/` → `components/LvUpload.tsx` | One "Upload files" button, list of current files with a role each (bill · regulation document · price list, guessed by `rolleRaten`, editable), "Evaluate". No example/demo buttons in the UI (t255/t259). |
| UI 2–3 run | `LvUpload` → `api.importiere` → `api.pruefen` | The open report and a running job survive page switches (sessionStorage `lv-aktuell-v1`, `lv-eval-sitzung-v1`); the sidebar/top bar links back. |
| UI 4–5 report | `components/bericht/Bericht.tsx` | **Level 1** summary: was · large score ring (segments = the issue/warning/recommendation counts below it) · estimated ±; issues · warnings · recommendations. Every deeper level has a way back (Hide details, Hide price report, floating ↑ Summary). **Level 2** ("Show details"): filter + sort + expandable rows with status/comment. **Level 3** ("Show full estimated price report"): every item was → estimated ± why, then "All analysis tools" (`components/Pruefbericht.tsx`, embedded). The level is remembered per tab (`lv-stufe-v1`). |
| Menu | `components/nav/Nav.tsx` | ≡ drawer: New evaluation · Submit (bill price per unit, final bill) · More (History, Step reports, Export, Tutorial) · Settings · theme ☀/☾. Dashboard and Statistics were removed on purpose (team decision). |
| UI 1 price list | `/einreichen#preise` | Price list → browser price database (`lib/preisliste.ts`) until #99/#111 exist. |
| UI 7 close project | `/einreichen#schluss`, `/history` | `components/history/ProjektAbschluss.tsx`: estimate + final bill → matched by OZ (`lib/abschluss.ts`) → `POST /api/history` + `PATCH`. |
| UI 6 export | `/export` | Excel + print-to-PDF. |

### Where numbers come from (never invent a price, item or standard)
- **Score /10 and counters:** five selectable models (`bewertungsmodell`, default Balanced) in `lib/bewertungsmodell.ts` / `api/app/pruefung/bewertung.py`, constants in `lib/bewertungsmodell-konstanten.json`. Chosen on the upload step and on the assessment view (`BewertungsmodellWahl`), persisted as `lv-bewertungsmodell-v1`. Backend `Pruefbericht.zusammenfassung` is official when it was computed with the same model. Until the backend sends Report 2 ("vergleich") deductions, `lib/einschaetzung.ts` adds the browser's Report 2 preview. Traffic light: Strict green ≥ 8.5 / yellow ≥ 6.5; the other models green ≥ 7.5 / yellow ≥ 5.
- **Estimated bill:** `lib/preisbericht.ts`: price list match → past projects of the same trade (`deviationByTrade`) → unchanged. Replace with the backend's estimated bill (#113/#114) when it exists.
- **Price outliers:** `lib/preise.ts` (Tukey fences on the same short text + unit). **AI evaluation:** `POST /api/lv/ai-evaluation` (configured model; without one an evidence-only fallback).
- **History:** `/api/history` (Next route; mock in `app/api/history/store.ts` until `HISTORY_API_URL` points to the DB service).

### No mock or demo in the UI (t255/t258/t259)
Nothing visible to users may say mock, demo or offer example/demo buttons, toggles, badges or notices — also not in Settings or the developer options. Offline-model placeholder findings (rule IDs `MOCK_*`) are filtered out of every list, count and export. The mock provider stays in code for tests only (`LLM_PROVIDER=mock`). Login: Google + email/password only (`docs/abo.md`).

### Conventions
- Every visible string goes through `t()` (`lib/einstellungen.tsx`, dictionary `lib/i18n.ts`, test keeps placeholders equal). Backend finding texts are translated by patterns in `lib/befundtext.ts`; add a pattern when a rule is new.
- Explanations live in `components/info/Info.tsx` (ⓘ tooltip), not in paragraphs. Prefer a chart over text.
- Icons only from `components/icon/Icon.tsx` (one stroke weight). Colours only from tokens in `app/globals.css` (`--sev-*`, `--button`, `--brand`, …); check light and dark.
- Tables: aligned columns, numbers right-aligned, one line per row, details on click.
- Pure logic in `lib/*.ts` with a `lib/*.test.mjs` (`node --test web/lib/*.test.mjs`); `npx tsc --noEmit` must pass.

### Open UI issues (owner Zukipany)
#102 regulation upload (UI done, backend import #96/#121) · #103 tiles (done) · #104 detail view with Report 1/2/3 (needs report tags from the backend) · #105 real PDF · #106 2-file close (done) · #115 price list (browser DB done, backend #111) · #116 colour comparison (PR #120) · #117 coloured export · #83 norm UI.

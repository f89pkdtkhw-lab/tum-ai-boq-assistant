# Demo guide: three-minute flow, startup, errors and offline fallback

For whoever presents. Everything here was run against `main` on 21 November 2026 (backend and UI started locally, the flow driven in a headless browser). Where something could not be checked from the repository, it says so. Measured numbers are in [data/vergleich.md](../data/vergleich.md); the pitch script is [pitch/pitch-en.md](../pitch/pitch-en.md).

The demo needs no API key and no internet. The review runs fixed rules, quantity plausibility and risk hints, plus an **offline model mock** (`MOCK_LLM`, labelled "Demo mode" in the report). `GET /health` shows `"mock": true`.

## 1. Before the presentation (10 minutes, once)

| Step | Command / action | Expect |
| --- | --- | --- |
| Install | `python3 tools/dev.py --install` (creates `.venv`, installs `api/requirements.txt` and `web/` with `npm ci`) | no error; Python 3.11+, Node 20+ |
| Start | `python3 tools/dev.py` | UI `http://localhost:3000`, backend `http://localhost:8000/health` |
| Health | open `http://localhost:8000/health` | `"ok": true`, `"mock": true` |
| UI badge | open `http://localhost:3000` | top right "mock · offline-lv-mock", not "Backend offline" |
| Rehearse | run the flow below once with the benchmark PDF | import 100 items in about 9 s, 32 entries in the report |
| Fallback | switch the backend off (Ctrl+C the `api` process) and try plan C below | "Show offline example report" appears |

Use the laptop that presents. Start the product **before** the audience arrives. Keep `data/testfaelle/rohbau_efh/lv_rohbau_efh.pdf` in a visible folder so it can be dragged in. The file stays on the laptop (confidential benchmark LV; never upload it to a third-party service).

## 2. The three-minute flow (plan A: real PDF)

Matches the scenes in the pitch. Times are guides.

| Time | Action | What the audience sees | Say |
| --- | --- | --- | --- |
| 0:00 | Open `/`. Drag `lv_rohbau_efh.pdf` into the drop zone, press **Review file**. | Three steps turn green: Upload, Import ("100 Items detected"), Review ("32 Entries in the report"). About 9 s. | "A real 40-page PDF bill of quantities, no preparation." |
| 0:30 | Scroll to the report header and the key figures. | 100 items, 32 entries, "Demo mode" banner, euro impact "unknown". | "The model part is a mock and says so. We show no euro value without a basis." |
| 0:50 | **Look at these first** panel, then the **Findings** filter (category, severity). | The ten most important items first, not 100 rows. | "The partner's problem is finding the 100 items that matter." |
| 1:20 | Open the detail of OZ `9...1` (no quantity, unit or long text) or `8...3` (quantity without unit). | OZ, reason, suggested action, source "rule" (`MENGE_FEHLT`, `EINHEIT_FEHLT`). | "Every finding names its item number and whether a rule or the model produced it." |
| 1:50 | **Bidder questions** panel; use **Copy all**. | Questions derived from risk findings (e.g. hourly-wage items in title 7, contingency items). | "This becomes a question to the client before I submit my price." |
| 2:15 | **Export report** (PDF print or XLSX), or **Step reports** in the navigation. | Printable report; step reports show their synthetic placeholders. | Optional, skip if short on time. |
| 2:30 | Say the limits and the measurement. | Nothing to show; `data/vergleich.md` open in a tab. | "On our one benchmark LV the fixed rules find 14 of 25 documented findings; the rest needs the live model. 1 of the 31 non-mock findings matches none of the 25." (Numbers from `data/vergleich.md`; do not quote others.) |

Do not claim: a hit rate on other LVs, a time saving versus manual work (not measured), euro savings (none computed), or Excel import (`.xlsx` answers "not implemented yet"). Supported on `main`: JSON, GAEB X83/X84, PDF.

## 3. Alternative plans

- **Plan B: synthetic example, no upload.** Press **Review synthetic example**. The backend returns its 30-item example; 6 entries (5 rule findings plus 1 `MOCK_LLM`). This is the pitch scene "OZ 02.00.0001, quantity missing → high severity". Use it if the PDF import misbehaves or the file is not at hand.
- **Plan C: backend unreachable, offline example report.** If the backend is down, **Review synthetic example** (or any upload) fails with "The backend is unreachable." and a **Show offline example report** button. It loads the saved snapshot `web/public/offline/beispiel-bericht.json` for the same synthetic example and labels it "Offline example: saved report, not a live analysis." Say that aloud. It also appears for 5xx errors. Refresh the snapshot after any rule change: start the backend, run `node web/scripts/offline-snapshot.mjs`, commit the changed JSON.
- **Plan D: nothing works.** Show `data/vergleich.md` and the screenshots or screen recording prepared during rehearsal. Do not improvise numbers.

## 4. Error paths (what the audience sees)

Backend messages were verified by posting each case to the running backend; the browser-side checks and the "backend unreachable" case were verified in a headless browser. Failures reached after upload are shown in the progress card with **Try again** and **Choose another file**.

| Input | Result |
| --- | --- |
| `.txt` or other extension | caught in the browser before upload: "“notes.txt” has an unsupported format. Allowed formats: JSON, X83, X84, XLSX, PDF." (the backend would answer 422 "Unsupported format. Allowed: JSON, X83, X84, XLSX, PDF.") |
| empty file | caught in the browser: "The file is empty." (backend: 422 "The uploaded file is empty.") |
| file over 10 MiB | caught in the browser: "The file is … The maximum is 10 MiB. It was not uploaded." (backend: 413 "File is too large (maximum 10 MiB)."). A failed import of a file above 9.5 MiB also gets a hint to use a smaller file (proxy limit). |
| unreadable PDF | 422 "The file is not a readable PDF. Please check the file or upload GAEB or Excel." |
| invalid JSON contract | 422 "Invalid BoQ JSON. Please use the documented BoQ contract." |
| not a GAEB document | 422 "Invalid GAEB root. Expected a GAEB document." |
| `.xlsx` | 501 "Excel XLSX import is not implemented yet. Please use the JSON example for the demo." |
| backend stopped | "Backend offline" badge, "The backend is unreachable.", offline example button (plan C) |

Backend does not start: check `python3 tools/dev.py` output of the `api` lines; most often missing dependencies (`--install`) or port 8000 in use. UI shows a blank page: check the `web` lines, port 3000 in use, Node below 20.

## 5. Deployment configuration (check only; nothing is deployed from this guide)

Publishing and infrastructure changes are made only on a separate instruction of the lead. Facts found in the repository:

- **Backend:** `render.yaml` defines one Render web service `boq-api` (`rootDir: api`, `pip install -r requirements.txt`, `uvicorn app.main:app --host 0.0.0.0 --port $PORT`, health check `/health`). `api/index.py` is the entry point if the backend runs as a Vercel project with root `api/`. The demo needs **no key**: the BoQ pipeline always uses the mock, even if keys are set. Set `WEB_ORIGINS` to the UI origin only if the browser calls the backend directly (the UI normally goes through the proxy below, so no CORS entry is needed).
- **UI:** `web/next.config.mjs` proxies `/backend/*` to `API_URL` (default `http://127.0.0.1:8000`). For a deployment set `API_URL` to the public backend URL in the UI host's environment. `npm run build` must pass (CI job `produkt` checks it).
- **Jury URL:** the workflow `Demo-Stand` moves branch `demo` to the latest green `main`; the comment in `.github/workflows/demo.yml` says the Vercel production deployment follows `demo`. The Vercel project settings themselves are not in the repository and were **not verified**.
- **Open points to confirm in the hosting dashboards (not changed here):** (1) the Python version on Render (CI uses 3.12; `render.yaml` sets none); (2) the upload size limit of the hosting proxy for files near 10 MiB (the 127 KiB demo PDF is far below any limit); (3) the backend cold start on a free instance, which can take longer than the 9 s import; open `/health` a few minutes before presenting.
- **Same code, three states of the demo:** local laptop (`tools/dev.py`), deployed UI plus backend, offline snapshot. Prefer the local laptop for the pitch; use the deployed URL only if it was rehearsed.

## 6. Checklist right before going on stage

1. `python3 tools/dev.py` running, `/health` shows `"mock": true`.
2. PDF imported once in this browser session so the report is visible; **Review again** re-runs the same file.
3. `data/vergleich.md` open in a tab; numbers on the slides equal it.
4. Plan B and C rehearsed; the sentence "this is a saved report, not a live analysis" ready.
5. No keys, no `.env` contents, no confidential file names visible on screen.

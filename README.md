# LV Review Assistant

**TUM.ai Construction Hackathon 2026 · Challenge A**

Before submitting a bid, an estimator needs to know which positions to correct, which quantities to verify, and which ambiguities to raise with the client. Upload a bill of quantities (LV) in GAEB XML, Excel, PDF or structured LV JSON. The assistant extracts the items and brings pricing errors, unusual quantities, standards references and potential Nachträge into one review report. Each finding points to an item number (OZ) and shows the evidence and a suggested next action.

## Quick start

Run this command from the repository root with Python 3.11+ and Node.js 20.9+ (including npm).

```sh
python tools/dev.py --install
```

On a fresh checkout the launcher installs the Python and web dependencies. Open [the app on port 3000](http://localhost:3000). The [API health endpoint](http://localhost:8000/health) shows the backend and model status. Use `python3` if your system has no `python` command.

The app uses the offline mock when no provider key is configured. Fixed rules, quantity checks and findings from the bundled standards register still run. The report labels mock model output. For live Claude review and supported web-backed standards research, create `.env.local` in the repository root, add the following, and restart the app.

```dotenv
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=your-key-here
```

Keep real keys in `.env.local` or environment variables and out of Git. Set `LLM_PROVIDER=mock` to explicitly choose offline mode.

## Jury demo

1. In **New evaluation**, choose **Upload files** and select [workshop-foundation.json](data/demo/workshop-foundation.json). This six-item LV is entirely synthetic and includes a deliberate total price error. Leave its role as **Bill of quantities** and click **Evaluate**.
2. Click **Show details** and open **OZ 01.0010** in the findings list. The arithmetic rule shows that 75 m³ × €24/m³ gives €1,800, while the LV states €1,500. The same item cites ATV DIN 18300 (2012-09) and uses legacy soil classes. Check the register evidence and raise the soil classification with the client.
3. Open **OZ 02.0010**. The primer covers 180 m² while the three related slab layers each cover 120 m². Use the quantity finding to ask whether the primer covers an additional area.
4. Open **OZ 01.0020**. The provisional dewatering is specified “as required.” Use the Nachtrag finding to ask who authorizes pumping, how its duration is measured, and how it will be paid.
5. Scroll back to the score at the top, then choose **Export report**. When a price list or matching database prices are available, open **Price report ›** to inspect the calculated estimate before using it in the bid.

## Architecture

| Stage | What it does |
| --- | --- |
| Import | The Next.js upload UI sends the file to FastAPI. The importer normalizes OZ, descriptions, quantities, units and any supplied prices into a common LV model. |
| Rules and model review | Fixed checks catch arithmetic and structural errors and compare related quantities. The server-side LLM reviews the item text for unclear scope and inconsistencies. |
| Risk and standards | Risk scoring surfaces items that need clarification and potential Nachträge. The bundled standards register provides local checks, with live research available through Claude. |
| Report and estimate | The report combines findings, evidence, and suggested actions. The estimate uses an uploaded price list or available database prices. The estimator reviews the result before bidding. |
| History | When project history is available, compare previous estimates with actuals. At closeout, record final quantities and costs to inform future bids. |

## Team resources

- [Challenge brief](docs/case.md) and [domain guide](docs/domaene.md)
- [Repository workflow](AGENTS.md) and [team board](https://github.com/f89pkdtkhw-lab/tum-ai-boq-assistant/issues/1)

Run the team tooling tests from the repository root with `python -m unittest discover -s tests -v`. Run the API tests from `api/` with `python -m pytest -q`.

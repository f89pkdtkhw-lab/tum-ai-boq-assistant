// Refresh the offline example report (#61) from the running API:
//   python3 tools/dev.py   (or uvicorn on :8000), then: node web/scripts/offline-snapshot.mjs
// API_URL overrides the backend address, as in web/next.config.mjs.
import { writeFile, mkdir } from "node:fs/promises";

const api = (process.env.API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const ziel = new URL("../public/offline/beispiel-bericht.json", import.meta.url);

async function json(antwort) {
  if (!antwort.ok) throw new Error(`${antwort.url} answered ${antwort.status}: ${await antwort.text()}`);
  return antwort.json();
}

const { items } = await json(await fetch(`${api}/api/beispiele`));
if (!items?.length) throw new Error("The API returned no example BoQ.");
const bericht = await json(await fetch(`${api}/api/lv/pruefen`, {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(items[0].lv),
}));
await mkdir(new URL(".", ziel), { recursive: true });
await writeFile(ziel, `${JSON.stringify(bericht, null, 2)}\n`);
console.log(`Wrote ${ziel.pathname}: ${bericht.lv.positionen.length} items, ${bericht.findings.length} findings.`);

// Run: node --test web/lib/analyse-job.test.mjs  (Node >= 23 strips the TypeScript types of analyse-job.ts)
import { test } from "node:test";
import assert from "node:assert/strict";
import { fuehreAnalyseAus, fuehreAnalyseWeiter, jobFehlerText } from "./analyse-job.ts";

const lv = { name: "Synthetic", quelle: "test", positionen: [], summen: {} };
const body = { lv, regelwerk: null, preisliste: null };
const bericht = { lv, findings: [], kennzahlen: { positionen: 0, findings: 0, kritisch: 0, modell_mock: true } };
const stand = (status, schritt, extra = {}) => ({
  job_id: "j1", status, schritt, schritte_gesamt: 8, prozent: schritt * 12, meldung: `Step ${schritt}/8: x`,
  fertige_schritte: [], fehler: [], sekunden: 0, ...extra,
});
const sofort = async () => {};

function fakeApi(staende) {
  const gesehen = [];
  return {
    gesehen,
    starteAnalyse: async (b) => { gesehen.push(["start", b]); return { job_id: "j1" }; },
    analyseStatus: async (id) => {
      gesehen.push(["status", id]);
      const naechster = staende.shift();
      if (naechster instanceof Error) throw naechster;
      return naechster;
    },
  };
}

test("polls until the job is done and reports every status", async () => {
  const api = fakeApi([stand("laeuft", 1), stand("laeuft", 3), stand("fertig", 8, { prozent: 100, ergebnis: bericht })]);
  const gesehen = [];
  const ende = await fuehreAnalyseAus(api, body, { aufStand: (s) => gesehen.push(s.schritt), warte: sofort });
  assert.deepEqual(ende.bericht, bericht);
  assert.deepEqual(gesehen, [1, 3, 8]);
  assert.deepEqual(api.gesehen[0], ["start", body]);
});

test("a failed job throws its own messages", async () => {
  const api = fakeApi([stand("fehler", 3, { fehler: ["The analysis failed: ValueError: x"] })]);
  await assert.rejects(fuehreAnalyseAus(api, body, { warte: sofort }), /ValueError: x/);
  assert.equal(jobFehlerText(stand("fehler", 1, { meldung: "Failed at step 1/8." })), "Failed at step 1/8.");
});

test("start errors pass through unchanged so a 404 can fall back to the sync route", async () => {
  const fehler = Object.assign(new Error("Not Found"), { status: 404 });
  const api = { starteAnalyse: async () => { throw fehler; }, analyseStatus: async () => stand("laeuft", 1) };
  await assert.rejects(fuehreAnalyseAus(api, body, { warte: sofort }), (e) => e === fehler);
});

test("network blips are retried, a lost job (404) is a readable error", async () => {
  const blip = new TypeError("fetch failed");
  const ok = await fuehreAnalyseAus(fakeApi([blip, blip, stand("fertig", 8, { ergebnis: bericht })]), body, { warte: sofort });
  assert.ok(ok.bericht);
  await assert.rejects(fuehreAnalyseAus(fakeApi([blip, blip, blip]), body, { warte: sofort }), (e) => e === blip);
  const weg = Object.assign(new Error("Unknown"), { status: 404 });
  await assert.rejects(fuehreAnalyseAus(fakeApi([weg]), body, { warte: sofort }), /backend restarted/);
});

test("a replaced run stops polling and resolves with null", async () => {
  let aktiv = true;
  const api = fakeApi([stand("laeuft", 1), stand("laeuft", 2)]);
  const ende = await fuehreAnalyseAus(api, body, { warte: async () => { aktiv = false; }, aktiv: () => aktiv });
  assert.equal(ende, null);
  assert.equal(api.gesehen.filter(([art]) => art === "status").length, 1);
});

test("aufStart receives the job id immediately, and fuehreAnalyseWeiter resumes without starting again", async () => {
  const api = fakeApi([stand("laeuft", 2), stand("fertig", 8, { prozent: 100, ergebnis: bericht })]);
  const starts = [];
  await fuehreAnalyseAus(api, body, { aufStart: (id) => starts.push(id), warte: sofort });
  assert.deepEqual(starts, ["j1"]);

  const weiter = fakeApi([stand("laeuft", 4), stand("fertig", 8, { prozent: 100, ergebnis: bericht })]);
  const ende = await fuehreAnalyseWeiter(weiter, "j1", { warte: sofort });
  assert.deepEqual(ende.bericht, bericht);
  assert.equal(weiter.gesehen.some(([art]) => art === "start"), false);
  assert.deepEqual(weiter.gesehen[0], ["status", "j1"]);
});

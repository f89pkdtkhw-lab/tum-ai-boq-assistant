// Run: node --test web/lib/analyse-lauf.test.mjs  (Node >= 23 strips the TypeScript types)
import { test } from "node:test";
import assert from "node:assert/strict";
import { registerHooks } from "node:module";

registerHooks({ resolve(spec, ctx, next) { try { return next(spec, ctx); } catch (e) { if (spec.startsWith(".")) return next(`${spec}.ts`, ctx); throw e; } } });
const { beobachteJob, verfolgeJob, wirdVerfolgt } = await import("./analyse-lauf.ts");

const lv = { name: "Synthetic", quelle: "test", positionen: [], summen: {} };
const bericht = { lv, findings: [], kennzahlen: { positionen: 0, findings: 0, kritisch: 0, modell_mock: true } };
const stand = (status, prozent, extra = {}) => ({
  job_id: "j1", status, schritt: 1, schritte_gesamt: 8, prozent, meldung: `${prozent} %`, fertige_schritte: [], fehler: [], sekunden: 0, ...extra,
});
const sofort = async () => {};
const api = (staende) => ({ aufrufe: 0, async analyseStatus() { this.aufrufe++; const s = staende.shift(); if (s instanceof Error) throw s; return s; } });

test("polls in the background without any page and saves through the hooks", async () => {
  const a = api([stand("laeuft", 12), stand("laeuft", 50), stand("fertig", 100, { ergebnis: bericht })]);
  const prozente = []; let gespeichert = null;
  const ende = await verfolgeJob(a, "j1", { aufStand: (s) => prozente.push(s.prozent), aufFertig: (e) => { gespeichert = e.bericht; } }, { warte: sofort });
  assert.deepEqual(prozente, [12, 50, 100]);
  assert.equal(gespeichert, bericht);
  assert.equal(ende.bericht, bericht);
  assert.equal(wirdVerfolgt("j1"), false);
});

test("a second page joins the running poller instead of polling twice, and gets the live status", async () => {
  let weiter; const tor = new Promise((r) => { weiter = r; });
  let n = 0;
  const a = { async analyseStatus() { n++; if (n === 1) return stand("laeuft", 30); await tor; return stand("fertig", 100, { ergebnis: bericht }); } };
  const erster = verfolgeJob(a, "j2", {}, { warte: sofort });
  await new Promise((r) => setTimeout(r, 0));
  assert.equal(wirdVerfolgt("j2"), true);
  const gesehen = [];
  const ab = beobachteJob("j2", (s) => gesehen.push(s.prozent));
  assert.deepEqual(gesehen, [30]); // last known status at once
  const zweiter = verfolgeJob(a, "j2", { aufFertig: () => assert.fail("hooks of the second call must not run") });
  weiter();
  assert.equal((await zweiter).bericht, bericht);
  assert.equal(await erster, await zweiter);
  assert.deepEqual(gesehen, [30, 100]);
  assert.equal(n, 2);
  ab();
});

test("a lost job reports through aufFehler and the promise", async () => {
  const a = api([Object.assign(new Error("gone"), { status: 404 })]);
  let fehler = null;
  await assert.rejects(verfolgeJob(a, "j3", { aufFehler: (f) => { fehler = f; } }, { warte: sofort }), /lost/);
  assert.match(String(fehler), /lost/);
  assert.equal(beobachteJob("j3", () => {})(), undefined);
});

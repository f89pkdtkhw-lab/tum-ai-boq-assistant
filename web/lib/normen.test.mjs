// Run: node --test web/lib/normen.test.mjs  (Node >= 23 strips the TypeScript types of normen.ts)
import { test } from "node:test";
import assert from "node:assert/strict";
import { filtereNormen, istAnnahme, istNormFinding, quellenUrls } from "./normen.ts";

const f = (regel_id) => ({ regel_id });

test("predicate matches NORM_* rule IDs only", () => {
  assert.equal(istNormFinding(f("NORM_ZURUECKGEZOGEN")), true);
  assert.equal(istNormFinding(f("NORM_BODENKLASSEN")), true);
  for (const id of ["MOCK_LLM", "RECHENFEHLER", "TEXT_WIDERSPRUCH", "norm_klein", ""]) assert.equal(istNormFinding(f(id)), false, id);
});

test("standards filter: off keeps everything, on keeps NORM_* only, no findings gives zero", () => {
  const liste = [f("RECHENFEHLER"), f("NORM_KI_HINWEIS"), f("MOCK_LLM")];
  assert.equal(filtereNormen(liste, false).length, 3);
  assert.deepEqual(filtereNormen(liste, true), [f("NORM_KI_HINWEIS")]);
  assert.equal(filtereNormen([f("RECHENFEHLER")], true).length, 0);
});

test("URL extraction finds an https URL and ignores text without one", () => {
  assert.deepEqual(quellenUrls("Withdrawn, see https://example.org/norm/din-1045?x=1. Please confirm."), ["https://example.org/norm/din-1045?x=1"]);
  assert.deepEqual(quellenUrls("Source: norm register entry (retrieved 2026-11-01)."), []);
  assert.deepEqual(quellenUrls(""), []);
  assert.deepEqual(quellenUrls(null), []);
  assert.deepEqual(quellenUrls("(https://a.example/x) and https://a.example/x"), ["https://a.example/x"]);
});

test("assumption marker: N3 prefix or approval flag", () => {
  assert.equal(istAnnahme({ text: "Assumption – approval required: for 10 m3 (OZ 01.01) C30/37 instead of C25/30 is assumed." }), true);
  assert.equal(istAnnahme({ text: "Plain note", approval_required: true }), true);
  assert.equal(istAnnahme({ text: "Assumption: layers cover the same area." }), false);
  assert.equal(istAnnahme({}), false);
});

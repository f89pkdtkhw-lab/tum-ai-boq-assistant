// Run: node --test web/lib/spezifikationen.test.mjs  (Node >= 23 strips the TypeScript types)
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  FIXTURE_SOURCES, emptySource, sourceStatuses, toSpecifications, unverifiedReasons, updateSource,
} from "./spezifikationen.ts";

const CHECKED_ON = "2026-11-20";
const ok = (over = {}) => ({
  ...emptySource("A"), document_ref: "Sheet", location: "Item 1", as_of: "2026-11-01",
  scope: { oz: ["01.001"], description: "" }, text: "10 cm", verified: true, ...over,
});

test("a complete confirmed record has no reasons", () => {
  assert.deepEqual(unverifiedReasons(ok(), CHECKED_ON), []);
  assert.deepEqual(unverifiedReasons(ok({ document_ref: null, source_url: "https://x.example.invalid" }), CHECKED_ON), []);
});

test("each reason alone, and all of them in the documented order", () => {
  assert.deepEqual(unverifiedReasons(ok({ document_ref: null }), CHECKED_ON), ["missing_source_reference"]);
  assert.deepEqual(unverifiedReasons(ok({ location: " " }), CHECKED_ON), ["missing_location"]);
  assert.deepEqual(unverifiedReasons(ok({ as_of: null }), CHECKED_ON), ["missing_as_of"]);
  assert.deepEqual(unverifiedReasons(ok({ as_of: "2026-02-30" }), CHECKED_ON), ["invalid_as_of"]);
  assert.deepEqual(unverifiedReasons(ok({ as_of: "20.11.2026" }), CHECKED_ON), ["invalid_as_of"]);
  assert.deepEqual(unverifiedReasons(ok({ verified: false }), CHECKED_ON), ["not_confirmed"]);
  assert.deepEqual(unverifiedReasons(ok({ document_ref: null, location: null, as_of: null, verified: false }), CHECKED_ON),
    ["missing_source_reference", "missing_location", "missing_as_of", "not_confirmed"]);
});

test("future as_of is judged against the fixed checked_on, not the clock", () => {
  assert.deepEqual(unverifiedReasons(ok({ as_of: "2027-03-01" }), CHECKED_ON), ["as_of_in_future"]);
  assert.deepEqual(unverifiedReasons(ok({ as_of: CHECKED_ON }), CHECKED_ON), []);
  assert.deepEqual(unverifiedReasons(ok({ as_of: "2027-03-01" }), "2027-03-01"), []);
});

test("priority 1-3 by category when verified, 4 when unverified, none when rejected", () => {
  const records = [
    ok({ spec_id: "D", category: "german_standard" }), ok({ spec_id: "U" }), ok({ spec_id: "E", category: "external_other" }),
    ok({ spec_id: "N", category: "german_standard", verified: false }),
  ];
  assert.deepEqual(sourceStatuses(records, ["01.001"], CHECKED_ON).map((s) => s.priority), [1, 2, 3, 4]);
});

test("rejection: later duplicate id, empty scope, OZ not in the LV", () => {
  const statuses = sourceStatuses([
    ok({ spec_id: "A" }), ok({ spec_id: "A" }), ok({ spec_id: "B", scope: { oz: [], description: "" } }),
    ok({ spec_id: "C", scope: { oz: ["01.001", "09.999"], description: "" } }),
  ], ["01.001"], CHECKED_ON);
  assert.deepEqual(statuses.map((s) => s.rejection), [null, "duplicate_spec_id", "missing_scope", "unknown_oz"]);
  assert.deepEqual(statuses.map((s) => s.priority), [2, null, null, null]);
});

test("the S10/S12 fixture projects exactly onto the documented step specifications", () => {
  const scenario = JSON.parse(readFileSync(new URL("../../data/architektur/spezifikationen.json", import.meta.url)))
    .scenarios.find((s) => s.id === "acceptance_conflict_unverified");
  assert.deepEqual(FIXTURE_SOURCES, scenario.sources);
  const statuses = sourceStatuses(FIXTURE_SOURCES, ["01.001"], scenario.checked_on);
  assert.deepEqual(statuses.map((s) => [s.verification, s.unverified_reasons, s.priority]),
    scenario.expected_context.items[0].sources.map((s) => [s.verification, s.unverified_reasons, s.priority]));
  assert.deepEqual(toSpecifications(FIXTURE_SOURCES, ["01.001"], scenario.checked_on), scenario.step_api_specifications);
});

test("mapping: one entry per scope OZ, standard source, rejected records not sent, priority order per OZ", () => {
  const specs = toSpecifications([
    ok({ spec_id: "U", scope: { oz: ["01.002", "01.001"], description: "" } }),
    ok({ spec_id: "D", category: "german_standard", source_type: "internet", scope: { oz: ["01.001"], description: "" } }),
    ok({ spec_id: "X", scope: { oz: ["09.999"], description: "" } }),
    ok({ spec_id: "N", category: "german_standard", verified: false }),
  ], ["01.001", "01.002"], CHECKED_ON);
  assert.deepEqual(specs.map((s) => [s.oz, s.id, s.source, s.verified_applicable]), [
    ["01.001", "D", "standard", true], ["01.001", "U", "user", false], ["01.001", "N", "standard", false],
    ["01.002", "U", "user", false],
  ]);
});

test("editing a reference field resets the confirmation; other edits and the tick itself do not", () => {
  const record = ok();
  for (const patch of [{ location: "Item 2" }, { source_url: "https://y.example.invalid" }, { document_ref: "Other" },
    { as_of: "2026-11-02" }, { scope: { oz: [], description: "" } }, { scope: { oz: ["01.001"], description: "changed" } }]) {
    assert.equal(updateSource(record, patch).verified, false, JSON.stringify(patch));
  }
  assert.equal(updateSource(record, { location: "Item 1" }).verified, true);
  assert.equal(updateSource(record, { text: "11 cm", title: "T", category: "german_standard" }).verified, true);
  assert.equal(updateSource(ok({ verified: false }), { verified: true }).verified, true);
});

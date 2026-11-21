// Run: node --test web/lib/i18n.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { DE, uebersetze } from "./i18n.ts";

test("German lookup with placeholders, English and unknown keys pass through", () => {
  assert.equal(uebersetze("de", "Page {a} of {b}", { a: 1, b: 3 }), "Seite 1 von 3");
  assert.equal(uebersetze("en", "Page {a} of {b}", { a: 1, b: 3 }), "Page 1 of 3");
  assert.equal(uebersetze("de", "not in the dictionary"), "not in the dictionary");
});

test("every German text keeps the placeholders of its English key", () => {
  const platzhalter = (s) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort().join();
  for (const [en, de] of Object.entries(DE)) assert.equal(platzhalter(de), platzhalter(en), en);
});

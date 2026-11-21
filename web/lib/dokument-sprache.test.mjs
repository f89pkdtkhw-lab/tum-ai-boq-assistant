// Run: node --test web/lib/dokument-sprache.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { glossar, spracheVon } from "./dokument-sprache.ts";

test("German compounds become English construction terms", () => {
  assert.equal(glossar("Betonarbeiten Stahlbetonwand", "en"), "Concrete work Reinforced concrete wall");
  assert.equal(glossar("Fenster Kunststoff 2-flg.", "en"), "Window UPVC 2-leaf.");
  assert.equal(glossar("Dacharbeiten Wärmedämmung Dach", "en"), "Roofing work Thermal insulation Roof");
  assert.equal(glossar("Erdarbeiten Baugrubenaushub", "en"), "Earthworks Building pit excavation");
});

test("unknown words, numbers and units stay untouched", () => {
  assert.equal(glossar("Xyzabc 24 cm C25/30", "en"), "Xyzabc 24 cm C25/30");
});

test("language detection and the reverse direction", () => {
  assert.equal(spracheVon("Stahlbetonwand herstellen"), "de");
  assert.equal(spracheVon("Supply and install reinforced concrete wall"), "en");
  assert.equal(glossar("Concrete work wall", "de"), "Betonarbeiten wand");
});

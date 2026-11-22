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

test("does not start a second /api/uebersetzen request while one is still waiting", async () => {
  const store = new Map();
  const localStorage = {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => { store.set(k, String(v)); },
  };
  globalThis.window = { localStorage };
  globalThis.localStorage = localStorage;

  let calls = 0;
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  const original = globalThis.fetch;
  globalThis.fetch = async (url, init) => {
    assert.match(String(url), /\/api\/uebersetzen$/);
    calls += 1;
    await gate;
    const body = JSON.parse(init.body);
    return new Response(JSON.stringify({ uebersetzungen: body.texte.map((t) => `${t} (en)`) }), {
      status: 200, headers: { "Content-Type": "application/json" },
    });
  };
  try {
    const { inSprache } = await import("./dokument-sprache.ts");
    const text = "Stahlbetonwand herstellen im Keller";
    const glossarText = inSprache(text, "en");
    assert.ok(glossarText.includes("Reinforced concrete wall"));
    await new Promise((r) => setTimeout(r, 300));
    assert.equal(calls, 1);
    inSprache(text, "en");
    inSprache(text, "en");
    await new Promise((r) => setTimeout(r, 300));
    assert.equal(calls, 1, "a remount during the wait must not enqueue a second job");
    release();
    await new Promise((r) => setTimeout(r, 50));
    assert.equal(inSprache(text, "en"), `${text} (en)`);
    assert.equal(calls, 1);
  } finally {
    globalThis.fetch = original;
  }
});

// Run: node --test web/lib/menue.test.mjs  (Node >= 23 strips the TypeScript types)
import { test } from "node:test";
import assert from "node:assert/strict";
import { menueIndex } from "./menue.ts";

test("arrow keys move through the menu and wrap around", () => {
  assert.equal(menueIndex("ArrowDown", 0, 3), 1);
  assert.equal(menueIndex("ArrowDown", 2, 3), 0);
  assert.equal(menueIndex("ArrowUp", 0, 3), 2);
  assert.equal(menueIndex("ArrowUp", 2, 3), 1);
});

test("from the button (no item focused) and Home/End", () => {
  assert.equal(menueIndex("ArrowDown", -1, 3), 0);
  assert.equal(menueIndex("ArrowUp", -1, 3), 2);
  assert.equal(menueIndex("Home", 2, 3), 0);
  assert.equal(menueIndex("End", 0, 3), 2);
});

test("other keys and empty menus are ignored", () => {
  assert.equal(menueIndex("Enter", 1, 3), null);
  assert.equal(menueIndex("ArrowDown", -1, 0), null);
});

import { test } from "node:test";
import assert from "node:assert/strict";
import { EINTRAG_TYPEN, TYP_NAME, eintraegeInTyp, typFuerPreisstufe, typFuerSchwere } from "./bericht-eintraege.ts";

test("finding severity maps to the same issue/warning groups as the report tiles", () => {
  assert.equal(typFuerSchwere("kritisch"), "issue");
  assert.equal(typFuerSchwere("hoch"), "issue");
  assert.equal(typFuerSchwere("mittel"), "warning");
  assert.equal(typFuerSchwere("niedrig"), "warning");
});

test("price outliers use the same colours as the tiles", () => {
  assert.equal(typFuerPreisstufe("rot"), "issue");
  assert.equal(typFuerPreisstufe("gelb"), "warning");
  assert.equal(typFuerPreisstufe("gruen"), null);
});

test("tile labels and typ filter", () => {
  assert.deepEqual([...EINTRAG_TYPEN], ["issue", "warning", "rec"]);
  assert.equal(TYP_NAME.issue, "Issues");
  assert.equal(TYP_NAME.warning, "Warnings");
  assert.equal(TYP_NAME.rec, "Recommendations");
  const liste = [{ typ: "issue" }, { typ: "warning" }, { typ: "issue" }, { typ: "rec" }];
  assert.equal(eintraegeInTyp(liste, "issue").length, 2);
  assert.equal(eintraegeInTyp(liste, "warning").length, 1);
  assert.equal(eintraegeInTyp(liste, "rec").length, 1);
  assert.equal(eintraegeInTyp(liste, null).length, 4);
});

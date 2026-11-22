// Run: node --test web/lib/evaluation-session.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { registerHooks } from "node:module";

registerHooks({ resolve(spec, ctx, next) { try { return next(spec, ctx); } catch (e) { if (spec.startsWith(".")) return next(`${spec}.ts`, ctx); throw e; } } });
const {
  AKTUELL_SCHLUESSEL, MAX_HISTORIE, SITZUNG_SCHLUESSEL,
  archiviereAktuelleEvaluation, evaluationListe, evaluationPfad, fortzusetzenderJob, istNeuerAuftrag,
  ladeBericht, ladeSitzung, leseSitzung, leereSitzung, setzeAktuelleEvaluation, setzeEvaluationSchritt,
  speichereBericht,
} = await import("./evaluation-session.ts");

function mockStorage() {
  const data = new Map();
  const storage = {
    get length() { return data.size; },
    key(i) { return [...data.keys()][i] ?? null; },
    getItem(k) { return data.has(k) ? data.get(k) : null; },
    setItem(k, v) { data.set(k, String(v)); },
    removeItem(k) { data.delete(k); },
    clear() { data.clear(); },
  };
  globalThis.window = { sessionStorage: storage };
  return storage;
}

test("leseSitzung ignores broken records and caps the history", () => {
  assert.deepEqual(leseSitzung(null), leereSitzung());
  assert.deepEqual(leseSitzung({ aktuell: { id: "x" }, historie: ["nope"] }), leereSitzung());
  const ok = {
    id: "a", jobId: "j1", titel: "Kita Nord", status: "fertig", schritt: "fehler",
    prozent: 100, meldung: "ok", updatedAt: 1,
  };
  const gelesen = leseSitzung({ aktuell: ok, historie: [ok, { id: "b" }, ok, { ...ok, id: "c", titel: "Other" }, { ...ok, id: "c" }] });
  assert.equal(gelesen.aktuell.id, "a");
  assert.deepEqual(gelesen.historie.map((e) => e.id), ["c"]);
});

test("setzeAktuelleEvaluation keeps progress on the same id and archives the previous one", () => {
  mockStorage();
  setzeAktuelleEvaluation({ id: "e1", jobId: "j1", titel: "A", status: "laeuft", prozent: 10, meldung: "step 1" });
  setzeAktuelleEvaluation({ id: "e1", titel: "A", status: "laeuft", prozent: 40, meldung: "step 3" });
  let s = ladeSitzung();
  assert.equal(s.aktuell.jobId, "j1");
  assert.equal(s.aktuell.prozent, 40);
  assert.equal(s.historie.length, 0);
  setzeAktuelleEvaluation({ id: "e2", jobId: "j2", titel: "B", status: "laeuft", schritt: "pruefen" });
  s = ladeSitzung();
  assert.equal(s.aktuell.id, "e2");
  assert.equal(s.historie[0].id, "e1");
  assert.equal(s.historie[0].prozent, 40);
  setzeEvaluationSchritt("marge");
  assert.equal(ladeSitzung().aktuell.schritt, "marge");
});

test("archiviereAktuelleEvaluation moves the current item into the history", () => {
  mockStorage();
  setzeAktuelleEvaluation({ id: "e1", titel: "A", status: "fertig", schritt: "export", prozent: 100, meldung: "" });
  archiviereAktuelleEvaluation();
  const s = ladeSitzung();
  assert.equal(s.aktuell, null);
  assert.equal(s.historie[0].id, "e1");
  assert.deepEqual(evaluationListe(s).map((e) => e.id), ["e1"]);
});

test("history stays capped and evaluationPfad points back into the wizard", () => {
  mockStorage();
  for (let i = 0; i < MAX_HISTORIE + 3; i++) {
    setzeAktuelleEvaluation({ id: `e${i}`, titel: `T${i}`, status: "fertig", schritt: "fehler" });
  }
  const s = ladeSitzung();
  assert.ok(s.historie.length <= MAX_HISTORIE);
  assert.equal(evaluationPfad({ id: "e1", jobId: "abc", status: "laeuft", schritt: "hochladen" }), "/?schritt=pruefen&eval=e1&job=abc");
  assert.equal(evaluationPfad({ id: "e2", jobId: null, status: "fertig", schritt: "marge" }), "/marge?schritt=marge&eval=e2");
  assert.equal(evaluationPfad({ id: "e3", jobId: "z", status: "fertig", schritt: "fehler" }), "/?schritt=fehler&eval=e3&job=z");
  assert.equal(istNeuerAuftrag("?neu=1"), true);
  assert.equal(istNeuerAuftrag("schritt=pruefen"), false);
});

test("reports are stored per evaluation and as the open session report", () => {
  const storage = mockStorage();
  const bericht = { lv: { name: "Kita", quelle: "test", positionen: [], summen: {} }, findings: [] };
  speichereBericht("Kita", null, bericht, "e1");
  assert.equal(ladeBericht("e1").titel, "Kita");
  assert.equal(JSON.parse(storage.getItem(AKTUELL_SCHLUESSEL)).titel, "Kita");
  assert.equal(ladeBericht("missing").titel, "Kita"); // falls back to the open report
  assert.ok(storage.getItem(SITZUNG_SCHLUESSEL) === null || ladeSitzung());
});

test("fortzusetzenderJob resumes running jobs, but opens a finished one from its stored report", () => {
  const e = (id, status) => ({ id, jobId: id, titel: "LV", status, schritt: "pruefen", prozent: null, meldung: "", updatedAt: 1 });
  const gespeichert = (ids) => (id) => ids.includes(id);
  // Running evaluation chip: resume the job from the link.
  assert.equal(fortzusetzenderJob({ aktuell: e("j1", "laeuft"), historie: [] }, "j1", "j1", gespeichert([])), "j1");
  // No link params: resume the current running job of this tab.
  assert.equal(fortzusetzenderJob({ aktuell: e("j1", "laeuft"), historie: [] }, null, null, gespeichert([])), "j1");
  // Finished with a stored report: restore it, even if the backend has lost the job.
  assert.equal(fortzusetzenderJob({ aktuell: e("j1", "fertig"), historie: [] }, "j1", "j1", gespeichert(["j1"])), null);
  assert.equal(fortzusetzenderJob({ aktuell: null, historie: [e("j2", "fertig")] }, "j2", "j2", gespeichert(["j2"])), null);
  // Finished but the report is gone (storage full): ask the backend again.
  assert.equal(fortzusetzenderJob({ aktuell: e("j1", "fertig"), historie: [] }, "j1", "j1", gespeichert([])), "j1");
  // Nothing running and no link: the start page.
  assert.equal(fortzusetzenderJob({ aktuell: e("j1", "fertig"), historie: [] }, null, null, gespeichert(["j1"])), null);
});

// Project-close upload on /history (issue #106, epic #93 D3): our report/estimate + the real final bill → DB record.
import { beilageFehler, importFehlerText, routeFehlt } from "./regelwerk";
import type { LV } from "./api";
import type { Mark, Measurement } from "./history-api";

export const BERICHT_FORMATE = [".json", ".xlsx", ".x83", ".x84", ".pdf"];
export const ABRECHNUNG_FORMATE = [".x84", ".x86", ".xlsx", ".pdf", ".json"];
export const ABSCHLUSS_ROUTE = "/backend/api/db/abschluss";

/** DB record as returned by D1/D3 (`RecordResponse` in db/client.py). */
export type DbRecord = {
  id: number; date: string; description: string; tags: string[];
  expected_json: Record<string, unknown>; actual_json: Record<string, unknown>; note: string;
  warnungen?: string[];
};

export type AbschlussEingabe = { bericht: File | null; abrechnung: File | null; beschreibung: string; tags: string; notiz: string };

/** Errors per file, keyed by field; empty object when the form can be sent. */
export function pruefeAbschluss(e: AbschlussEingabe): Partial<Record<"bericht" | "abrechnung", string>> {
  const fehler: Partial<Record<"bericht" | "abrechnung", string>> = {};
  if (!e.bericht) fehler.bericht = "Choose our report or estimate file.";
  else { const f = beilageFehler(e.bericht, BERICHT_FORMATE, "Report file"); if (f) fehler.bericht = f; }
  if (!e.abrechnung) fehler.abrechnung = "Choose the real final bill.";
  else { const f = beilageFehler(e.abrechnung, ABRECHNUNG_FORMATE, "Final bill"); if (f) fehler.abrechnung = f; }
  return fehler;
}

/** "a, b ,, c" → ["a", "b", "c"]: trimmed, no empties, no duplicates. */
export function tagListe(text: string): string[] {
  return [...new Set(text.split(",").map((t) => t.trim()).filter(Boolean))];
}

/** Multipart body of POST /api/db/abschluss; optional fields only when filled, so the backend generates them. */
export function abschlussForm(e: AbschlussEingabe): FormData {
  const form = new FormData();
  form.append("bericht", e.bericht!);
  form.append("abrechnung", e.abrechnung!);
  if (e.beschreibung.trim()) form.append("description", e.beschreibung.trim());
  const tags = tagListe(e.tags);
  if (tags.length > 0) form.append("tags", tags.join(","));
  if (e.notiz.trim()) form.append("note", e.notiz.trim());
  return form;
}

export type AbschlussFehler = { text: string; routeFehlt: boolean };

/** Readable failure: missing route → keep manual entry; otherwise name the file when the backend does. */
export function abschlussFehler(fehler: unknown, e: AbschlussEingabe): AbschlussFehler {
  if (routeFehlt(fehler)) {
    return { text: "This backend cannot ingest project-close files yet. Please use the manual entry below.", routeFehlt: true };
  }
  const nachricht = fehler instanceof Error ? fehler.message : "";
  const datei = [e.bericht, e.abrechnung].find((d) => d && nachricht.includes(d.name));
  return { text: datei ? nachricht : importFehlerText("Project-close upload", [e.bericht?.name, e.abrechnung?.name].filter(Boolean).join(" + "), fehler), routeFehlt: false };
}

/** Item numbers in both sides, only expected, only actual. Works on the `{oz: {...}}` or `{positionen: [...]}` shapes. */
export function vergleich(r: Pick<DbRecord, "expected_json" | "actual_json">) {
  const ozVon = (j: Record<string, unknown>) => {
    const liste = Array.isArray(j.positionen) ? (j.positionen as { oz?: string }[]).map((p) => p.oz).filter((oz): oz is string => !!oz) : Object.keys(j);
    return new Set(liste);
  };
  const soll = ozVon(r.expected_json);
  const ist = ozVon(r.actual_json);
  return {
    beide: [...soll].filter((oz) => ist.has(oz)).length,
    nurSoll: [...soll].filter((oz) => !ist.has(oz)).length,
    nurIst: [...ist].filter((oz) => !soll.has(oz)).length,
  };
}

// Local close (redesign, ProjektAbschluss.tsx):
// Closing a project (team spec, UI step 7): our estimate and the real final bill become one history case.
// Items are matched by OZ; prices are compared per item and marked "confirmed" (within 10 %) or "deviation".

export type Abschluss = { estimated_values: Measurement[]; real_values: Measurement[]; marks: Mark[]; nurGeschaetzt: string[]; nurReal: string[] };

const TOLERANZ = .1;

/** Reads an uploaded JSON: a review report ({ lv, findings }) or a plain BoQ ({ positionen }). */
export function lvAusJson(daten: unknown): LV | null {
  const d = daten as { lv?: LV; positionen?: unknown };
  if (d && typeof d === "object" && d.lv && Array.isArray(d.lv.positionen)) return d.lv;
  if (d && typeof d === "object" && Array.isArray(d.positionen)) return d as LV;
  return null;
}

export function abschliessen(geschaetzt: LV, real: LV): Abschluss {
  const preis = (p: LV["positionen"][number]) => p.gp ?? (p.menge !== null && p.ep !== null ? p.menge * p.ep : null);
  const realNachOz = new Map(real.positionen.map((p) => [p.oz, p]));
  const geschaetztOz = new Set(geschaetzt.positionen.map((p) => p.oz));
  const estimated_values: Measurement[] = [];
  const real_values: Measurement[] = [];
  const marks: Mark[] = [];
  for (const p of geschaetzt.positionen) {
    const e = preis(p);
    if (e === null || e < 0) continue;
    estimated_values.push({ oz: p.oz, title_path: p.titel_pfad, metric: "price", value: Math.round(e * 100) / 100, unit: "EUR" });
    const r = realNachOz.get(p.oz);
    const rp = r ? preis(r) : null;
    if (rp === null || rp < 0) continue;
    real_values.push({ oz: p.oz, title_path: p.titel_pfad, metric: "price", value: Math.round(rp * 100) / 100, unit: "EUR" });
    const abw = e ? (rp - e) / e : 0;
    marks.push(Math.abs(abw) <= TOLERANZ
      ? { oz: p.oz, title_path: p.titel_pfad, status: "confirmed" }
      : { oz: p.oz, title_path: p.titel_pfad, status: "deviation", what_happened: `Real price ${abw > 0 ? "+" : ""}${Math.round(abw * 100)} % vs. estimate` });
  }
  return {
    estimated_values, real_values, marks,
    nurGeschaetzt: geschaetzt.positionen.filter((p) => !realNachOz.has(p.oz)).map((p) => p.oz),
    nurReal: real.positionen.filter((p) => !geschaetztOz.has(p.oz)).map((p) => p.oz),
  };
}

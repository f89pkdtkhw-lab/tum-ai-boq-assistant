// Project-close upload on /history (issue #106, epic #93 D3): our report/estimate + the real final bill → DB record.
import { beilageFehler, importFehlerText, routeFehlt } from "./regelwerk";

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

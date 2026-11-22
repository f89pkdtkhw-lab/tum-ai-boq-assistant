// Optional price list next to the bill (issue #115, epic #93 D4/B6).
import type { Preisliste } from "./api";

export const PREISLISTE_FORMATE = [".csv", ".xlsx", ".x84", ".d84", ".x86", ".d86", ".json"];
/** Tender bill next to a D84 offer: the offer carries OZ and prices, the bill the item texts (api/app/preis_api.py). */
export const PREIS_LV_FORMATE = [".x83", ".d83", ".x86", ".d86"];

export function preislisteText(p: Preisliste): string {
  const n = p.eintraege.length;
  const teile = [`${n} ${n === 1 ? "entry" : "entries"}`];
  if (p.warnungen.length > 0) teile.push(`${p.warnungen.length} ${p.warnungen.length === 1 ? "warning" : "warnings"}`);
  return `${p.dateiname}: ${teile.join(", ")}`;
}

// Price list ("bill price per unit", team diagram: price database id · item · unit · price per unit).
// Until the backend price database exists (#99/#111) the list is kept in this browser and used by the price report.
/** `preis` is the price per unit; own entries also keep its parts: material and labour (hours × hourly rate) per unit. */
export type Preis = { item: string; unit: string; preis: number; material?: number; lohn?: number; stunden?: number };

const SCHLUESSEL = "lv-preisliste-v1";
const norm = (s: string) => s.toLowerCase().normalize("NFKD").replace(/[^\p{L}\p{N}]+/gu, " ").trim();
const zahl = (s: string) => Number(s.replace(/\s|€|eur/gi, "").replace(/\.(?=\d{3}(\D|$))/g, "").replace(",", "."));

/** Reads CSV (comma, semicolon or tab; header with item/unit/price in English or German) or JSON [{item, unit, price}]. */
export function lesePreisliste(text: string): Preis[] {
  const t = text.trim();
  if (t.startsWith("[") || t.startsWith("{")) {
    const d = JSON.parse(t);
    const liste = Array.isArray(d) ? d : d.preise ?? d.prices ?? [];
    return liste.map((x: Record<string, unknown>) => teile(
      String(x.item ?? x.bezeichnung ?? x.kurztext ?? ""), String(x.unit ?? x.einheit ?? ""), x.price ?? x.preis ?? x.ep,
      x.material, x.labour ?? x.labor ?? x.lohn, x.hours ?? x.stunden,
    )).filter((p: Preis) => p.item && Number.isFinite(p.preis));
  }
  const zeilen = t.split(/\r?\n/).filter((z) => z.trim());
  const trenner = [";", "\t", ","].find((c) => zeilen[0].includes(c)) ?? ",";
  const kopf = zeilen[0].split(trenner).map((k) => norm(k));
  const spalte = (...namen: string[]) => kopf.findIndex((k) => namen.some((n) => k.includes(n)));
  const [iItem, iUnit, iPreis] = [spalte("item", "bezeichnung", "kurztext", "leistung", "position"), spalte("unit", "einheit", "me"), spalte("price", "preis", "ep")];
  const [iMat, iLohn, iStd] = [spalte("material"), spalte("labour", "labor", "lohn"), spalte("hours", "stunden")];
  if (iItem < 0 || (iPreis < 0 && iMat < 0 && iLohn < 0)) throw new Error("The price list needs an item and a price column.");
  const feld = (f: string[], i: number) => (i < 0 || !(f[i] ?? "").trim() ? undefined : zahl(f[i]));
  return zeilen.slice(1).map((z) => z.split(trenner)).map((f) => teile((f[iItem] ?? "").trim(), iUnit < 0 ? "" : (f[iUnit] ?? "").trim(),
    feld(f, iPreis), feld(f, iMat), feld(f, iLohn), feld(f, iStd)))
    .filter((p) => p.item && Number.isFinite(p.preis));
}

const num = (x: unknown) => (x === undefined || x === null || x === "" ? undefined : Number(x));
/** One entry; without a total price, price = material + labour. */
function teile(item: string, unit: string, preis: unknown, material: unknown, lohn: unknown, stunden: unknown): Preis {
  const [m, l, h] = [num(material), num(lohn), num(stunden)];
  const p: Preis = { item, unit, preis: num(preis) ?? (m ?? 0) + (l ?? 0) };
  if (m !== undefined && Number.isFinite(m)) p.material = m;
  if (l !== undefined && Number.isFinite(l)) p.lohn = l;
  if (h !== undefined && Number.isFinite(h)) p.stunden = h;
  if (m === undefined && l === undefined && num(preis) === undefined) p.preis = NaN;
  return p;
}

/** Own entry from the form: material €/unit plus labour hours/unit × hourly rate. Replaces an entry with the same item and unit. */
export function eintragHinzu(liste: Preis[], e: { item: string; unit: string; material: number; stunden: number; stundensatz: number }): Preis[] {
  const lohn = Math.round(e.stunden * e.stundensatz * 100) / 100;
  const neu: Preis = { item: e.item.trim(), unit: e.unit.trim(), material: e.material, stunden: e.stunden, lohn, preis: Math.round((e.material + lohn) * 100) / 100 };
  return [...liste.filter((p) => !(norm(p.item) === norm(neu.item) && norm(p.unit) === norm(neu.unit))), neu];
}

/** The list as CSV (semicolon, reads back with lesePreisliste) to reuse or share your own dataset. */
export function preislisteCsv(liste: Preis[]): string {
  const z = (n: number | undefined) => (n === undefined ? "" : String(n));
  const feld = (s: string) => (/[;"\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s);
  return ["item;unit;material;hours;labour;price", ...liste.map((p) => [feld(p.item), feld(p.unit), z(p.material), z(p.stunden), z(p.lohn), z(p.preis)].join(";"))].join("\n") + "\n";
}

/** Best price for an item: exact name first, otherwise the longest list entry contained in the short text; same unit if given. */
export function findePreis(liste: Preis[], kurztext: string, einheit: string | null): Preis | null {
  const k = norm(kurztext);
  const passt = (p: Preis) => !einheit || !p.unit || norm(p.unit) === norm(einheit);
  const exakt = liste.find((p) => norm(p.item) === k && passt(p));
  if (exakt) return exakt;
  return liste.filter((p) => passt(p) && norm(p.item).length >= 4 && k.includes(norm(p.item)))
    .sort((a, b) => norm(b.item).length - norm(a.item).length)[0] ?? null;
}

export function ladePreisliste(): Preis[] {
  try { const d = JSON.parse(window.localStorage.getItem(SCHLUESSEL) ?? "[]"); return Array.isArray(d) ? d : []; } catch { return []; }
}
export function speicherePreisliste(liste: Preis[]): boolean {
  try { window.localStorage.setItem(SCHLUESSEL, JSON.stringify(liste)); return true; } catch { return false; }
}

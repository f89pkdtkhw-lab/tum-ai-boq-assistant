// Margin slider (spec "Margin slider to undercut competitors", sections 1–5): competitor markup per item,
// outliers removed, median as benchmark, our markup just below it but never under our own costs.
import { zahl } from "./wettbewerb";

/** One table row: a competitor bid, or our own row (bidder "Our company" / "Wir") with quantity and costs. */
export type Gebot = { bieter: string; item: string; einheit: string; menge: number | null; preis: number | null; summe: number | null;
  direkt: number | null; bgk: number | null; marge: number | null };
export type Punkt = { bieter: string; item: string; aufschlag: number; gewicht: number; angebot: number };
/** One competitor over all its items: markup weighted by direct cost × quantity, offer = sum of its line totals. */
export type Bieter = { name: string; aufschlag: number; angebot: number };

const EIGEN = /^(our|own|us|we|wir|eigen)/i;
const median = (w: number[]) => { const s = [...w].sort((a, b) => a - b), m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };
const mittel = (w: number[]) => w.reduce((a, b) => a + b, 0) / w.length;
const quantil = (s: number[], q: number) => { const i = (s.length - 1) * q, u = Math.floor(i); return s[u] + (s[Math.ceil(i)] - s[u]) * (i - u); };
const ent = (s: string) => s.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&apos;/g, "'")
  .replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(Number(n))).replace(/&amp;/g, "&");
const text = (xml: string) => [...xml.replace(/<rPh\b[\s\S]*?<\/rPh>/g, "").matchAll(/<t\b[^>]*>([\s\S]*?)<\/t>/g)].map((m) => ent(m[1])).join("");

/** First worksheet of an .xlsx as rows of cell texts, read in the browser (zip directory + deflate + XML), no library. */
export async function leseXlsx(daten: ArrayBuffer): Promise<string[][]> {
  const b = new Uint8Array(daten), v = new DataView(daten), dateien = new Map<string, () => Promise<string>>();
  let e = b.length - 22;
  while (e >= 0 && v.getUint32(e, true) !== 0x06054b50) e--;
  if (e < 0) throw new Error("This is not an .xlsx file.");
  for (let p = v.getUint32(e + 16, true), n = v.getUint16(e + 10, true); n > 0; n--) {
    const art = v.getUint16(p + 10, true), groesse = v.getUint32(p + 20, true), nl = v.getUint16(p + 28, true), lokal = v.getUint32(p + 42, true);
    const start = lokal + 30 + v.getUint16(lokal + 26, true) + v.getUint16(lokal + 28, true), roh = b.slice(start, start + groesse);
    dateien.set(new TextDecoder().decode(b.subarray(p + 46, p + 46 + nl)), async () => new TextDecoder().decode(art === 0 ? roh
      : await new Response(new Blob([roh]).stream().pipeThrough(new DecompressionStream("deflate-raw"))).arrayBuffer()));
    p += 46 + nl + v.getUint16(p + 30, true) + v.getUint16(p + 32, true);
  }
  const lies = async (name: string) => (await dateien.get(name)?.()) ?? "";
  const id = (await lies("xl/workbook.xml")).match(/<sheet\b[^>]*\br:id="([^"]+)"/)?.[1];
  const ziel = id && (await lies("xl/_rels/workbook.xml.rels")).match(new RegExp(`<Relationship\\b[^>]*Id="${id}"[^>]*>`))?.[0].match(/Target="([^"]+)"/)?.[1];
  const blatt = await lies(ziel ? (ziel.startsWith("/") ? ziel.slice(1) : `xl/${ziel}`) : "xl/worksheets/sheet1.xml");
  if (!blatt) throw new Error("The Excel file has no worksheet.");
  const strings = [...(await lies("xl/sharedStrings.xml")).matchAll(/<si>([\s\S]*?)<\/si>/g)].map((m) => text(m[1]));
  return [...blatt.matchAll(/<row\b[^>]*?(?:\/>|>([\s\S]*?)<\/row>)/g)].map((r) => {
    const zeile: string[] = [];
    for (const [i, c] of [...(r[1] ?? "").matchAll(/<c\b([^>]*?)(?:\/>|>([\s\S]*?)<\/c>)/g)].entries()) {
      const spalte = c[1].match(/\br="([A-Z]+)\d+"/)?.[1], typ = c[1].match(/\bt="(\w+)"/)?.[1], inhalt = c[2] ?? "", wert = inhalt.match(/<v>([\s\S]*?)<\/v>/)?.[1];
      const j = spalte ? [...spalte].reduce((s, z) => s * 26 + z.charCodeAt(0) - 64, 0) - 1 : i;
      zeile[j] = typ === "inlineStr" ? text(inhalt) : wert == null || typ === "e" ? "" : typ === "s" ? strings[Number(wert)] ?? "" : typ === "b" ? (wert === "1" ? "TRUE" : "FALSE") : ent(wert);
    }
    return Array.from(zeile, (z) => (z ?? "").trim());
  }).filter((z) => z.some(Boolean));
}

/** Rows of the first sheet (header row first) → bids. Columns by name, English or German. */
export function leseGebote(zeilen: string[][]): Gebot[] {
  const NAME = /provider|anbieter|bidder|bieter|firma|company/i;
  const k = zeilen.findIndex((z) => z.some((c) => NAME.test(c)));
  if (k < 0) throw new Error("No header row with a provider or bidder column found.");
  const kopf = zeilen[k].map((c) => c.toLowerCase());
  const s = (re: RegExp) => kopf.findIndex((c) => re.test(c));
  const i = { bieter: s(NAME), item: s(/item|position|leistung|tender|oz/), einheit: s(/^(unit|einheit|me)$/), menge: s(/quantity|menge/),
    preis: s(/unit price|einheitspreis|^ep$|price|preis/), summe: s(/offer|angebot|total|gesamt|^gp$/), direkt: s(/direct|direkt|einzelkosten/),
    bgk: s(/operat|overhead|gemeinkosten|bgk/), marge: s(/margin|marge|gewinn/) };
  const nr = (z: string[], j: number) => {
    const t = j < 0 ? "" : (z[j] ?? "").trim();
    const x = /^-?\d+(\.\d+)?(e[-+]?\d+)?$/i.test(t) ? Number(t) : t ? zahl(t) : NaN;
    return Number.isFinite(x) ? x : null;
  };
  return zeilen.slice(k + 1).map((z) => ({ bieter: (z[i.bieter] ?? "").trim(), item: (z[i.item] ?? "").trim() || "–", einheit: (z[i.einheit] ?? "").trim(),
    menge: nr(z, i.menge), preis: nr(z, i.preis), summe: nr(z, i.summe), direkt: nr(z, i.direkt), bgk: nr(z, i.bgk), marge: nr(z, i.marge) })).filter((g) => g.bieter);
}

/** Section 1: markup = operating cost % + margin %; without that split back-calculated from price and direct cost
 *  (the bid's own, else our direct cost for the item). */
export function punkte(gebote: Gebot[]): Punkt[] {
  const uns = new Map(gebote.filter((g) => EIGEN.test(g.bieter)).map((g) => [g.item, g]));
  return gebote.filter((g) => !EIGEN.test(g.bieter)).flatMap((g): Punkt[] => {
    const d = g.direkt ?? uns.get(g.item)?.direkt, menge = g.menge ?? uns.get(g.item)?.menge ?? 1;
    const aufschlag = g.bgk != null && g.marge != null ? g.bgk + g.marge : d && g.preis != null ? ((g.preis - d) / d) * 100 : null;
    return aufschlag == null ? [] : [{ bieter: g.bieter, item: g.item, aufschlag, gewicht: menge * (d ?? 1), angebot: g.summe ?? menge * (g.preis ?? 0) }];
  });
}

export function bieterListe(alle: Punkt[]): Bieter[] {
  const je = new Map<string, Punkt[]>();
  for (const p of alle) je.set(p.bieter, [...(je.get(p.bieter) ?? []), p]);
  return [...je].map(([name, ps]) => ({ name, angebot: ps.reduce((s, p) => s + p.angebot, 0),
    aufschlag: ps.reduce((s, p) => s + p.aufschlag * p.gewicht, 0) / ps.reduce((s, p) => s + p.gewicht, 0) }));
}

/** Section 2: IQR fences from 5 points on; below that only implausible values (< 0 or > 100 %) go, and the result is low confidence. */
export function bereinige(werte: number[]) {
  const s = [...werte].sort((a, b) => a - b);
  let drin = (x: number) => x >= 0 && x <= 100;
  if (s.length >= 5) { const q1 = quantil(s, 0.25), q3 = quantil(s, 0.75), r = 1.5 * (q3 - q1); drin = (x) => x >= q1 - r && x <= q3 + r; }
  return { werte: werte.filter(drin), raus: werte.filter((x) => !drin(x)).length, wenig: s.length < 5 };
}

/** Section 3: median is the benchmark, mean is shown as info; more than 3 points apart = skewed data. */
export function kennzahlen(werte: number[]) {
  if (!werte.length) return null;
  const m = median(werte), d = mittel(werte);
  return { median: m, mittel: d, schief: Math.abs(d - m) > 3 };
}

export type Posten = { item: string; einheit: string; menge: number; direkt: number; bgk: number; n: number; raus: number; wenig: boolean;
  median: number | null; mittel: number | null; schief: boolean; aufschlag: number; amBoden: boolean; preis: number; preisKonk: number | null };

/** The slider range picks the competitors (by their overall markup); their bids form the per-item benchmark.
 *  Sections 4–5: per item our markup = competitor median + offset (start −1 point), never below our operating costs
 *  plus the minimum margin (our row's margin %, else 0), so never below direct cost. Totals weighted by quantity. */
export function auswerten(gebote: Gebot[], bereich: [number, number], abstand: number) {
  const alle = punkte(gebote), liste = bieterListe(alle);
  const bieter = liste.filter((x) => x.aufschlag >= bereich[0] && x.aufschlag <= bereich[1]);
  const namen = new Set(bieter.map((x) => x.name));
  const gewaehlt = alle.filter((p) => namen.has(p.bieter));
  const posten: Posten[] = gebote.filter((g) => EIGEN.test(g.bieter) && g.direkt).map((u) => {
    const b = bereinige(gewaehlt.filter((p) => p.item === u.item).map((p) => p.aufschlag));
    const k = kennzahlen(b.werte);
    const direkt = u.direkt!, bgk = u.bgk ?? 0, boden = Math.max(0, bgk + Math.max(0, u.marge ?? 0));
    const ziel = k ? k.median + abstand : boden;
    const aufschlag = Math.max(ziel, boden);
    return { item: u.item, einheit: u.einheit, menge: u.menge ?? 1, direkt, bgk, n: b.werte.length, raus: b.raus, wenig: b.wenig,
      median: k?.median ?? null, mittel: k?.mittel ?? null, schief: k?.schief ?? false, aufschlag, amBoden: ziel < boden,
      preis: direkt * (1 + aufschlag / 100), preisKonk: k ? direkt * (1 + k.median / 100) : null };
  });
  const mit = posten.filter((p) => p.preisKonk != null);
  const summe = (f: (p: Posten) => number) => mit.reduce((s, p) => s + p.menge * f(p), 0);
  const gewinn = (auf: (p: Posten) => number) => summe((p) => (p.direkt * (auf(p) - p.bgk)) / 100);
  const w = bieter.map((x) => x.aufschlag);
  return {
    liste, bieter, posten,
    auswahl: { bieter: bieter.length, vonBietern: liste.length, mittel: w.length ? mittel(w) : null, median: w.length ? median(w) : null },
    summe: { uns: summe((p) => p.preis), konk: summe((p) => p.preisKonk!), gewinn: gewinn((p) => p.aufschlag), gewinnKonk: gewinn((p) => p.median!) },
  };
}

/** Histogram bars over [lo, hi]. */
export function histogramm(werte: number[], lo: number, hi: number, faecher = 24): number[] {
  const h = new Array<number>(faecher).fill(0), breite = (hi - lo) / faecher || 1;
  for (const x of werte) h[Math.min(faecher - 1, Math.max(0, Math.floor((x - lo) / breite)))]++;
  return h;
}

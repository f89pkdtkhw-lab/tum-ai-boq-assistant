// Margin slider (spec "Margin slider to undercut competitors", sections 1–5): competitor markup per item,
// outliers removed, median as benchmark, our markup just below it but never under our own costs.
import { zahl } from "./wettbewerb";

/** One table row: a competitor bid, or our own row (bidder "Our company" / "Wir") with quantity and costs. */
export type Gebot = { bieter: string; item: string; einheit: string; menge: number | null; preis: number | null; summe: number | null;
  direkt: number | null; bgk: number | null; marge: number | null };
export type Punkt = { bieter: string; item: string; aufschlag: number; gewicht: number; angebot: number;
  bgk: number | null; marge: number | null };
/** One competitor over all its items: markup weighted by direct cost × quantity, offer = sum of its line totals.
 *  bgk/marge are unweighted averages of the disclosed split (annual, as in the file), or null. */
export type Bieter = { name: string; aufschlag: number; angebot: number; bgk: number | null; marge: number | null; ausreisser: boolean };

const EIGEN = /^(our|own|us|we|wir|eigen)/i;
const median = (w: number[]) => { const s = [...w].sort((a, b) => a - b), m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };
const mittel = (w: number[]) => w.reduce((a, b) => a + b, 0) / w.length;
const quantil = (s: number[], q: number) => { const i = (s.length - 1) * q, u = Math.floor(i); return s[u] + (s[Math.ceil(i)] - s[u]) * (i - u); };
const schnitt = (w: number[]) => (w.length ? w.reduce((a, b) => a + b, 0) / w.length : null);

/** Project duration → factor on annual operating costs (10 months → 10/12). Non-positive falls back to a full year. */
export function monateFaktor(monate: number | null | undefined): number {
  return Number.isFinite(monate) && (monate as number) > 0 ? (monate as number) / 12 : 1;
}

/** Slider accent hue: 0 (red) at the cost-floor margin, 120 (green) at or above the competitor median margin. */
export function sliderHue(marge: number, boden: number, median: number | null): number {
  if (median == null || !(median > boden)) return marge <= boden ? 0 : 120;
  return Math.min(1, Math.max(0, (marge - boden) / (median - boden))) * 120;
}

/** Well-spaced hues so nearby companies stay distinguishable in light and dark mode. */
export const BIETER_FARB_HUES = [220, 8, 152, 36, 280, 332, 190, 85, 22, 255, 172, 305, 48, 128];

/** Preferred hue for a company name (stable across sessions). */
export function bieterFarbHue(name: string): number {
  let h = 0;
  for (const c of name) h = (h * 33 + c.charCodeAt(0)) >>> 0;
  return BIETER_FARB_HUES[h % BIETER_FARB_HUES.length];
}

/** CSS colour for avatars and tests (light-theme mid-tone). The UI also raises lightness in dark mode. */
export function bieterFarbe(name: string): string {
  return `hsl(${bieterFarbHue(name)} 72% 44%)`;
}

/** Unique hues for a set of names: preferred hue if free, otherwise the next palette slot. */
export function bieterFarben(namen: Iterable<string>): Map<string, number> {
  const liste = [...new Set(namen)].sort((a, b) => a.localeCompare(b));
  const belegt = new Set<number>();
  const map = new Map<string, number>();
  for (const name of liste) {
    let hue = bieterFarbHue(name);
    if (belegt.has(hue)) {
      const start = Math.max(0, BIETER_FARB_HUES.indexOf(hue));
      for (let k = 1; k < BIETER_FARB_HUES.length; k++) {
        const alt = BIETER_FARB_HUES[(start + k) % BIETER_FARB_HUES.length];
        if (!belegt.has(alt)) { hue = alt; break; }
      }
    }
    belegt.add(hue);
    map.set(name, hue);
  }
  return map;
}

/** Implied profit margin on the slider scale: competitor markup minus our pro-rated operating costs. */
export function impliziteMarge(aufschlag: number, bgkUns: number): number {
  return aufschlag - bgkUns;
}

export type SliderMarker = { name: string; marge: number; ausreisser: boolean; pct: number };

/** Markers for the margin slider, sorted by implied margin (low → high), positions clamped to the track. */
export function sliderMarker(liste: Bieter[], bgkUns: number, boden: number, hi: number): SliderMarker[] {
  const spanne = Math.max(0.1, hi - boden);
  return liste
    .map((x) => {
      const marge = impliziteMarge(x.aufschlag, bgkUns);
      const pct = ((Math.min(hi, Math.max(boden, marge)) - boden) / spanne) * 100;
      return { name: x.name, marge, ausreisser: x.ausreisser, pct };
    })
    .sort((a, b) => a.marge - b.marge || a.name.localeCompare(b.name));
}

/** Vertical lane offsets (−2…2) so markers that sit within `minAbstand` percent of each other do not fully cover one another. */
export function markerVersatz(marker: { pct: number }[], minAbstand = 3): number[] {
  const lanes: number[] = [];
  for (let i = 0; i < marker.length; i++) {
    const used = new Set<number>();
    for (let j = 0; j < i; j++) {
      if (Math.abs(marker[i].pct - marker[j].pct) < minAbstand) used.add(lanes[j]);
    }
    let lane = 0, schritt = 1;
    while (used.has(lane)) {
      lane = schritt % 2 ? Math.ceil(schritt / 2) : -schritt / 2;
      schritt++;
    }
    lanes.push(lane);
  }
  return lanes;
}
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

/** Section 1: markup = (annual operating cost % × months/12) + margin %; without that split back-calculated from
 *  price and direct cost (the bid's own, else our direct cost for the item). Back-calculated prices are already
 *  project bids, so they are not pro-rated. */
export function punkte(gebote: Gebot[], monate = 12): Punkt[] {
  const faktor = monateFaktor(monate);
  const uns = new Map(gebote.filter((g) => EIGEN.test(g.bieter)).map((g) => [g.item, g]));
  return gebote.filter((g) => !EIGEN.test(g.bieter)).flatMap((g): Punkt[] => {
    const d = g.direkt ?? uns.get(g.item)?.direkt, menge = g.menge ?? uns.get(g.item)?.menge ?? 1;
    const aufschlag = g.bgk != null && g.marge != null ? g.bgk * faktor + g.marge : d && g.preis != null ? ((g.preis - d) / d) * 100 : null;
    return aufschlag == null ? [] : [{ bieter: g.bieter, item: g.item, aufschlag, gewicht: menge * (d ?? 1),
      angebot: g.summe ?? menge * (g.preis ?? 0), bgk: g.bgk, marge: g.marge }];
  });
}

export function bieterListe(alle: Punkt[]): Bieter[] {
  const je = new Map<string, Punkt[]>();
  for (const p of alle) je.set(p.bieter, [...(je.get(p.bieter) ?? []), p]);
  return [...je].map(([name, ps]) => {
    const gewicht = ps.reduce((s, p) => s + p.gewicht, 0);
    return { name, angebot: ps.reduce((s, p) => s + p.angebot, 0),
      aufschlag: gewicht ? ps.reduce((s, p) => s + p.aufschlag * p.gewicht, 0) / gewicht : 0,
      bgk: schnitt(ps.map((p) => p.bgk).filter((x): x is number => x != null)),
      marge: schnitt(ps.map((p) => p.marge).filter((x): x is number => x != null)),
      ausreisser: false };
  });
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

export type Optionen = {
  /** Selected competitor names; omit or null = every competitor. */
  namen?: Iterable<string> | null;
  /** Drop IQR outliers among the selection (default true). */
  ausreisser?: boolean;
  /** Our profit margin as % of direct cost. Omit for competitor-median implied margin − 1 point, floored. */
  marge?: number | null;
  /** Project duration in months; annual operating costs are pro-rated by months/12 (default 12). */
  monate?: number;
};

function zaehle(werte: number[]) {
  const m = new Map<number, number>();
  for (const v of werte) m.set(v, (m.get(v) ?? 0) + 1);
  return m;
}

/** The checked competitors (optional IQR drop) form the benchmark. Our price on every item is
 *  pro-rated operating costs + the slider margin, never below our costs plus the minimum margin
 *  (our row's margin %, else 0). Competitor mean/median and implied margins are taken from the selection. */
export function auswerten(gebote: Gebot[], opt: Optionen = {}) {
  const monate = opt.monate ?? 12, faktor = monateFaktor(monate);
  const alle = punkte(gebote, monate), liste0 = bieterListe(alle);
  const namen = opt.namen == null ? null : new Set([...opt.namen]);
  const ausgewaehlt = namen ? liste0.filter((x) => namen.has(x.name)) : liste0;
  const sauber = opt.ausreisser === false
    ? ausgewaehlt.map((x) => x.aufschlag)
    : bereinige(ausgewaehlt.map((x) => x.aufschlag)).werte;
  const rest = zaehle(sauber);
  const nimmt = (x: number) => { const n = rest.get(x) ?? 0; if (n <= 0) return false; rest.set(x, n - 1); return true; };
  const liste = liste0.map((x) => ({ ...x, ausreisser: (!namen || namen.has(x.name)) && !nimmt(x.aufschlag) }));
  const bieter = liste.filter((x) => (!namen || namen.has(x.name)) && !x.ausreisser);
  const gewaehlt = alle.filter((p) => bieter.some((b) => b.name === p.bieter));

  const uns = gebote.filter((g) => EIGEN.test(g.bieter) && g.direkt);
  const bodenMarge = uns.length ? Math.max(0, ...uns.map((u) => Math.max(0, u.marge ?? 0))) : 0;
  const gewichtUns = uns.reduce((s, u) => s + (u.menge ?? 1) * u.direkt!, 0);
  const bgkUns = gewichtUns ? uns.reduce((s, u) => s + (u.menge ?? 1) * u.direkt! * (u.bgk ?? 0) * faktor, 0) / gewichtUns : 0;
  const margen = bieter.map((x) => x.aufschlag - bgkUns);
  const medianMarge = margen.length ? median(margen) : null, mittelMarge = margen.length ? mittel(margen) : null;
  const vorgabe = medianMarge == null ? bodenMarge : Math.max(bodenMarge, medianMarge - 1);
  const wunsch = opt.marge == null || !Number.isFinite(opt.marge) ? vorgabe : opt.marge;
  const marge = Math.max(bodenMarge, wunsch);

  const posten: Posten[] = uns.map((u) => {
    const b = bereinige(gewaehlt.filter((p) => p.item === u.item).map((p) => p.aufschlag));
    const k = kennzahlen(b.werte);
    const direkt = u.direkt!, bgk = (u.bgk ?? 0) * faktor, mindest = Math.max(0, u.marge ?? 0);
    const effektiv = Math.max(marge, mindest);
    const aufschlag = bgk + effektiv;
    return { item: u.item, einheit: u.einheit, menge: u.menge ?? 1, direkt, bgk, n: b.werte.length, raus: b.raus, wenig: b.wenig,
      median: k?.median ?? null, mittel: k?.mittel ?? null, schief: k?.schief ?? false, aufschlag, amBoden: wunsch < mindest,
      preis: direkt * (1 + aufschlag / 100), preisKonk: k ? direkt * (1 + k.median / 100) : null };
  });
  const mit = posten.filter((p) => p.preisKonk != null);
  const summe = (f: (p: Posten) => number) => mit.reduce((s, p) => s + p.menge * f(p), 0);
  const gewinn = (auf: (p: Posten) => number) => summe((p) => (p.direkt * (auf(p) - p.bgk)) / 100);
  const w = bieter.map((x) => x.aufschlag);
  const hiMarge = Math.max(bodenMarge, ...(margen.length ? margen : [bodenMarge]));
  return {
    liste, bieter, posten, monate, faktor, bgkUns,
    boden: bodenMarge, marge, vorgabe, medianMarge, mittelMarge, hiMarge,
    hue: sliderHue(marge, bodenMarge, medianMarge),
    auswahl: { bieter: bieter.length, vonBietern: liste0.length, ausgewaehlt: ausgewaehlt.length,
      mittel: w.length ? mittel(w) : null, median: w.length ? median(w) : null, mittelMarge, medianMarge },
    summe: { uns: summe((p) => p.preis), konk: summe((p) => p.preisKonk!), gewinn: gewinn((p) => p.aufschlag), gewinnKonk: gewinn((p) => p.median!) },
  };
}

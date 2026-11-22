// GAEB DA XML 3.2 export of a bill (Export page): same structure the backend importer reads (api/app/lv/gaeb.py).
// Phases: X81 bill of quantities, X83 request for offer (no prices), X84 offer, X86 contract award.
// The estimated bill is an X84 with the estimated unit prices from the price report.
import type { LV, Position } from "./api";
import type { Preisbericht } from "./preisbericht";

export type GaebPhase = "81" | "83" | "84" | "86";
export const GAEB_PHASEN: { dp: GaebPhase; name: string }[] = [
  { dp: "81", name: "X81 · Bill of quantities" },
  { dp: "83", name: "X83 · Request for offer (no prices)" },
  { dp: "84", name: "X84 · Offer (with prices)" },
  { dp: "86", name: "X86 · Contract award" },
];

const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const dez = (n: number, stellen: number) => n.toFixed(stellen);
const mitPreis = (dp: GaebPhase) => dp === "84" || dp === "86";

type Knoten = { code: string; titel?: string; kinder: Map<string, Knoten>; positionen: Position[] };

/** `preis`: use the estimated unit prices (estimated bill); otherwise the bill's own prices. */
export function gaebXml(lv: LV, dp: GaebPhase, opt: { preis?: Preisbericht; name?: string; datum?: Date } = {}): string {
  // Estimated bill: unit price and total per item exactly as in the price report (index = item order, OZ may repeat).
  const geschaetzt = new Map<Position, { ep: number | null; gp: number | null }>();
  if (opt.preis) lv.positionen.forEach((p, i) => { const z = opt.preis!.zeilen[i]; if (z) geschaetzt.set(p, { ep: z.epGeschaetzt, gp: z.geschaetzt }); });

  // Tree from the OZ: every part but the last is a section level (01.02.0013 → 01 / 02 / item 0013).
  const wurzel: Knoten = { code: "", kinder: new Map(), positionen: [] };
  let ebenen = 0, posBreite = 1;
  const breiten: number[] = [];
  for (const p of lv.positionen) {
    const teile = p.oz.split(".").filter(Boolean);
    const stufen = teile.slice(0, -1);
    ebenen = Math.max(ebenen, stufen.length);
    stufen.forEach((s, i) => { breiten[i] = Math.max(breiten[i] ?? 1, s.length); });
    posBreite = Math.max(posBreite, (teile.at(-1) ?? "").replace(/[^0-9]/g, "").length || 1);
    let k = wurzel;
    stufen.forEach((s, i) => {
      if (!k.kinder.has(s)) k.kinder.set(s, { code: s, kinder: new Map(), positionen: [] });
      k = k.kinder.get(s)!;
      // Section label: the matching title from the bill if it is there.
      const titel = p.titel_pfad[i + (p.titel_pfad.length - stufen.length)];
      if (titel && !k.titel) k.titel = titel.replace(new RegExp(`^${s}\\s+`), "");
    });
    k.positionen.push(p);
  }

  const summe = (k: Knoten): number => k.positionen.reduce((s, p) => s + (gp(p) ?? 0), 0) + [...k.kinder.values()].reduce((s, c) => s + summe(c), 0);
  // Original bill: its own EP and GP unchanged (also where they disagree – that is a finding, not ours to fix).
  const einheitspreis = (p: Position): number | null => (opt.preis ? geschaetzt.get(p)?.ep ?? null : p.ep);
  const gp = (p: Position): number | null => (opt.preis ? geschaetzt.get(p)?.gp ?? null : p.gp);

  function item(p: Position): string {
    const letzte = p.oz.split(".").filter(Boolean).at(-1) ?? p.oz;
    const m = letzte.match(/^(\d+)(\D*)$/);
    const attr = m ? `RNoPart="${esc(m[1])}"${m[2] ? ` RNoIndex="${esc(m[2])}"` : ""}` : `RNoPart="${esc(letzte)}"`;
    const e = einheitspreis(p), g = gp(p);
    const preise = mitPreis(dp) ? `${e !== null ? `<UP>${dez(e, 2)}</UP>` : ""}${g !== null ? `<IT>${dez(g, 2)}</IT>` : ""}` : "";
    const art = p.typ === "pauschal" ? "<LumpSumItem>Yes</LumpSumItem>" : p.typ === "bedarf" ? "<Provis>WithoutTotal</Provis>" : "";
    const lang = (p.langtext ?? "").split(/\n+/).filter(Boolean).map((z) => `<p>${esc(z)}</p>`).join("");
    return `<Item ${attr}>${art}${p.menge !== null ? `<Qty>${dez(p.menge, 3)}</Qty>` : ""}${p.einheit ? `<QU>${esc(p.einheit)}</QU>` : ""}${preise}`
      + `<Description><CompleteText><OutlineText><OutlTxt><TextOutlTxt><span>${esc(p.kurztext)}</span></TextOutlTxt></OutlTxt></OutlineText>`
      + `${lang ? `<DetailTxt><Text>${lang}</Text></DetailTxt>` : ""}</CompleteText></Description></Item>`;
  }
  function body(k: Knoten): string {
    const teile = [...k.kinder.values()].map((c) =>
      `<BoQCtgy RNoPart="${esc(c.code)}"><LblTx><p>${esc(c.titel ?? c.code)}</p></LblTx><BoQBody>${body(c)}</BoQBody>`
      + `${mitPreis(dp) ? `<Totals><Total>${dez(summe(c), 2)}</Total></Totals>` : ""}</BoQCtgy>`);
    if (k.positionen.length) teile.push(`<Itemlist>${k.positionen.map(item).join("")}</Itemlist>`);
    return teile.join("");
  }

  const bkdn = [...Array.from({ length: ebenen }, (_, i) => `<BoQBkdn><Type>BoQLevel</Type><Length>${breiten[i] ?? 2}</Length><Num>Yes</Num></BoQBkdn>`),
    `<BoQBkdn><Type>Item</Type><Length>${Math.min(posBreite, 14)}</Length><Num>Yes</Num></BoQBkdn>`].join("");
  const datum = (opt.datum ?? new Date()).toISOString().slice(0, 10);
  return `<?xml version="1.0" encoding="UTF-8"?>\n<GAEB xmlns="http://www.gaeb.de/GAEB_DA_XML/DA${dp}/3.2">`
    + `<GAEBInfo><Version>3.2</Version><ProgSystem>LV Scout</ProgSystem><Date>${datum}</Date></GAEBInfo>`
    + `<Award><DP>${dp}</DP><AwardInfo><Cur>EUR</Cur></AwardInfo><BoQ><BoQInfo><Name>${esc(opt.name ?? lv.name)}</Name>${bkdn}</BoQInfo>`
    + `<BoQBody>${body(wurzel)}</BoQBody></BoQ></Award></GAEB>\n`;
}

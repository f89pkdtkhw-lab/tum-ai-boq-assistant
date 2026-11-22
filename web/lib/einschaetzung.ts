// One-glance assessment of a reviewed BoQ: traffic light, score, cost comparison and recommendations.
// Only evidenced numbers: stated and recalculated prices come from the file, the history estimate from past
// projects. No AI price is invented; that slot stays empty until a live estimation model exists.
import type { Finding, Pruefbericht } from "./api";
import type { TradeStat } from "./history-api";
import {
  ampelVonScore, DEFAULT_MODELL, PREIS_AUSREISSER, SCHAETZUNG, zusammenfassenLokal,
  type Bewertungsmodell,
} from "./bewertungsmodell.ts";

export type Ampel = "rot" | "gelb" | "gruen";
export type Faktor = { name: string; wert: string; ampel: Ampel; werte?: Record<string, string | number> };
export type Empfehlung = { ampel: Ampel; text: string; werte?: Record<string, string | number> };
export type Einschaetzung = {
  /** Team score out of 10 (one decimal); `punkte` is the same ×10 for storage and charts. */
  score: number; punkte: number; ampel: Ampel; urteil: string;
  /** Counts for the report header: big problems, warnings, local recommendations; estimate as centre ± half range. */
  zaehler: { grosseProbleme: number; warnungen: number; empfehlungen: number };
  schaetzung: { mitte: number; plusMinus: number } | null;
  /** True when the score comes from the backend summary (#94) rather than only from the browser. */
  offiziell: boolean;
  positionen: Record<Ampel, number>;
  kosten: { angegeben: number | null; nachgerechnet: number | null; risiko: number | null; historie: number | null };
  faktoren: Faktor[]; empfehlungen: Empfehlung[];
};

const ROT: Finding["schwere"][] = ["kritisch", "hoch"];
const IM_VERTRAG = new Set(["normal", "pauschal", "stundenlohn", "zulage"]);
const prozent = (x: number) => `${Math.round(x * 100)} %`;
const ampelVon = (wert: number, gelb: number, rot: number): Ampel => (wert >= rot ? "rot" : wert >= gelb ? "gelb" : "gruen");
/** Same trade key as deviationByTrade in history-api.ts: first word of 4+ letters, capitalised. */
export const gewerkVon = (kurztext: string) => {
  const w = kurztext.split(/[^\p{L}\p{N}]+/u).find((x) => x.length >= 4);
  return w ? w[0].toUpperCase() + w.slice(1).toLowerCase() : null;
};

/** Optional price-check counts (lib/preise.ts): unusual = yellow + red, verglichen = all compared unit prices. */
export type PreisSignal = { auffaellig: number; verglichen: number; rot?: number };

/** Backend reason texts (bewertung.py) as translatable templates; unknown texts pass through unchanged. */
export function grundVorlage(grund: string): { name: string; werte?: Record<string, string | number> } {
  const share = grund.match(/^Share of affected items: (\d+(?:\.\d+)?) % \((?:−|-)([0-9.]+)\)$/);
  if (share) return { name: "Share of affected items: {pct} % (−{p})", werte: { pct: share[1], p: share[2] } };
  const approx = grund.match(/^Report 2: (\d+) approximation\(s\) too big$/);
  if (approx) return { name: "Report 2: {n} approximations too big", werte: { n: approx[1] } };
  const report = grund.match(/^Report (\d): (.+)$/);
  if (report) {
    const r = report[1];
    let rest = report[2];
    let p: string | undefined;
    const withPts = rest.match(/^(.*) \((?:−|-)([0-9.]+)\)$/);
    if (withPts) { rest = withPts[1]; p = withPts[2]; }
    const schwer = / \(critical or 5\+\)$/.test(rest);
    rest = rest.replace(/ \(critical or 5\+\)$/, "");
    const both = rest.match(/^(\d+) big problems?(?:, (\d+) warnings?)?$/);
    const warn = rest.match(/^(\d+) warnings?$/);
    if (both) {
      const n = both[1], w = both[2];
      let name = schwer ? "Report {r}: {n} big problems (critical or 5+)" : "Report {r}: {n} big problems";
      if (w) name = "Report {r}: {n} big problems, {w} warnings";
      if (p) name += " (−{p})";
      return { name, werte: w ? { r, n, w, ...(p ? { p } : {}) } : { r, n, ...(p ? { p } : {}) } };
    }
    if (warn) {
      const name = p ? "Report {r}: {w} warnings (−{p})" : "Report {r}: {w} warnings";
      return { name, werte: { r, w: warn[1], ...(p ? { p } : {}) } };
    }
  }
  return { name: grund };
}

export function einschaetzen(bericht: Pruefbericht, gewerke: TradeStat[] | null, preise: PreisSignal | null = null,
  modell: Bewertungsmodell = DEFAULT_MODELL): Einschaetzung {
  const { lv, findings, zusammenfassung } = bericht;
  const echte = findings.filter((f) => !f.regel_id.startsWith("MOCK_"));
  const schlimmste = new Map<string, Finding["schwere"]>();
  const rang = { kritisch: 0, hoch: 1, mittel: 2, niedrig: 3 };
  for (const f of echte) {
    const alt = schlimmste.get(f.oz);
    if (!alt || rang[f.schwere] < rang[alt]) schlimmste.set(f.oz, f.schwere);
  }
  const positionen: Record<Ampel, number> = { rot: 0, gelb: 0, gruen: 0 };
  for (const p of lv.positionen) {
    const s = schlimmste.get(p.oz);
    positionen[!s ? "gruen" : ROT.includes(s) ? "rot" : s === "mittel" ? "gelb" : "gruen"] += 1;
  }
  const n = Math.max(lv.positionen.length, 1);

  // Costs: contract items only; optional/alternative items are the risk add-on.
  const vertrag = lv.positionen.filter((p) => IM_VERTRAG.has(p.typ));
  const mitGp = vertrag.filter((p) => p.gp !== null);
  const angegeben = mitGp.length ? mitGp.reduce((s, p) => s + (p.gp ?? 0), 0) : null;
  const rechenbar = vertrag.filter((p) => p.menge !== null && p.ep !== null);
  const nachgerechnet = rechenbar.length ? rechenbar.reduce((s, p) => s + (p.menge ?? 0) * (p.ep ?? 0), 0) : null;
  const optional = lv.positionen.filter((p) => !IM_VERTRAG.has(p.typ) && p.menge !== null && p.ep !== null)
    .reduce((s, p) => s + (p.menge ?? 0) * (p.ep ?? 0), 0);
  const risiko = nachgerechnet === null ? null : nachgerechnet + optional;

  const abweichung = new Map((gewerke ?? []).filter((g) => g.avgDeviation !== null).map((g) => [g.trade, g.avgDeviation as number]));
  const historie = nachgerechnet === null || abweichung.size === 0 ? null : rechenbar.reduce((s, p) => {
    const dev = abweichung.get(gewerkVon(p.kurztext) ?? "") ?? 0;
    return s + (p.menge ?? 0) * (p.ep ?? 0) * (1 + dev / 100);
  }, 0);

  const preisAnteil = preise?.verglichen ? preise.auffaellig / preise.verglichen : 0;
  const offenAnteil = nachgerechnet ? optional / nachgerechnet : 0;

  const gross = echte.filter((f) => ROT.includes(f.schwere)).length;
  const preisRot = preise?.rot ?? 0;
  const warnungen = echte.length - gross + Math.max(0, (preise?.auffaellig ?? 0) - preisRot);
  const abzugHistorie = preisRot === 0 ? 0 : preisRot >= PREIS_AUSREISSER.schwelle_schwer ? PREIS_AUSREISSER.abzug_schwer : PREIS_AUSREISSER.abzug;
  const zuWeit = rechenbar.filter((p) => Math.abs(abweichung.get(gewerkVon(p.kurztext) ?? "") ?? 0) > SCHAETZUNG.grenze_prozent).length + preisRot;
  const abzugSchaetzung = Math.round(Math.min(SCHAETZUNG.max, zuWeit * SCHAETZUNG.abzug) * 10) / 10;
  // Official only when the backend summary was computed with the same model (or predates the field).
  const z = zusammenfassung ?? null;
  const offiziell = z !== null && (!z.bewertungsmodell || z.bewertungsmodell === modell) ? z : null;
  const backendVergleich = offiziell?.score_abzuege.some((a) => a.bericht === "vergleich") ?? false;
  const browserR2 = backendVergleich ? 0 : abzugHistorie + abzugSchaetzung;
  const lokal = zusammenfassenLokal(echte, n, modell);
  const roh = (offiziell ? offiziell.score : lokal.score) - browserR2;
  const score = Math.round(Math.max(0, Math.min(10, roh)) * 10) / 10;
  const punkte = Math.round(score * 10);
  const ampel: Ampel = ampelVonScore(score, modell);
  const urteil = ampel === "gruen" ? "Looks good – ready to price" : ampel === "gelb" ? "Bid with care – clarify first" : "High risk – do not bid as is";
  const abzug = (x: number) => (x === 0 ? "0" : `−${x}`);

  const ampelAbzug = (x: number): Ampel => (x >= 2 ? "rot" : x > 0 ? "gelb" : "gruen");
  const sichtbareAbzuege = offiziell ? offiziell.score_abzuege : lokal.score_abzuege;
  const keinBefund = sichtbareAbzuege.filter((a) => a.bericht !== "vergleich").length === 0;
  const keinAbzugHinweis = modell === "streng"
    ? "Warnings and what-if cases (no penalty)"
    : "Notices and what-if cases (no penalty)";
  const r2Preview = backendVergleich ? [] : [
    { name: "Report 2 (browser preview): {n} price outliers", werte: { n: preisRot }, wert: abzug(abzugHistorie), ampel: ampelAbzug(abzugHistorie) },
    { name: "Report 2 (browser preview): estimates too far off (±), {n} items", werte: { n: zuWeit }, wert: abzug(abzugSchaetzung), ampel: abzugSchaetzung >= 1 ? "rot" : ampelAbzug(abzugSchaetzung) },
  ];
  const faktoren: Faktor[] = [
    ...sichtbareAbzuege.map((a) => ({ ...grundVorlage(a.grund), wert: abzug(Math.abs(a.punkte)), ampel: ampelAbzug(Math.abs(a.punkte)) })),
    ...(keinBefund ? [{ name: "Report 1: no big problems", wert: "0", ampel: "gruen" as Ampel }] : []),
    ...r2Preview,
    { name: keinAbzugHinweis, werte: {}, wert: "0", ampel: "gruen" },
  ];
  const tief = nachgerechnet ?? angegeben;
  const schaetzung = tief === null ? null : { mitte: (tief + (historie ?? tief) + optional) / 2, plusMinus: ((historie ?? tief) + optional - tief) / 2 };

  const anzahl = (regel: string) => echte.filter((f) => f.regel_id === regel).length;
  const empfehlungen: Empfehlung[] = [];
  const rechenfehler = anzahl("RECHENFEHLER");
  if (rechenfehler) empfehlungen.push({ ampel: "rot", text: "Correct {n} price errors before pricing; they change the total by {euro}.",
    werte: { n: rechenfehler, euro: Math.round(Math.abs((angegeben ?? 0) - (nachgerechnet ?? 0))) } });
  const fehlt = anzahl("MENGE_FEHLT") + anzahl("EINHEIT_FEHLT") + anzahl("LANGTEXT_FEHLT");
  if (fehlt) empfehlungen.push({ ampel: "gelb", text: "Ask the client for {n} missing quantities, units or descriptions.", werte: { n: fehlt } });
  const doppelt = anzahl("OZ_DUPLIKAT");
  if (doppelt) empfehlungen.push({ ampel: "gelb", text: "Clarify {n} duplicate item numbers.", werte: { n: doppelt } });
  const teuer = (gewerke ?? []).filter((g) => (g.avgDeviation ?? 0) >= 15 && rechenbar.some((p) => gewerkVon(p.kurztext) === g.trade));
  if (teuer.length) empfehlungen.push({ ampel: "gelb", text: "Add a buffer for {trades}: past projects ran over by 15 % or more.",
    werte: { trades: teuer.slice(0, 4).map((g) => `${g.trade} (+${Math.round(g.avgDeviation ?? 0)} %)`).join(", ") } });
  if (preise?.auffaellig) empfehlungen.push({ ampel: preisAnteil >= .04 ? "rot" : "gelb", text: "Re-check {n} unusual unit prices in the Prices tab.", werte: { n: preise.auffaellig } });
  if (optional > 0) empfehlungen.push({ ampel: offenAnteil >= .15 ? "rot" : "gelb", text: "Optional and alternative items are worth {euro} on top; agree how they will be instructed.",
    werte: { euro: Math.round(optional) } });
  if (empfehlungen.length === 0 && ampel === "gruen") empfehlungen.push({ ampel: "gruen", text: "No blocking issues found by the rules. Do a final manual check and price the BoQ." });

  return { score, punkte, ampel, urteil, positionen, kosten: { angegeben, nachgerechnet, risiko, historie }, faktoren, empfehlungen,
    // Counts are always what the report lists (real findings + price outliers, no demo entry), so tiles, ring and list agree.
    // The backend summary stays the source of the score only.
    zaehler: { grosseProbleme: gross + preisRot, warnungen, empfehlungen: empfehlungen.filter((x) => x.ampel !== "gruen").length },
    schaetzung, offiziell: offiziell !== null };
}

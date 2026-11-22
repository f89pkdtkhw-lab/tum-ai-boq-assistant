// Selectable scoring models. Tunable constants live in bewertungsmodell-konstanten.json
// (shared with api/app/pruefung/bewertung.py). Pure helpers; persistence is opt-in.
import KONST from "./bewertungsmodell-konstanten.json" with { type: "json" };
import type { Finding, ScoreAbzug, Zusammenfassung } from "./api";

export type Bewertungsmodell = "streng" | "gestaffelt" | "anteil" | "fehler_klaerung" | "ausgewogen";
export const MODELLE = KONST.ids as Bewertungsmodell[];
export const DEFAULT_MODELL: Bewertungsmodell = KONST.default as Bewertungsmodell;
export const SPEICHER_SCHLUESSEL = "lv-bewertungsmodell-v1";

const SCORE_START = KONST.score_start;
const SCORE_MIN = KONST.score_min;
const ABZUG = KONST.abzug as Record<string, number>;
const HALB = KONST.halb_gewicht;
const CAP = KONST.findings_cap;
const GROESSE_BEZUG = KONST.groesse_bezug;
const AI_QUELLEN = new Set(KONST.ai_quellen);
const HALB_KATEGORIEN = new Set(KONST.halb_kategorien);
const ECHTE_REGELN = new Set(KONST.echte_fehler_regeln);
const GROSS = new Set(["kritisch", "hoch"]);
const RANG: Record<string, number> = { kritisch: 0, hoch: 1, mittel: 2, niedrig: 3 };
const ANTEIL_GEWICHT: Record<string, number> = { kritisch: 1, hoch: 1, mittel: 0.2, niedrig: 0 };
const TITEL: Record<string, string> = { regelwerk: "Report 1", vergleich: "Report 2", was_wenn: "Report 3" };
const BERICHTE = ["regelwerk", "vergleich", "was_wenn"] as const;

export function istBewertungsmodell(wert: unknown): wert is Bewertungsmodell {
  return typeof wert === "string" && (MODELLE as readonly string[]).includes(wert);
}

export function ampelGrenzen(modell: Bewertungsmodell): { gruen: number; gelb: number } {
  if (modell === "streng") return { gruen: KONST.streng.ampel_gruen, gelb: KONST.streng.ampel_gelb };
  return { gruen: KONST.ampel_gruen, gelb: KONST.ampel_gelb };
}

export function ampelVonScore(score: number, modell: Bewertungsmodell): "rot" | "gelb" | "gruen" {
  const { gruen, gelb } = ampelGrenzen(modell);
  return score >= gruen ? "gruen" : score >= gelb ? "gelb" : "rot";
}

export function vollesGewicht(finding: Pick<Finding, "kategorie" | "quelle" | "regel_id"> | { kategorie?: string; quelle?: string; regel_id?: string }): boolean {
  const quelle = finding.quelle || "regel";
  if (AI_QUELLEN.has(quelle)) return false;
  const kategorie = finding.kategorie || "fehler";
  if (HALB_KATEGORIEN.has(kategorie)) return false;
  return kategorie === "fehler" || ECHTE_REGELN.has(finding.regel_id ?? "");
}

export function groessenFaktor(nPositionen: number): number {
  const n = Math.max(nPositionen, 1);
  if (n <= GROESSE_BEZUG) return 1;
  return Math.min(1, Math.sqrt(GROESSE_BEZUG / n));
}

const r1 = (wert: number) => Math.round(wert * 10) / 10;

function befundGrund(titel: string, nGross: number, nWarn: number, punkte: number, schwer = false): string {
  const teile: string[] = [];
  if (nGross) teile.push(`${nGross} ${nGross === 1 ? "big problem" : "big problems"}${schwer ? " (critical or 5+)" : ""}`);
  if (nWarn) teile.push(`${nWarn} ${nWarn === 1 ? "warning" : "warnings"}`);
  return `${titel}: ${teile.join(", ")} (−${r1(Math.abs(punkte)).toFixed(1)})`;
}

function anteilGrund(anteil: number, punkte: number): string {
  const pct = r1(anteil * 100);
  const pctText = pct === Math.trunc(pct) ? String(Math.trunc(pct)) : pct.toFixed(1);
  return `Share of affected items: ${pctText} % (−${r1(Math.abs(punkte)).toFixed(1)})`;
}

function verteilen(roh: Record<string, number>, ziel: number): Record<string, number> {
  const gesamt = Object.values(roh).reduce((s, v) => s + v, 0);
  if (gesamt <= 0 || ziel <= 0) return Object.fromEntries(Object.keys(roh).map((k) => [k, 0]));
  const verteilt: Record<string, number> = {};
  for (const [b, wert] of Object.entries(roh)) verteilt[b] = r1(ziel * (wert / gesamt));
  const drift = r1(ziel - Object.values(verteilt).reduce((s, v) => s + v, 0));
  if (drift) {
    const haupt = Object.keys(verteilt).sort((a, b) => verteilt[b] - verteilt[a])[0];
    verteilt[haupt] = r1(verteilt[haupt] + drift);
  }
  return verteilt;
}

function gestaffeltRoh(findings: FindingLike[], mitGewicht: boolean): number {
  return findings.reduce((s, f) => {
    const basis = ABZUG[f.schwere] ?? 0;
    const faktor = !mitGewicht || vollesGewicht(f) ? 1 : HALB;
    return s + basis * faktor;
  }, 0);
}

function anteilRoh(findings: FindingLike[], nPositionen: number): { roh: number; anteil: number } {
  const worst = new Map<string, FindingLike["schwere"]>();
  for (const f of findings) {
    const alt = worst.get(f.oz);
    if (!alt || (RANG[f.schwere] ?? 9) < (RANG[alt] ?? 9)) worst.set(f.oz, f.schwere);
  }
  const n = Math.max(nPositionen, 1);
  const anteil = [...worst.values()].reduce((s, sev) => s + (ANTEIL_GEWICHT[sev] ?? 0), 0) / n;
  return { roh: SCORE_START * anteil, anteil };
}

export type FindingLike = {
  oz: string;
  schwere: Finding["schwere"];
  kategorie?: Finding["kategorie"] | string;
  quelle?: Finding["quelle"] | string;
  regel_id?: string;
};

export type BerichtVon = (f: FindingLike) => ScoreAbzug["bericht"];

/** Findings deductions only (no price-outlier / approximation rows). Mirrors bewertung.py. */
export function findingsAbzuege(
  findings: FindingLike[],
  nPositionen: number,
  modell: Bewertungsmodell,
  berichtVon: BerichtVon = () => "regelwerk",
): ScoreAbzug[] {
  const gruppen: Record<ScoreAbzug["bericht"], FindingLike[]> = { regelwerk: [], vergleich: [], was_wenn: [] };
  for (const f of findings) {
    const b = berichtVon(f);
    gruppen[b in gruppen ? b : "regelwerk"].push(f);
  }

  if (modell === "streng") {
    const aus: ScoreAbzug[] = [];
    for (const b of BERICHTE) {
      const gross = gruppen[b].filter((f) => GROSS.has(f.schwere));
      const n = gross.length;
      if (!n) continue;
      const schwer = n >= KONST.streng.grosse_probleme_schwer || gross.some((f) => f.schwere === "kritisch");
      const punkte = schwer ? KONST.streng.abzug_bericht_schwer : KONST.streng.abzug_bericht;
      aus.push({ grund: befundGrund(TITEL[b], n, 0, punkte, schwer), punkte: -r1(punkte), bericht: b });
    }
    return aus;
  }

  if (modell === "anteil") {
    const { roh, anteil } = anteilRoh(findings, nPositionen);
    const punkte = Math.min(CAP, roh);
    if (punkte <= 0) return [];
    return [{ grund: anteilGrund(anteil, punkte), punkte: -r1(punkte), bericht: "regelwerk" }];
  }

  const mitGewicht = modell === "fehler_klaerung" || modell === "ausgewogen";
  const rawBy: Record<string, number> = {};
  for (const b of BERICHTE) rawBy[b] = gestaffeltRoh(gruppen[b], mitGewicht);
  const raw = Object.values(rawBy).reduce((s, v) => s + v, 0);
  const faktor = modell === "ausgewogen" ? groessenFaktor(nPositionen) : 1;
  const ziel = Math.min(CAP, raw * faktor);
  if (ziel <= 0) return [];
  const verteilt = verteilen(rawBy, ziel);
  const aus: ScoreAbzug[] = [];
  for (const b of BERICHTE) {
    const punkte = verteilt[b];
    if (punkte <= 0) continue;
    const nGross = gruppen[b].filter((f) => GROSS.has(f.schwere)).length;
    const nWarn = gruppen[b].filter((f) => f.schwere === "mittel").length;
    aus.push({ grund: befundGrund(TITEL[b], nGross, nWarn, punkte), punkte: -r1(punkte), bericht: b });
  }
  return aus;
}

export function scoreAusAbzuegen(abzuege: { punkte: number }[]): number {
  return r1(Math.max(SCORE_MIN, SCORE_START + abzuege.reduce((s, a) => s + a.punkte, 0)));
}

export function zusammenfassenLokal(
  findings: FindingLike[],
  nPositionen: number,
  modell: Bewertungsmodell,
): Pick<Zusammenfassung, "score" | "score_abzuege" | "bewertungsmodell"> {
  const score_abzuege = findingsAbzuege(findings, nPositionen, modell);
  return { score: scoreAusAbzuegen(score_abzuege), score_abzuege, bewertungsmodell: modell };
}

export function ladeBewertungsmodell(): Bewertungsmodell {
  if (typeof window === "undefined") return DEFAULT_MODELL;
  try {
    const wert = window.localStorage.getItem(SPEICHER_SCHLUESSEL);
    if (istBewertungsmodell(wert)) return wert;
  } catch { /* storage blocked */ }
  return DEFAULT_MODELL;
}

const hoerer = new Set<() => void>();

export function speichereBewertungsmodell(modell: Bewertungsmodell): void {
  try { window.localStorage.setItem(SPEICHER_SCHLUESSEL, modell); } catch { /* memory only */ }
  hoerer.forEach((h) => h());
}

export function beobachteBewertungsmodell(hoer: () => void): () => void {
  hoerer.add(hoer);
  return () => { hoerer.delete(hoer); };
}

/** Labels and info-sheet copy (English keys; German via i18n). */
export const MODELL_INFO: Record<Bewertungsmodell, { name: string; kurz: string; text: string; beispiel: string }> = {
  streng: {
    name: "Strict",
    kurz: "Even a few serious problems drop the score sharply.",
    text: "This model is strict: even a few serious problems lower the score a lot, and warnings barely count. Choose it when you want a clear yes or no before you bid.",
    beispiel: "Example: a short BoQ with one serious AI finding gets 6.5 (yellow).",
  },
  gestaffelt: {
    name: "Graduated",
    kurz: "Each finding lowers the score; serious ones more than small ones.",
    text: "Each finding lowers the score on its own, serious ones more than small ones. Choose it when you want the score to reflect how many problems there are.",
    beispiel: "Example: a short BoQ with one serious AI finding gets 9.0 (green).",
  },
  anteil: {
    name: "Share",
    kurz: "Looks at the share of affected items, not the raw count.",
    text: "The score follows the share of items with a problem, so a large BoQ is not punished just for having more lines. Choose it for long bills of quantities.",
    beispiel: "Example: a short BoQ with one serious AI finding (half the items) gets 5.0 (yellow).",
  },
  fehler_klaerung: {
    name: "Errors vs. hints",
    kurz: "Real errors count fully; hints and AI notes count less.",
    text: "Clear mistakes, such as wrong figures or missing quantities, count fully; hints and AI notes count less. Choose it when you want real errors to weigh more than things that only need checking.",
    beispiel: "Example: a short BoQ with one serious AI finding gets 9.5 (green).",
  },
  ausgewogen: {
    name: "Balanced",
    kurz: "Default: a fair mix for everyday use.",
    text: "A balanced mix: serious findings count more, hints less, and large BoQs are treated a little more gently. This is the default and a good choice for everyday use.",
    beispiel: "Example: a short BoQ with one serious AI finding gets 9.5 (green).",
  },
};

export const PREIS_AUSREISSER = KONST.preis_ausreisser;
export const SCHAETZUNG = KONST.schaetzung;
export { SCORE_START, SCORE_MIN, KONST };

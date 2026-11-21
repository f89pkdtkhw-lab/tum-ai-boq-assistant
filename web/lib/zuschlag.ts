// Markup calculation (Zuschlagskalkulation, Endsummen method) and bid advice from a tender opening result (Submissionsergebnis).
// Orientation values as share of turnover (bauprofessor.de, "Vorbestimmte Kalkulationszuschläge", Eckwerte):
//   BGK 5–12 %, AGK 8–20 %, Wagnis + Gewinn 3–8 %; together ~20–35 % of the bid total.
// Too-low threshold (Aufgreifschwelle, § 16d VOB/A): building practice often checks from 10 % below the next bid,
// OLG Düsseldorf uses 20 % as the rule. We warn at 10 % to stay on the safe side.

export type Zuschlaege = {
  bgkProzent: number;          // site overheads, % of the bid total
  agkModus: "prozent" | "monat";
  agkProzent: number;          // general business costs, % of the bid total
  agkMonat: number;            // or: AGK € per month …
  monate: number;              // … × construction months, charged to this job
  wgProzent: number;           // risk and profit, % of the bid total
  unterbieten: number;         // undercut the lowest competitor by this many %
};
export const STANDARD: Zuschlaege = { bgkProzent: 8, agkModus: "prozent", agkProzent: 12, agkMonat: 25000, monate: 6, wgProzent: 5, unterbieten: 2 };
export const SPANNEN = { bgk: [5, 12], agk: [8, 20], wg: [3, 8] } as const;
export const AUFGREIFSCHWELLE = 10; // % below the next bid

export type Kalkulation = { ekt: number; bgk: number; agk: number; selbstkosten: number; wg: number; angebot: number; zuschlagAufEkt: number; agkProzent: number };

/** Bid total from direct costs (EKT): shares of the bid total, so Angebot = (EKT + fixed AGK) / (1 − shares). */
export function kalkuliere(ekt: number, z: Zuschlaege): Kalkulation {
  const anteile = (z.bgkProzent + (z.agkModus === "prozent" ? z.agkProzent : 0) + z.wgProzent) / 100;
  if (anteile >= 0.95) throw new Error("Markups must stay below 95 % of the bid total.");
  const agkFest = z.agkModus === "monat" ? z.agkMonat * z.monate : 0;
  const angebot = (ekt + agkFest) / (1 - anteile);
  const bgk = angebot * z.bgkProzent / 100;
  const agk = z.agkModus === "prozent" ? angebot * z.agkProzent / 100 : agkFest;
  const wg = angebot * z.wgProzent / 100;
  const r = (n: number) => Math.round(n * 100) / 100;
  return { ekt: r(ekt), bgk: r(bgk), agk: r(agk), selbstkosten: r(ekt + bgk + agk), wg: r(wg), angebot: r(angebot),
    zuschlagAufEkt: ekt ? Math.round((angebot / ekt - 1) * 1000) / 10 : 0, agkProzent: angebot ? Math.round(agk / angebot * 1000) / 10 : 0 };
}

export type Gebot = {
  empfohlen: number;                 // recommended bid total
  wgProzent: number;                 // risk + profit left in that bid, % of the bid
  rang: number;                      // place among the bids (1 = lowest)
  grund: "kalkuliert" | "unterbietet" | "angehoben" | "selbstkosten" | "schwelle";
  warnungen: ("unter_selbstkosten" | "preispruefung" | "teurer_als_alle")[];
  naechstes: number | null;          // lowest competitor
};

/** Advice: undercut the lowest competitor a little, but never below own costs (Selbstkosten) or into the price-check zone. */
export function gebot(k: Kalkulation, konkurrenz: number[], z: Pick<Zuschlaege, "unterbieten">): Gebot {
  const andere = konkurrenz.filter((n) => Number.isFinite(n) && n > 0).sort((a, b) => a - b);
  const naechstes = andere[0] ?? null;
  let empfohlen = k.angebot;
  let grund: Gebot["grund"] = "kalkuliert";
  // Aim just under the cheapest competitor – also upwards when our own calculation is far lower (money left on the table).
  if (naechstes !== null) {
    empfohlen = naechstes * (1 - z.unterbieten / 100);
    grund = empfohlen < k.angebot ? "unterbietet" : "angehoben";
    const schwelle = naechstes * (1 - AUFGREIFSCHWELLE / 100);
    if (empfohlen < schwelle) { empfohlen = schwelle; grund = "schwelle"; }
    if (empfohlen < k.selbstkosten) { empfohlen = k.selbstkosten; grund = "selbstkosten"; }
  }
  empfohlen = Math.round(empfohlen);
  const warnungen: Gebot["warnungen"] = [];
  if (empfohlen < k.selbstkosten) warnungen.push("unter_selbstkosten");
  if (naechstes !== null && empfohlen < naechstes * (1 - AUFGREIFSCHWELLE / 100)) warnungen.push("preispruefung");
  if (naechstes !== null && empfohlen >= naechstes) warnungen.push("teurer_als_alle");
  return { empfohlen, wgProzent: empfohlen ? Math.round((empfohlen - k.selbstkosten) / empfohlen * 1000) / 10 : 0,
    rang: andere.filter((n) => n < empfohlen).length + 1, grund, warnungen, naechstes };
}

/** Competitor totals from free text: one per line or separated by ; – German or English number format. */
export function leseGebote(text: string): number[] {
  return text.split(/[\n;]+/).map((s) => s.replace(/[€\s]|eur/gi, "")).filter(Boolean).map((s) => {
    const de = /,\d{1,2}$/.test(s) || /\.\d{3}(\D|$)/.test(s) && !/,\d{3}/.test(s);
    return Number(de ? s.replace(/\./g, "").replace(",", ".") : s.replace(/,/g, ""));
  }).filter((n) => Number.isFinite(n) && n > 0);
}

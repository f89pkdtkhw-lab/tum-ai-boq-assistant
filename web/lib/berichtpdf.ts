// The review report as a real PDF file (Export → Save PDF). Uses the dependency-free writer in lib/pdf.ts.
import type { Finding, Pruefbericht } from "./api";
import { befundAnzeige } from "./befundtext";
import type { Sprache } from "./i18n";
import { A4, PdfSchreiber, umbrechen } from "./pdf";
import type { Preisbericht } from "./preisbericht";

type Uebersetzer = (text: string, werte?: Record<string, string | number>) => string;
type Status = (f: Finding) => string;

const RAND = 36;
const FARBE: Record<Finding["schwere"], [number, number, number]> = {
  kritisch: [0.85, 0.18, 0.13], hoch: [0.94, 0.55, 0], mittel: [0.6, 0.42, 0], niedrig: [0.4, 0.6, 0.2],
};
const NAME: Record<Finding["schwere"], string> = { kritisch: "Critical", hoch: "High", mittel: "Medium", niedrig: "Low" };
const GRAU: [number, number, number] = [0.37, 0.41, 0.47];
// Column x positions and widths (A4 portrait, 523 pt usable).
const SPALTEN = [
  { titel: "OZ", x: RAND, b: 58 }, { titel: "Severity", x: RAND + 60, b: 46 }, { titel: "Finding", x: RAND + 108, b: 205 },
  { titel: "Suggestion", x: RAND + 316, b: 140 }, { titel: "Euro impact", x: RAND + 459, b: 64 },
];

/** `preis`: the estimated price report (final estimated price and changed items), shown before the findings. */
export function berichtPdf(bericht: Pruefbericht, opt: { t: Uebersetzer; sprache: Sprache; status: Status; titel?: string; datum?: Date; preis?: Preisbericht }): Uint8Array {
  const { t, sprache } = opt;
  // Offline-model placeholders (rule IDs MOCK_*) are not findings and never appear in the PDF.
  const echteBefunde = bericht.findings.filter((f) => !f.regel_id.startsWith("MOCK_"));
  const loc = sprache === "de" ? "de-DE" : "en-GB";
  // The euro sign goes after the number: PDF viewers draw the standard-font "€" wider than its advance,
  // so a digit right after it overlapped ("€65" looked smeared). "65.4M €" has nothing after the sign.
  const mitEuro = (nf: Intl.NumberFormat) => ({ format: (n: number) => `${nf.format(n)} €` });
  const euro = mitEuro(new Intl.NumberFormat(loc, { maximumFractionDigits: 0 }));
  const zahl = new Intl.NumberFormat(loc);
  const euroKurz = mitEuro(new Intl.NumberFormat(loc, { notation: "compact", maximumFractionDigits: 1 }));
  const pdf = new PdfSchreiber();
  let seite = 1;
  let y = RAND;
  const fuss = () => pdf.text(RAND, A4.hoehe - 20, `LV Scout · ${(opt.datum ?? new Date()).toLocaleDateString(loc)} · ${t("Page")} ${seite}`, 8, false, GRAU);

  // Title and source
  pdf.text(RAND, y + 14, opt.titel || bericht.lv.name, 18, true);
  y += 30;
  pdf.text(RAND, y, `${bericht.lv.name} · ${zahl.format(bericht.lv.positionen.length)} ${t("items")} · ${t("Source:")} ${bericht.lv.quelle}`, 9, false, GRAU);
  y += 22;

  // Summary tiles: score and counts from the backend summary (#94), total from the bill
  const z = bericht.zusammenfassung;
  const summe = bericht.lv.positionen.reduce((s, p) => s + (p.gp ?? 0), 0);
  const kacheln: [string, string][] = [
    [t("Score"), z ? `${z.score.toFixed(1)} / 10` : "–"], [t("Big problems"), z ? zahl.format(z.grosse_probleme) : "–"],
    [t("Warnings"), z ? zahl.format(z.warnungen) : "–"], [t("Recommendations"), z ? zahl.format(z.empfehlungen) : "–"],
    [t("Total in the bill"), Math.abs(summe) >= 1e7 ? euroKurz.format(summe) : euro.format(summe)],
  ];
  const kb = (A4.breite - 2 * RAND - 4 * 8) / 5;
  kacheln.forEach(([label, wert], i) => {
    const x = RAND + i * (kb + 8);
    pdf.rechteck(x, y, kb, 44, [0.95, 0.96, 0.97]);
    pdf.text(x + 8, y + 15, label, 8, false, GRAU);
    pdf.text(x + 8, y + 34, wert, 14, true);
  });
  y += 52;
  // Final estimated price (team spec: original vs estimated bill and the difference)
  const preis = opt.preis;
  if (preis) {
    const geld = (n: number) => (Math.abs(n) >= 1e7 ? euroKurz : euro).format(n);
    const preisKacheln: [string, string, [number, number, number]][] = [
      [t("Was"), geld(preis.war), [0.95, 0.96, 0.97]],
      [t("Final estimated price"), preis.von != null && preis.bis != null ? `${geld(preis.geschaetzt)}  (${geld(preis.von)}–${geld(preis.bis)})` : geld(preis.geschaetzt), [0.9, 0.97, 0.92]],
      [t("Difference"), `${preis.diff > 0 ? "+" : ""}${geld(preis.diff)}`, preis.diff > 0 ? [0.99, 0.92, 0.9] : [0.9, 0.97, 0.92]],
      [t("Items with a changed price"), zahl.format(preis.geaendert), [0.95, 0.96, 0.97]],
    ];
    const pb = (A4.breite - 2 * RAND - 3 * 8) / 4;
    preisKacheln.forEach(([label, wert, farbe], i) => {
      const x = RAND + i * (pb + 8);
      pdf.rechteck(x, y, pb, 44, farbe);
      pdf.text(x + 8, y + 15, label, 8, false, GRAU);
      pdf.text(x + 8, y + 34, wert, 14, true);
    });
    y += 52;
  }
  y += 10;

  // Estimated price report: changed items, largest difference first (all items are in the Excel export)
  if (preis && preis.geaendert > 0) {
    const MAX = 150;
    const zeilen = preis.zeilen.filter((r) => r.war && r.diff && Math.abs(r.diff) / Math.abs(r.war) >= .02)
      .sort((a, b) => Math.abs(b.diff ?? 0) - Math.abs(a.diff ?? 0));
    const PS = [{ titel: "OZ", x: RAND, b: 58 }, { titel: "Item", x: RAND + 60, b: 150 }, { titel: "Was", x: RAND + 212, b: 70 },
      { titel: "Estimated", x: RAND + 284, b: 70 }, { titel: "±", x: RAND + 356, b: 62 }, { titel: "Why", x: RAND + 420, b: 103 }];
    const preisKopf = () => {
      pdf.rechteck(RAND, y, A4.breite - 2 * RAND, 18, [0.11, 0.17, 0.31]);
      PS.forEach((s) => pdf.text(s.x + 3, y + 12.5, t(s.titel), 8, true, [1, 1, 1]));
      y += 22;
    };
    pdf.text(RAND, y + 4, `${t("Estimated price report")} (${zahl.format(Math.min(MAX, zeilen.length))} ${t("of")} ${zahl.format(zeilen.length)} ${t("changed items")})`, 12, true);
    y += 14;
    preisKopf();
    const rechts = (x: number, b: number, text: string, yy: number, farbe?: [number, number, number]) => pdf.text(x + b - 3 - text.length * 4.1, yy, text, 8, false, farbe);
    for (const r of zeilen.slice(0, MAX)) {
      const item = umbrechen(r.kurztext, PS[1].b - 6, 8).slice(0, 2);
      const grund = umbrechen(t(r.grund, r.werte), PS[5].b - 6, 7.5).slice(0, 2);
      const hoehe = Math.max(item.length, grund.length) * 10 + 6;
      if (y + hoehe > A4.hoehe - 40) { fuss(); pdf.neueSeite(); seite++; y = RAND; preisKopf(); }
      pdf.rechteck(RAND, y - 2, 3, hoehe - 4, [0.96, 0.77, 0.09]);
      pdf.text(PS[0].x + 6, y + 8, r.oz, 8);
      item.forEach((l, i) => pdf.text(PS[1].x + 3, y + 8 + i * 10, l, 8));
      rechts(PS[2].x, PS[2].b, euro.format(r.war ?? 0), y + 8);
      const geschaetztText = r.von != null && r.bis != null
        ? `${euro.format(r.geschaetzt ?? 0)} (${euro.format(r.von)}–${euro.format(r.bis)})`
        : euro.format(r.geschaetzt ?? 0);
      rechts(PS[3].x, PS[3].b, geschaetztText, y + 8);
      rechts(PS[4].x, PS[4].b, `${(r.diff ?? 0) > 0 ? "+" : ""}${euro.format(r.diff ?? 0)}`, y + 8, (r.diff ?? 0) > 0 ? [0.85, 0.18, 0.13] : [0.13, 0.6, 0.3]);
      grund.forEach((l, i) => pdf.text(PS[5].x + 3, y + 8 + i * 9, l, 7.5, false, GRAU));
      y += hoehe;
      pdf.linie(RAND, y - 4, A4.breite - RAND);
    }
    if (zeilen.length > MAX) { pdf.text(RAND, y + 6, t("All items are in the Excel export."), 8, false, GRAU); y += 14; }
    y += 14;
    if (y > A4.hoehe - 120) { fuss(); pdf.neueSeite(); seite++; y = RAND; }
  }

  // Findings table
  const kopf = () => {
    pdf.rechteck(RAND, y, A4.breite - 2 * RAND, 18, [0.11, 0.17, 0.31]);
    SPALTEN.forEach((s) => pdf.text(s.x + 3, y + 12.5, t(s.titel), 8, true, [1, 1, 1]));
    y += 22;
  };
  pdf.text(RAND, y + 4, `${t("Findings")} (${zahl.format(echteBefunde.length)})`, 12, true);
  y += 14;
  kopf();
  for (const roh of echteBefunde) {
    const f = befundAnzeige(roh, sprache);
    const status = opt.status(roh);
    const finding = umbrechen(f.titel, SPALTEN[2].b - 6, 8.5, true);
    // Long explanations (e.g. lists of item numbers) are cut to keep the PDF readable; app and Excel keep the full text.
    const kurz = (zeilen: string[], max: number) => (zeilen.length > max ? [...zeilen.slice(0, max - 1), `${zeilen[max - 1]} …`] : zeilen);
    const why = kurz(umbrechen(f.begruendung, SPALTEN[2].b - 6, 7.5), 4);
    const vorschlag = kurz(umbrechen(`${f.vorschlag}${status ? `  [${status}]` : ""}`, SPALTEN[3].b - 6, 7.5), 5);
    const hoehe = Math.max(finding.length * 10.5 + why.length * 9, vorschlag.length * 9, 12) + 8;
    if (y + hoehe > A4.hoehe - 40) { fuss(); pdf.neueSeite(); seite++; y = RAND; kopf(); }
    pdf.rechteck(RAND, y - 2, 3, hoehe - 4, FARBE[f.schwere]);
    pdf.text(SPALTEN[0].x + 6, y + 8, f.oz, 8);
    pdf.text(SPALTEN[1].x + 3, y + 8, t(NAME[f.schwere]), 8, true, FARBE[f.schwere]);
    let yy = y + 8;
    for (const l of finding) { pdf.text(SPALTEN[2].x + 3, yy, l, 8.5, true); yy += 10.5; }
    for (const l of why) { pdf.text(SPALTEN[2].x + 3, yy, l, 7.5, false, GRAU); yy += 9; }
    vorschlag.forEach((l, i) => pdf.text(SPALTEN[3].x + 3, y + 8 + i * 9, l, 7.5));
    const e = f.euro_wirkung === null ? "–" : euro.format(f.euro_wirkung);
    pdf.text(SPALTEN[4].x + SPALTEN[4].b - 3 - e.length * 4.2, y + 8, e, 8);
    y += hoehe;
    pdf.linie(RAND, y - 4, A4.breite - RAND);
  }
  fuss();
  return pdf.bytes();
}

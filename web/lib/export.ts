// Export helpers for /export (#15): read a stored Pruefbericht and write it as XLSX without dependencies.
import type { PreisZeile, Preisbericht } from "./preisbericht";
import type { Finding, Pruefbericht } from "@/lib/api";
import { bewertungVon, statusName, type Bewertungen } from "./bewertung";
import { bieterfragen } from "./bieterfragen";
import { mengenSummen } from "./mengen";
import { statusInfo } from "./kalkulation";
import { schlussTabelle } from "./schlussbericht";

export const MOCK_REGEL = "MOCK_LLM";

/** Parses a stored or uploaded report; returns null if it is not a Pruefbericht. */
export function leseBericht(text: string | null): Pruefbericht | null {
  if (!text) return null;
  try {
    const b = JSON.parse(text);
    const ok = b && typeof b === "object" && b.lv && typeof b.lv.name === "string" && Array.isArray(b.lv.positionen)
      && Array.isArray(b.findings) && b.kennzahlen && typeof b.kennzahlen === "object";
    return ok ? (b as Pruefbericht) : null;
  } catch {
    return null;
  }
}

export const istMock = (f: Finding) => f.regel_id.startsWith("MOCK_"); // contract: all mock rule IDs start with MOCK_

const CATEGORY_LABELS = { fehler: "Error", risiko: "Risk", nachtrag: "Change order" };
const SEVERITY_LABELS = { kritisch: "Critical", hoch: "High", mittel: "Medium", niedrig: "Low" };
const ITEM_TYPE_LABELS = { normal: "Standard item", bedarf: "Optional item", alternativ: "Alternative item", zulage: "Supplement item", pauschal: "Lump sum item", stundenlohn: "Hourly rate item" };

type Zelle = string | number | null;
/** Row colour of the priced/estimated bill (#117); same meaning as in the report (#116). */
export type ZeilenStil = "added" | "removed" | "updated" | "summe";
export type Tabelle = { name: string; zeilen: Zelle[][]; stile?: (ZeilenStil | undefined)[] };

/** Priced and estimated bill sheets; only the ones whose fields exist (#117). */
function kalkulationsTabellen(bericht: Pruefbericht): Tabelle[] {
  const blaetter: Tabelle[] = [];
  const k = bericht.kalkulation;
  if (k) {
    const kurztext = new Map(bericht.lv.positionen.map((p) => [p.oz, p.kurztext]));
    const mwst = `${Math.round(k.mwst_satz * 1000) / 10} %`;
    blaetter.push({
      name: "Priced bill",
      zeilen: [
        ["OZ", "Short description", "Quantity", "Unit", "Unit price (EUR)", "Total (EUR)", "Price-list match", "BoQ unit price (EUR)", "BoQ total (EUR)", "Range low (EUR)", "Range high (EUR)"],
        ...k.positionen.map((p) => [p.oz, p.kurztext || kurztext.get(p.oz) || "", p.menge, p.einheit, p.ep, p.gp,
          p.treffer === "kein_treffer" ? "no price" : p.treffer === "index" ? "estimated (index)" : p.treffer === "recherche" ? "estimated (research)" : p.treffer, p.ep_lv, p.gp_lv,
          p.ep_von ?? null, p.ep_bis ?? null]),
        ["Net", "", null, "", null, k.summe_netto, "", null, null, null, null],
        [`Gross (VAT ${mwst})`, "", null, "", null, k.summe_brutto, "", null, null, null, null],
        ["Without price", "", k.ohne_preis, "items", null, null, "", null, null, null, null],
      ],
      stile: [undefined, ...k.positionen.map(() => undefined), "summe", "summe", "summe"],
    });
  }
  const g = bericht.geschaetztes_lv;
  if (g) {
    blaetter.push({
      name: "Estimated bill",
      zeilen: [
        ["Status", "OZ", "Short description", "Unit", "Quantity old", "Quantity new", "Unit price (EUR)", "Total old (EUR)", "Total new (EUR)", "Reason", "Approval required", "Range low (EUR)", "Range high (EUR)"],
        ...g.positionen.map((p) => [statusInfo(p.status).marke, p.oz, p.kurztext, p.einheit, p.menge_alt, p.menge_neu, p.ep, p.gp_alt, p.gp_neu,
          p.grund, p.freigabe_noetig ? "yes" : "", p.gp_von ?? null, p.gp_bis ?? null]),
        ["Net", "", "", "", null, null, null, g.summe_netto - g.differenz_netto, g.summe_netto, "", "", g.summe_netto_von ?? null, g.summe_netto_bis ?? null],
        ["Gross", "", "", "", null, null, null, null, g.summe_brutto, "", "", null, null],
        ["Difference net", "", `${g.differenz_prozent > 0 ? "+" : ""}${g.differenz_prozent} %`, "", null, null, null, null, g.differenz_netto, "", "", null, null],
      ],
      stile: [undefined, ...g.positionen.map((p) => (p.status === "unchanged" ? undefined : p.status)), "summe", "summe", "summe"],
    });
  }
  return blaetter;
}

/** Fills "{name}" placeholders of a price-report reason (English in the file). */
const grundText = (z: PreisZeile) => z.grund.replace(/\{(\w+)\}/g, (_, k) => String(z.werte?.[k] ?? ""));

/** Sheets of the Excel export; with `preis` it starts with a summary and the estimated price report (final estimated price). */
export function tabellen(bericht: Pruefbericht, bewertungen: Bewertungen = {}, preis?: Preisbericht): Tabelle[] {
  const positionen: Zelle[][] = [
    ["OZ", "Short description", "Detailed description", "Quantity", "Unit", "Unit price (EUR)", "Total price (EUR)", "Type", "Title"],
    ...bericht.lv.positionen.map((p) => [p.oz, p.kurztext, p.langtext, p.menge, p.einheit, p.ep, p.gp, ITEM_TYPE_LABELS[p.typ], p.titel_pfad.join(" › ")]),
  ];
  const befunde: Zelle[][] = [
    ["OZ", "Category", "Severity", "Title", "Explanation", "Suggestion", "Source", "Rule", "Euro impact (EUR)", "Review status", "Comment"],
    ...bericht.findings.filter((f) => !istMock(f)).map((f) => [
      f.oz, CATEGORY_LABELS[f.kategorie], SEVERITY_LABELS[f.schwere], f.titel, f.begruendung, f.vorschlag, f.quelle === "regel" ? "Rule" : "Model", f.regel_id, f.euro_wirkung,
      statusName(bewertungVon(bewertungen, f.id).status), bewertungVon(bewertungen, f.id).kommentar,
    ]),
  ];
  const m = mengenSummen(bericht.lv.positionen);
  const mengen: Zelle[][] = [
    ["Scope", "Title", "Unit", "Quantity", "Items"],
    ...m.einheiten.map((e) => ["Total", "", e.einheit, e.summe, e.positionen]),
    ...m.titel.flatMap((t) => m.einheiten.filter((e) => e.schluessel in t.summen).map((e) => ["Title", t.titel, e.einheit, t.summen[e.schluessel], null])),
    ...(m.ausserVertrag ? [["Excluded: optional or alternative", "", "", null, m.ausserVertrag]] : []),
    ...(m.ohneMenge ? [["Excluded: no quantity or unit", "", "", null, m.ohneMenge]] : []),
  ];
  const fragen: Zelle[][] = [
    ["OZ", "Short description", "Title", "Question"],
    ...bieterfragen(bericht.findings, bericht.lv.positionen).map((f) => [f.oz, f.kurztext, f.titel, f.frage]),
  ];
  const z = bericht.zusammenfassung;
  const zusammenfassung: Zelle[][] = [
    ["Measure", "Value"],
    ["Score (out of 10)", z?.score ?? null], ["Big problems", z?.grosse_probleme ?? null], ["Warnings", z?.warnungen ?? null],
    ["Recommendations", z?.empfehlungen ?? null], ["Items", bericht.lv.positionen.length],
    ...(preis ? [["Total in the bill, was (EUR)", preis.war], ["Final estimated price (EUR)", preis.geschaetzt],
      ...(preis.von != null && preis.bis != null ? [["Estimate range (EUR)", `${preis.von} – ${preis.bis}`]] as Zelle[][] : []),
      ["Difference (EUR)", preis.diff], ["Items with a changed price", preis.geaendert]] as Zelle[][] : []),
  ];
  const preise: Zelle[][] = preis ? [
    ["OZ", "Item", "Quantity", "Unit", "Was (EUR)", "Estimated (EUR)", "Difference (EUR)", "Why", "Range low (EUR)", "Range high (EUR)", "Source"],
    ...preis.zeilen.map((r) => [r.oz, r.kurztext, r.menge, r.einheit, r.war, r.geschaetzt, r.diff, grundText(r), r.von ?? null, r.bis ?? null, r.quelle ?? ""]),
    ["Total", "", null, "", preis.war, preis.geschaetzt, preis.diff, "", preis.von ?? null, preis.bis ?? null, ""],
  ] : [];
  return [
    ...(preis ? [{ name: "Summary", zeilen: zusammenfassung }, { name: "Estimated prices", zeilen: preise }] : []),
    { name: "Findings", zeilen: befunde }, { name: "Items", zeilen: positionen },
    { name: "Quantities", zeilen: mengen }, { name: "Bidder questions", zeilen: fragen },
    ...kalkulationsTabellen(bericht),
    ...schlussBlatt(bericht),
  ];
}

/** "Final report" sheet (#167): every item with problems, ± approximation, need to add and recommendations. */
function schlussBlatt(bericht: Pruefbericht): Tabelle[] {
  const zeilen = schlussTabelle(bericht);
  return zeilen ? [{ name: "Final report", zeilen }] : [];
}

// ---------- XLSX (Office Open XML) ----------

const xml = (s: string) =>
  // drop characters XML 1.0 forbids, then escape
  s.replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g, "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]!);

function spalte(i: number) {
  let s = "";
  for (i += 1; i > 0; i = Math.floor((i - 1) / 26)) s = String.fromCharCode(65 + ((i - 1) % 26)) + s;
  return s;
}

/** cellXfs ids in styles.xml: [text, number] per row colour. Removed rows also strike the font through. */
export const STIL_IDS: Record<ZeilenStil, [number, number]> = { added: [3, 4], removed: [5, 6], updated: [7, 8], summe: [2, 9] };

function blatt(zeilen: Zelle[][], stile: (ZeilenStil | undefined)[] = []) {
  const rows = zeilen.map((zeile, r) => {
    const stil = stile[r] ? STIL_IDS[stile[r]!] : null;
    const cells = zeile.map((wert, c) => {
      const ref = `${spalte(c)}${r + 1}`;
      // Coloured rows fill empty cells too, so the whole row shows its status.
      if (wert === null || wert === "") return stil ? `<c r="${ref}" s="${stil[1]}"/>` : "";
      if (typeof wert === "number") return `<c r="${ref}"${stil ? ` s="${stil[1]}"` : ""}><v>${wert}</v></c>`;
      // Inline strings are never evaluated as formulas; quotePrefix style (s="1") keeps "=…" text as text when edited.
      return `<c r="${ref}" t="inlineStr" s="${stil ? stil[0] : r === 0 ? 2 : 1}"><is><t xml:space="preserve">${xml(wert)}</t></is></c>`;
    }).join("");
    return `<row r="${r + 1}">${cells}</row>`;
  }).join("");
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><sheetData>${rows}</sheetData></worksheet>`;
}

export function xlsxDateien(bericht: Pruefbericht, bewertungen: Bewertungen = {}, preis?: Preisbericht): Record<string, string> {
  const blaetter = tabellen(bericht, bewertungen, preis);
  const dateien: Record<string, string> = {
    "[Content_Types].xml": `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>${blaetter.map((_, i) => `<Override PartName="/xl/worksheets/sheet${i + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>`).join("")}</Types>`,
    "_rels/.rels": `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>`,
    "xl/workbook.xml": `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>${blaetter.map((b, i) => `<sheet name="${xml(b.name)}" sheetId="${i + 1}" r:id="rId${i + 1}"/>`).join("")}</sheets></workbook>`,
    "xl/_rels/workbook.xml.rels": `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">${blaetter.map((_, i) => `<Relationship Id="rId${i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet${i + 1}.xml"/>`).join("")}<Relationship Id="rId${blaetter.length + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>`,
    "xl/styles.xml": `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="3"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font><font><strike/><sz val="11"/><color rgb="FF9B1C1C"/><name val="Calibri"/></font></fonts><fills count="5"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FFD1FAE5"/><bgColor indexed="64"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFFEE2E2"/><bgColor indexed="64"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFFEF3C7"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs><cellXfs count="10"><xf/><xf quotePrefix="1" applyAlignment="1"><alignment wrapText="1" vertical="top"/></xf><xf fontId="1" applyFont="1" quotePrefix="1"/><xf fillId="2" applyFill="1" quotePrefix="1"/><xf fillId="2" applyFill="1"/><xf fillId="3" fontId="2" applyFill="1" applyFont="1" quotePrefix="1"/><xf fillId="3" fontId="2" applyFill="1" applyFont="1"/><xf fillId="4" applyFill="1" quotePrefix="1"/><xf fillId="4" applyFill="1"/><xf fontId="1" applyFont="1"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>`,
  };
  blaetter.forEach((b, i) => { dateien[`xl/worksheets/sheet${i + 1}.xml`] = blatt(b.zeilen, b.stile); });
  return dateien;
}

// ---------- minimal ZIP writer (store, no compression) ----------

const CRC_TABELLE = Array.from({ length: 256 }, (_, n) => {
  let c = n;
  for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  return c >>> 0;
});
function crc32(daten: Uint8Array) {
  let c = 0xffffffff;
  for (const byte of daten) c = CRC_TABELLE[(c ^ byte) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

export function zip(dateien: Record<string, string>): Uint8Array {
  const enc = new TextEncoder();
  const teile: Uint8Array[] = [];
  const zentral: Uint8Array[] = [];
  let offset = 0;
  for (const [name, inhalt] of Object.entries(dateien)) {
    const n = enc.encode(name), d = enc.encode(inhalt), crc = crc32(d);
    const kopf = new DataView(new ArrayBuffer(30));
    [[0, 0x04034b50, 4], [4, 20, 2], [6, 0x0800, 2], [8, 0, 2], [14, crc, 4], [18, d.length, 4], [22, d.length, 4], [26, n.length, 2]]
      .forEach(([o, v, l]) => (l === 4 ? kopf.setUint32(o, v, true) : kopf.setUint16(o, v, true)));
    const z = new DataView(new ArrayBuffer(46));
    [[0, 0x02014b50, 4], [4, 20, 2], [6, 20, 2], [8, 0x0800, 2], [16, crc, 4], [20, d.length, 4], [24, d.length, 4], [28, n.length, 2], [42, offset, 4]]
      .forEach(([o, v, l]) => (l === 4 ? z.setUint32(o, v, true) : z.setUint16(o, v, true)));
    teile.push(new Uint8Array(kopf.buffer), n, d);
    zentral.push(new Uint8Array(z.buffer), n);
    offset += 30 + n.length + d.length;
  }
  const groesse = zentral.reduce((s, t) => s + t.length, 0);
  const ende = new DataView(new ArrayBuffer(22));
  const anzahl = Object.keys(dateien).length;
  [[0, 0x06054b50, 4], [8, anzahl, 2], [10, anzahl, 2], [12, groesse, 4], [16, offset, 4]]
    .forEach(([o, v, l]) => (l === 4 ? ende.setUint32(o, v, true) : ende.setUint16(o, v, true)));
  const alle = [...teile, ...zentral, new Uint8Array(ende.buffer)];
  const out = new Uint8Array(alle.reduce((s, t) => s + t.length, 0));
  let p = 0;
  for (const t of alle) { out.set(t, p); p += t.length; }
  return out;
}

export const xlsx = (bericht: Pruefbericht, bewertungen: Bewertungen = {}, preis?: Preisbericht) => zip(xlsxDateien(bericht, bewertungen, preis));

export function dateiname(name: string, endung: string) {
  const basis = name.normalize("NFKD").replace(/[^\w-]+/g, "-").replace(/^-+|-+$/g, "").toLowerCase();
  return `pruefbericht-${basis || "lv"}.${endung}`;
}

// ---------- PDF download (#105): content only; Export.tsx draws it with jsPDF ----------

/** jsPDF's built-in fonts only cover WinAnsi: map the few symbols we use, drop what cannot be drawn. */
export function pdfText(s: string): string {
  return s.replace(/→/g, "->").replace(/[−‐‑]/g, "-").replace(/[⁠​]/g, "").replace(/[^\x09\x0A\x0D\x20-\x7E\xA0-\xFF€–—‘’‚“”„†‡•…‰‹›ŠšŽžŒœŸƒˆ˜™]/g, "?");
}

export type PdfAbschnitt = { name: string; kopf: string[]; zeilen: string[][] };
export type PdfInhalt = { titel: string; quelle: string; zusammenfassung: string[]; abschnitte: PdfAbschnitt[] };

type MitBerichten = Pruefbericht & { berichte?: { titel: string; status: string; meldung: string; finding_ids: string[] }[] | null };

const pdfZahl = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 3 });

/** Same sheets and rows as the XLSX, plus the summary and the three report sections when present. */
export function pdfInhalt(bericht: MitBerichten, bewertungen: Bewertungen = {}): PdfInhalt {
  const k = bericht.kennzahlen;
  const z = bericht.zusammenfassung;
  const zusammenfassung = [
    `Items: ${pdfZahl.format(bericht.lv.positionen.length)} · Entries: ${pdfZahl.format(bericht.findings.filter((f) => !istMock(f)).length)} · Critical: ${pdfZahl.format(k.kritisch)}`,
    ...(z ? [
      `Score: ${z.score.toFixed(1)} / 10 · Big problems: ${z.grosse_probleme} · Warnings: ${z.warnungen} · Notices: ${z.hinweise} · Recommendations: ${z.empfehlungen}`,
      `Estimate deviation: ${z.schaetzung_abweichung_eur === null ? "not connected" : `${pdfZahl.format(z.schaetzung_abweichung_eur)} EUR`}${z.schaetzung_von != null && z.schaetzung_bis != null ? ` · Range: ${pdfZahl.format(z.schaetzung_von)}–${pdfZahl.format(z.schaetzung_bis)} EUR` : ""}`,
      ...z.score_abzuege.map((a) => `Deduction ${a.punkte.toFixed(1)}: ${a.grund}`),
    ] : []),
  ];
  const zelle = (w: string | number | null) => (w === null ? "" : typeof w === "number" ? pdfZahl.format(w) : w);
  const abschnitte: PdfAbschnitt[] = [];
  if (bericht.berichte?.length) {
    abschnitte.push({
      name: "Reports",
      kopf: ["Report", "Status", "Findings", "Message"],
      zeilen: bericht.berichte.map((b) => [b.titel, b.status === "ok" ? "ok" : b.status === "nicht_verbunden" ? "not connected" : "failed", String(b.finding_ids.length), b.meldung]),
    });
  }
  for (const t of tabellen(bericht, bewertungen)) {
    const [kopf, ...zeilen] = t.zeilen;
    abschnitte.push({ name: t.name, kopf: kopf.map(zelle), zeilen: zeilen.map((r) => r.map(zelle)) });
  }
  const text = (s: string) => pdfText(s);
  return {
    titel: text(bericht.lv.name || "Unnamed BoQ"), quelle: text(bericht.lv.quelle || ""),
    zusammenfassung: zusammenfassung.map(text),
    abschnitte: abschnitte.map((a) => ({ name: text(a.name), kopf: a.kopf.map(text), zeilen: a.zeilen.map((r) => r.map(text)) })),
  };
}

/** review-report-<lv-name>-<YYYY-MM-DD>.pdf */
export function pdfDateiname(name: string, heute: Date = new Date()): string {
  const basis = name.normalize("NFKD").replace(/[^\w-]+/g, "-").replace(/^-+|-+$/g, "").toLowerCase();
  return `review-report-${basis || "lv"}-${heute.toISOString().slice(0, 10)}.pdf`;
}

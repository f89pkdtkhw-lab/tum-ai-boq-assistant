// Export helpers for /export (#15): read a stored Pruefbericht and write it as XLSX without dependencies.
import type { Finding, Pruefbericht } from "@/lib/api";

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

export const istMock = (f: Finding) => f.regel_id === MOCK_REGEL;

type Zelle = string | number | null;

export function tabellen(bericht: Pruefbericht): { name: string; zeilen: Zelle[][] }[] {
  const positionen: Zelle[][] = [
    ["OZ", "Kurztext", "Langtext", "Menge", "Einheit", "EP (EUR)", "GP (EUR)", "Typ", "Titel"],
    ...bericht.lv.positionen.map((p) => [p.oz, p.kurztext, p.langtext, p.menge, p.einheit, p.ep, p.gp, p.typ, p.titel_pfad.join(" › ")]),
  ];
  const befunde: Zelle[][] = [
    ["OZ", "Kategorie", "Schwere", "Titel", "Begründung", "Vorschlag", "Quelle", "Regel", "Euro-Wirkung (EUR)", "Hinweis"],
    ...bericht.findings.map((f) => [
      f.oz, f.kategorie, f.schwere, f.titel, f.begruendung, f.vorschlag, f.quelle, f.regel_id, f.euro_wirkung,
      istMock(f) ? "Demonstration (Mock), kein fachlicher Befund" : "",
    ]),
  ];
  return [{ name: "Befunde", zeilen: befunde }, { name: "Positionen", zeilen: positionen }];
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

function blatt(zeilen: Zelle[][]) {
  const rows = zeilen.map((zeile, r) => {
    const cells = zeile.map((wert, c) => {
      const ref = `${spalte(c)}${r + 1}`;
      if (wert === null || wert === "") return "";
      if (typeof wert === "number") return `<c r="${ref}"><v>${wert}</v></c>`;
      // Inline strings are never evaluated as formulas; quotePrefix style (s="1") keeps "=…" text as text when edited.
      return `<c r="${ref}" t="inlineStr" s="${r === 0 ? 2 : 1}"><is><t xml:space="preserve">${xml(wert)}</t></is></c>`;
    }).join("");
    return `<row r="${r + 1}">${cells}</row>`;
  }).join("");
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><sheetData>${rows}</sheetData></worksheet>`;
}

export function xlsxDateien(bericht: Pruefbericht): Record<string, string> {
  const blaetter = tabellen(bericht);
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
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts><fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs><cellXfs count="3"><xf/><xf quotePrefix="1" applyAlignment="1"><alignment wrapText="1" vertical="top"/></xf><xf fontId="1" applyFont="1" quotePrefix="1"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>`,
  };
  blaetter.forEach((b, i) => { dateien[`xl/worksheets/sheet${i + 1}.xml`] = blatt(b.zeilen); });
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

export const xlsx = (bericht: Pruefbericht) => zip(xlsxDateien(bericht));

export function dateiname(name: string, endung: string) {
  const basis = name.normalize("NFKD").replace(/[^\w-]+/g, "-").replace(/^-+|-+$/g, "").toLowerCase();
  return `pruefbericht-${basis || "lv"}.${endung}`;
}

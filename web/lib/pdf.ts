// Minimal PDF writer without dependencies (issue #105 "real PDF download"): A4 pages, Helvetica / Helvetica-Bold
// in WinAnsi encoding (covers German umlauts, ß and €), text, filled rectangles and simple word wrapping.
// shortcut: text widths are estimated per character class, not read from font metrics; good enough for table cells.

export const A4 = { breite: 595.28, hoehe: 841.89 };
type Farbe = [number, number, number];

// WinAnsi code points for characters outside Latin-1 that reports use.
const WIN_ANSI: Record<string, number> = {
  "€": 0x80, "‚": 0x82, "„": 0x84, "…": 0x85, "‘": 0x91, "’": 0x92, "“": 0x93, "”": 0x94, "•": 0x95, "–": 0x96, "—": 0x97, "™": 0x99,
};

function kodiere(text: string): number[] {
  const out: number[] = [];
  for (const ch of text.normalize("NFC")) {
    const c = ch.codePointAt(0)!;
    if (WIN_ANSI[ch] !== undefined) out.push(WIN_ANSI[ch]);
    else if (ch === "−") out.push(0x2d);
    else if (ch === "≥") out.push(...[0x3e, 0x3d]);
    else if (ch === "≤") out.push(...[0x3c, 0x3d]);
    else if (ch === "±") out.push(0xb1);
    else if (c >= 0x20 && c <= 0xff && !(c >= 0x7f && c <= 0x9f)) out.push(c);
    else out.push(0x3f); // "?"
  }
  return out;
}

/** Estimated width of text in points (Helvetica-like proportions). */
export function breite(text: string, groesse: number, fett = false): number {
  let w = 0;
  for (const ch of text) {
    w += /[ilI.,;:'|!jtf ]/.test(ch) ? .28 : /[mwMW@%]/.test(ch) ? .86 : /[A-ZÄÖÜ0-9€]/.test(ch) ? .64 : .52;
  }
  return w * groesse * (fett ? 1.05 : 1);
}

/** Splits text into lines that fit the width; very long words are cut. */
export function umbrechen(text: string, maxBreite: number, groesse: number, fett = false): string[] {
  const zeilen: string[] = [];
  for (const absatz of text.split("\n")) {
    let zeile = "";
    for (const wort of absatz.split(/\s+/).filter(Boolean)) {
      const probe = zeile ? `${zeile} ${wort}` : wort;
      if (breite(probe, groesse, fett) <= maxBreite) { zeile = probe; continue; }
      if (zeile) zeilen.push(zeile);
      let rest = wort;
      while (breite(rest, groesse, fett) > maxBreite) {
        let n = rest.length;
        while (n > 1 && breite(rest.slice(0, n), groesse, fett) > maxBreite) n--;
        zeilen.push(rest.slice(0, n));
        rest = rest.slice(n);
      }
      zeile = rest;
    }
    zeilen.push(zeile);
  }
  return zeilen;
}

const str = (text: string) => kodiere(text).map((b) => (b === 0x28 || b === 0x29 || b === 0x5c ? `\\${String.fromCharCode(b)}` : String.fromCharCode(b))).join("");
const zahl = (n: number) => (Math.round(n * 100) / 100).toString();

export class PdfSchreiber {
  private seiten: string[] = [];
  private aktuell = "";

  constructor() { this.neueSeite(); }

  neueSeite() {
    if (this.aktuell) this.seiten.push(this.aktuell);
    this.aktuell = "";
  }

  /** Text at (x, y) from the top-left corner, like screen coordinates. */
  text(x: number, y: number, text: string, groesse = 10, fett = false, farbe: Farbe = [0.11, 0.17, 0.31]) {
    this.aktuell += `BT /${fett ? "F2" : "F1"} ${groesse} Tf ${farbe.map(zahl).join(" ")} rg ${zahl(x)} ${zahl(A4.hoehe - y)} Td (${str(text)}) Tj ET\n`;
  }

  rechteck(x: number, y: number, b: number, h: number, farbe: Farbe) {
    this.aktuell += `${farbe.map(zahl).join(" ")} rg ${zahl(x)} ${zahl(A4.hoehe - y - h)} ${zahl(b)} ${zahl(h)} re f\n`;
  }

  linie(x1: number, y: number, x2: number, farbe: Farbe = [0.85, 0.87, 0.9]) {
    this.aktuell += `${farbe.map(zahl).join(" ")} RG 0.5 w ${zahl(x1)} ${zahl(A4.hoehe - y)} m ${zahl(x2)} ${zahl(A4.hoehe - y)} l S\n`;
  }

  /** The finished file as bytes. */
  bytes(): Uint8Array {
    const seiten = [...this.seiten, this.aktuell];
    const objekte: string[] = [];
    const n = seiten.length;
    // 1 catalog, 2 pages, 3 F1, 4 F2, then per page: page object + content stream
    objekte.push("<< /Type /Catalog /Pages 2 0 R >>");
    objekte.push(`<< /Type /Pages /Count ${n} /Kids [${seiten.map((_, i) => `${5 + i * 2} 0 R`).join(" ")}] >>`);
    objekte.push("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>");
    objekte.push("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>");
    seiten.forEach((inhalt, i) => {
      objekte.push(`<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${A4.breite} ${A4.hoehe}] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents ${6 + i * 2} 0 R >>`);
      objekte.push(`<< /Length ${inhalt.length} >>\nstream\n${inhalt}endstream`);
    });
    // Every character above is a single byte (WinAnsi), so string length = byte length.
    let pdf = "%PDF-1.4\n%\xe2\xe3\xcf\xd3\n";
    const versatz: number[] = [];
    objekte.forEach((o, i) => { versatz.push(pdf.length); pdf += `${i + 1} 0 obj\n${o}\nendobj\n`; });
    const xref = pdf.length;
    pdf += `xref\n0 ${objekte.length + 1}\n0000000000 65535 f \n${versatz.map((v) => `${String(v).padStart(10, "0")} 00000 n \n`).join("")}`;
    pdf += `trailer\n<< /Size ${objekte.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
    return Uint8Array.from(pdf, (c) => c.charCodeAt(0) & 0xff);
  }
}

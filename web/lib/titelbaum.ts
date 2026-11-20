import type { Finding, Position } from "./api";

type Schwere = Finding["schwere"];

export type Titelknoten = {
  /** Unique key of the node: the joined path; "" for the "Without title" node. */
  schluessel: string;
  titel: string;
  /** Path from the root; empty for the "Without title" node. */
  pfad: string[];
  /** Items in this node and all descendants. */
  positionen: number;
  /** Findings linked to an item of this subtree, each counted once. */
  findings: number;
  maxSchwere: Schwere | null;
  kinder: Titelknoten[];
};

export const OHNE_TITEL_NAME = "Without title";

const RANG: Record<Schwere, number> = { kritisch: 0, hoch: 1, mittel: 2, niedrig: 3 };
const TRENNER = "\u001f";

/** Title path of an item with blank titles dropped. */
export function pfadVon(position: Position): string[] {
  return position.titel_pfad.map((t) => t.trim()).filter(Boolean);
}

function schluesselVon(pfad: string[]) {
  return pfad.join(TRENNER);
}

/**
 * Title tree from `titel_pfad` in BoQ order, "Without title" last.
 * O(items × depth + findings × depth); call once per report.
 */
export function baueTitelbaum(positionen: Position[], findings: Finding[]): Titelknoten[] {
  const wurzeln: Titelknoten[] = [];
  const knoten = new Map<string, Titelknoten>();
  const knotenNachOz = new Map<string, Set<Titelknoten>>();
  let ohneTitel: Titelknoten | null = null;

  for (const position of positionen) {
    const pfad = pfadVon(position);
    const kette: Titelknoten[] = [];
    if (pfad.length === 0) {
      ohneTitel ??= { schluessel: "", titel: OHNE_TITEL_NAME, pfad: [], positionen: 0, findings: 0, maxSchwere: null, kinder: [] };
      kette.push(ohneTitel);
    }
    let geschwister = wurzeln;
    for (let tiefe = 1; tiefe <= pfad.length; tiefe += 1) {
      const teil = pfad.slice(0, tiefe);
      const schluessel = schluesselVon(teil);
      let k = knoten.get(schluessel);
      if (!k) {
        k = { schluessel, titel: teil[tiefe - 1], pfad: teil, positionen: 0, findings: 0, maxSchwere: null, kinder: [] };
        knoten.set(schluessel, k);
        geschwister.push(k);
      }
      kette.push(k);
      geschwister = k.kinder;
    }
    const ziel = knotenNachOz.get(position.oz) ?? new Set();
    for (const k of kette) { k.positionen += 1; ziel.add(k); }
    knotenNachOz.set(position.oz, ziel);
  }

  for (const finding of findings) {
    for (const k of knotenNachOz.get(finding.oz) ?? []) {
      k.findings += 1;
      if (k.maxSchwere === null || RANG[finding.schwere] < RANG[k.maxSchwere]) k.maxSchwere = finding.schwere;
    }
  }

  if (ohneTitel) wurzeln.push(ohneTitel);
  return wurzeln;
}

/** True if the item lies in the subtree at `pfad`; an empty `pfad` means "Without title". */
export function imTeilbaum(position: Position, pfad: string[]): boolean {
  const eigener = pfadVon(position);
  if (pfad.length === 0) return eigener.length === 0;
  return pfad.length <= eigener.length && pfad.every((t, i) => eigener[i] === t);
}

/** OZ of all items in the subtree, for filtering findings. */
export function ozImTeilbaum(positionen: Position[], pfad: string[]): Set<string> {
  return new Set(positionen.filter((p) => imTeilbaum(p, pfad)).map((p) => p.oz));
}

// Person-set review status and comment per finding (#56). Kept only in this browser's localStorage.
import type { Finding } from "./api";

export type Status = "offen" | "bestaetigt" | "verworfen";
export type Bewertung = { status: Status; kommentar: string };
/** Finding id → decision. A finding without an entry is Open with no comment. */
export type Bewertungen = Record<string, Bewertung>;

export const STATUS: { wert: Status; name: string }[] = [
  { wert: "offen", name: "Open" },
  { wert: "bestaetigt", name: "Confirmed" },
  { wert: "verworfen", name: "Dismissed" },
];
export const statusName = (s: Status) => STATUS.find((x) => x.wert === s)?.name ?? s;

const OFFEN: Bewertung = { status: "offen", kommentar: "" };

/** One key per BoQ name; a new format needs a new prefix. */
export const speicherSchluessel = (lvName: string) => `lv-bewertung-v1:${lvName}`;

export const bewertungVon = (b: Bewertungen, id: string): Bewertung => b[id] ?? OFFEN;

/** Returns a new map; Open with an empty (trimmed) comment removes the entry. */
export function setze(b: Bewertungen, id: string, aenderung: Partial<Bewertung>): Bewertungen {
  const alt = bewertungVon(b, id);
  const neu: Bewertung = { status: aenderung.status ?? alt.status, kommentar: (aenderung.kommentar ?? alt.kommentar).trim() };
  const { [id]: _, ...rest } = b;
  return neu.status === "offen" && neu.kommentar === "" ? rest : { ...rest, [id]: neu };
}

/** Parses stored decisions, keeping only valid entries for the given findings. */
export function leseBewertungen(text: string | null, findings: Finding[]): Bewertungen {
  if (!text) return {};
  let roh: unknown;
  try { roh = JSON.parse(text); } catch { return {}; }
  if (!roh || typeof roh !== "object") return {};
  const ids = new Set(findings.map((f) => f.id));
  const gueltig = new Set(STATUS.map((s) => s.wert));
  const aus: Bewertungen = {};
  for (const [id, w] of Object.entries(roh as Record<string, unknown>)) {
    const v = w as Partial<Bewertung> | null;
    if (!ids.has(id) || !v || !gueltig.has(v.status as Status)) continue;
    const kommentar = typeof v.kommentar === "string" ? v.kommentar.trim() : "";
    if (v.status !== "offen" || kommentar) aus[id] = { status: v.status as Status, kommentar };
  }
  return aus;
}

/** Findings the person confirmed or dismissed. */
export const anzahlGeprueft = (findings: Finding[], b: Bewertungen) =>
  findings.filter((f) => bewertungVon(b, f.id).status !== "offen").length;

export function ladeBewertungen(lvName: string, findings: Finding[]): Bewertungen {
  try { return leseBewertungen(window.localStorage.getItem(speicherSchluessel(lvName)), findings); } catch { return {}; }
}

/** Returns false if the browser blocks storage; the page keeps working in memory. */
export function speichereBewertungen(lvName: string, b: Bewertungen): boolean {
  try {
    const schluessel = speicherSchluessel(lvName);
    if (Object.keys(b).length === 0) window.localStorage.removeItem(schluessel);
    else window.localStorage.setItem(schluessel, JSON.stringify(b));
    return true;
  } catch {
    return false;
  }
}

// Local document vault (t243/t247/t248): every bill, regulation, price list and result in one place.
// Backend: api/app/vault.py, files under data/vault/ on the machine that runs the API (git-ignored).

export type VaultTyp = "lv" | "regelwerk" | "preisliste" | "wettbewerb" | "bericht" | "recherche" | "preisrecherche" | "auswertung";
export type VaultEintrag = {
  id: string; typ: VaultTyp; dateiname: string; groesse: number; hash: string; hochgeladen_am: string;
  tags: string[]; projekt: string | null; besitzer: string | null; quelle: string;
  lv_schluessel: string | null; lv_name: string | null; version: number | null;
};
export type VaultTab = "lvs" | "regelwerke" | "preislisten" | "wettbewerb" | "preisdatenbank" | "recherchen" | "historie" | "einreichen";

export const DOKUMENT_TYPEN: VaultTyp[] = ["lv", "regelwerk", "preisliste", "wettbewerb"];
export const ERGEBNIS_TYPEN: VaultTyp[] = ["bericht", "recherche", "preisrecherche", "auswertung"];
export const TABS: { id: VaultTab; label: string; typen?: VaultTyp[] }[] = [
  { id: "lvs", label: "Bills", typen: ["lv"] },
  { id: "regelwerke", label: "Regulations", typen: ["regelwerk"] },
  { id: "preislisten", label: "Price lists", typen: ["preisliste"] },
  { id: "wettbewerb", label: "Competition / margin", typen: ["wettbewerb"] },
  { id: "preisdatenbank", label: "Price database" },
  { id: "recherchen", label: "Research", typen: ERGEBNIS_TYPEN },
  { id: "historie", label: "History" },
  { id: "einreichen", label: "Submit" },
];
export const TYP_LABEL: Record<VaultTyp, string> = {
  lv: "Bill", regelwerk: "Regulation", preisliste: "Price list", wettbewerb: "Competitor bids", bericht: "Analysis report",
  recherche: "Web research", preisrecherche: "Price research", auswertung: "AI evaluation",
};
/** Formats per document type, same as the upload cards in the wizard and on the price database page. */
export const FORMATE: Partial<Record<VaultTyp, string[]>> = {
  lv: [".json", ".x83", ".x84", ".d83", ".d84", ".d86", ".x86", ".xlsx", ".pdf"],
  regelwerk: [".pdf", ".docx", ".txt", ".md"],
  preisliste: [".csv", ".xlsx", ".json", ".x83", ".x84", ".x86", ".d83", ".d84", ".d86"],
  wettbewerb: [".xlsx"],
};

/** `?tab=` of /vault; the old routes (/preise, /history, /einreichen) redirect here. Unknown → bills. */
export function tabAusQuery(wert: string | null | undefined): VaultTab {
  return TABS.some((t) => t.id === wert) ? (wert as VaultTab) : "lvs";
}

/** Wizard role for a stored document ("Choose from vault"). */
export function rolleFuerTyp(typ: VaultTyp): "lv" | "regel" | "preise" | null {
  return typ === "lv" ? "lv" : typ === "regelwerk" ? "regel" : typ === "preisliste" ? "preise" : null;
}

export function groesseText(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function datumText(iso: string, sprache: "de" | "en" = "de"): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString(sprache === "de" ? "de-DE" : "en-GB", { dateStyle: "medium", timeStyle: "short" });
}

/** Search over file name, bill name, tags and project (case-insensitive). */
export function filtereVault(liste: readonly VaultEintrag[], suche: string): VaultEintrag[] {
  const q = suche.trim().toLocaleLowerCase("de");
  if (!q) return [...liste];
  return liste.filter((e) => [e.dateiname, e.lv_name ?? "", e.projekt ?? "", ...e.tags].some((s) => s.toLocaleLowerCase("de").includes(q)));
}

export type LvGruppe = { schluessel: string; name: string; eintraege: VaultEintrag[] };
/** Results grouped by bill, newest first inside each group (version list per bill, t248). */
export function gruppiereNachLv(liste: readonly VaultEintrag[]): LvGruppe[] {
  const gruppen = new Map<string, LvGruppe>();
  for (const e of liste) {
    const schluessel = e.lv_schluessel ?? `name:${e.lv_name ?? ""}`;
    const g = gruppen.get(schluessel) ?? { schluessel, name: e.lv_name || "Without bill", eintraege: [] };
    g.eintraege.push(e);
    gruppen.set(schluessel, g);
  }
  const neu = (a: VaultEintrag, b: VaultEintrag) => b.hochgeladen_am.localeCompare(a.hochgeladen_am);
  return [...gruppen.values()]
    .map((g) => ({ ...g, eintraege: [...g.eintraege].sort(neu) }))
    .sort((a, b) => neu(a.eintraege[0], b.eintraege[0]));
}

/** "a, b , ,c" → ["a", "b", "c"] */
export function tagsAusText(text: string): string[] {
  return [...new Set(text.split(",").map((t) => t.trim()).filter(Boolean))];
}

// Signed-in e-mail, sent as X-LV-Scout-User so the backend records the owner (set by the account chip).
let besitzer: string | null = null;
export function setzeBesitzer(email: string | null | undefined) { besitzer = email || null; }
export function besitzerKopf(): Record<string, string> { return besitzer ? { "X-LV-Scout-User": besitzer } : {}; }

async function vaultCall<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/backend${path}`, { cache: "no-store", ...init, headers: { ...besitzerKopf(), ...(init?.headers as Record<string, string> | undefined) } });
  if (response.status === 204) return undefined as T;
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw Object.assign(new Error(typeof body.detail === "string" ? body.detail : `Vault request failed (${response.status}).`), { status: response.status });
  return body as T;
}

export const vaultApi = {
  liste: (typen?: VaultTyp[], lv?: string) => {
    const q = new URLSearchParams();
    if (typen?.length) q.set("typ", typen.join(","));
    if (lv) q.set("lv", lv);
    const s = q.toString();
    return vaultCall<VaultEintrag[]>(`/api/vault${s ? `?${s}` : ""}`);
  },
  hochladen: (datei: File, typ: VaultTyp, tags: string[] = []) => {
    const form = new FormData();
    form.append("datei", datei);
    form.append("typ", typ);
    form.append("tags", tags.join(","));
    return vaultCall<VaultEintrag>("/api/vault", { method: "POST", body: form });
  },
  aendern: (id: string, aenderung: { dateiname?: string; tags?: string[]; projekt?: string }) =>
    vaultCall<VaultEintrag>(`/api/vault/${encodeURIComponent(id)}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(aenderung) }),
  loeschen: (id: string) => vaultCall<void>(`/api/vault/${encodeURIComponent(id)}`, { method: "DELETE" }),
  dateiUrl: (id: string) => `/backend/api/vault/${encodeURIComponent(id)}/datei`,
  /** Stored file as a File, so the wizard can reuse it without a new upload from disk. */
  alsDatei: async (e: VaultEintrag): Promise<File> => {
    const response = await fetch(vaultApi.dateiUrl(e.id));
    if (!response.ok) throw new Error(`The stored file could not be loaded (${response.status}).`);
    return new File([await response.blob()], e.dateiname, { type: response.headers.get("content-type") ?? "" });
  },
  json: async <T = unknown>(e: VaultEintrag): Promise<T> => {
    const response = await fetch(vaultApi.dateiUrl(e.id));
    if (!response.ok) throw new Error(`The stored file could not be loaded (${response.status}).`);
    return response.json() as Promise<T>;
  },
};

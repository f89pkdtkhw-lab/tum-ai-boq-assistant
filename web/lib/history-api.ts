// History cases for the UI (#24). Shapes follow the proposal in docs/architektur.md and the metadata
// contract in docs/comparison-api.md; field details stay provisional until the #18 history API lands.
// Pure functions only, so the browser, the route handlers and node --test can all import this file.

export type Measurement = { oz: string; title_path?: string[]; metric: string; value: number | null; unit: string };
export type Mark = { oz: string; title_path: string[]; status: string; what_happened?: string | null; reason?: string | null };
export type CaseLv = { name: string; quelle: string; positionen: { oz: string; kurztext?: string }[] };
export type HistoryCase = {
  case_id: string; date: string; description: string; tags: string[]; source: string;
  estimated_values: Measurement[]; real_values: Measurement[]; comments: string[]; marks: Mark[];
  lv: CaseLv; // kept so description/tags can be regenerated through /api/history/metadata
};
export type CaseUpdate = { real_values?: Measurement[]; comments?: string[]; marks?: Mark[] };

export const MARK_STATUSES = ["confirmed", "deviation", "open"] as const;

const isObj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
const text = (v: unknown) => (typeof v === "string" ? v.trim() : "");

/** Returns a readable reason why an update cannot be applied to this case, or null. */
export function validateUpdate(current: HistoryCase, update: unknown): string | null {
  if (!isObj(update)) return "The update must be a JSON object.";
  const known = new Set(current.lv.positionen.map((p) => p.oz));
  const { real_values, comments, marks } = update;
  if (real_values !== undefined) {
    if (!Array.isArray(real_values)) return "real_values must be a list.";
    for (const m of real_values) {
      if (!isObj(m) || !known.has(m.oz as string)) return `Actual value for unknown OZ ${isObj(m) ? String(m.oz) : ""}.`.trim();
      if (!text(m.metric) || !text(m.unit)) return `Actual value for OZ ${m.oz} needs a metric and a unit.`;
      if (m.value !== null && (typeof m.value !== "number" || !Number.isFinite(m.value) || m.value < 0)) {
        return `Actual value for OZ ${m.oz} must be a non-negative number or empty.`;
      }
    }
  }
  if (comments !== undefined && (!Array.isArray(comments) || comments.some((c) => typeof c !== "string"))) {
    return "comments must be a list of text.";
  }
  if (marks !== undefined) {
    if (!Array.isArray(marks)) return "marks must be a list.";
    for (const k of marks) {
      if (!isObj(k) || !known.has(k.oz as string)) return `Mark for unknown OZ ${isObj(k) ? String(k.oz) : ""}.`.trim();
      if (!text(k.status)) return `Mark for OZ ${k.oz} needs a status.`;
    }
  }
  return null;
}

const key = (m: { oz: string; metric?: string }) => `${m.oz}\u0000${m.metric ?? ""}`;

/** Merges user input into a case. Repeat saves replace instead of duplicating; empty explanations stay absent. */
export function applyUpdate(current: HistoryCase, update: CaseUpdate): HistoryCase {
  const real = new Map(current.real_values.map((m) => [key(m), m]));
  for (const m of update.real_values ?? []) real.set(key(m), { ...m, metric: m.metric.trim(), unit: m.unit.trim() });

  const comments = [...current.comments];
  for (const c of update.comments ?? []) {
    const t = c.trim();
    if (t && !comments.includes(t)) comments.push(t);
  }

  const marks = new Map(current.marks.map((k) => [k.oz, k]));
  for (const k of update.marks ?? []) {
    const mark: Mark = { oz: k.oz, title_path: k.title_path ?? [], status: k.status.trim() };
    if (text(k.what_happened)) mark.what_happened = text(k.what_happened);
    if (text(k.reason)) mark.reason = text(k.reason);
    marks.set(k.oz, mark); // one assessment per OZ
  }
  return { ...current, real_values: [...real.values()], comments, marks: [...marks.values()] };
}

/** Newest first, optionally only cases carrying the tag. */
export function filterCases(cases: HistoryCase[], tag: string | null, limit = 20): HistoryCase[] {
  return cases.filter((c) => !tag || c.tags.includes(tag)).sort((a, b) => b.date.localeCompare(a.date)).slice(0, limit);
}

export const isMockSource = (source: string) => source === "model_mock";

// ---------- browser client for the UI API (web/app/api/history) ----------

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { cache: "no-store", ...init });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof body.error === "string" ? body.error : `Request failed (HTTP ${response.status}).`);
  return body as T;
}

export const historyApi = {
  list: (tag?: string | null) => call<{ items: HistoryCase[] }>(`/api/history${tag ? `?tag=${encodeURIComponent(tag)}` : ""}`).then((b) => b.items),
  get: (caseId: string) => call<HistoryCase>(`/api/history/${encodeURIComponent(caseId)}`),
  update: (caseId: string, update: CaseUpdate) => call<HistoryCase>(`/api/history/${encodeURIComponent(caseId)}`, {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(update),
  }),
};

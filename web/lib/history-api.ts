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
  list: (tag?: string | null, limit = 20) => call<{ items: HistoryCase[] }>(`/api/history?limit=${limit}${tag ? `&tag=${encodeURIComponent(tag)}` : ""}`).then((b) => b.items),
  get: (caseId: string) => call<HistoryCase>(`/api/history/${encodeURIComponent(caseId)}`),
  create: (body: { date: string; lv: CaseLv; estimated_values: Measurement[] }) => call<HistoryCase>("/api/history", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  }),
  update: (caseId: string, update: CaseUpdate) => call<HistoryCase>(`/api/history/${encodeURIComponent(caseId)}`, {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(update),
  }),
};

export type PastPosition = { case: HistoryCase; oz: string; kurztext: string; estimated: Measurement[]; real: Measurement[]; mark: Mark | null };

const words = (s: string) => s.toLowerCase().split(/[^\p{L}\p{N}]+/u).filter((w) => w.length >= 4);

/** Past positions whose short text starts with the same work type as this one (e.g. "Erdarbeiten …"), newest first. */
// shortcut: matches only on the first word of the short text; upgrade to the history API's similarity search once #18 offers one.
export function similarPositions(cases: HistoryCase[], kurztext: string | null | undefined, limit = 5): PastPosition[] {
  const key = words(kurztext ?? "")[0];
  if (!key) return [];
  const found: PastPosition[] = [];
  for (const c of [...cases].sort((a, b) => b.date.localeCompare(a.date))) {
    for (const p of c.lv.positionen) {
      if (words(p.kurztext ?? "")[0] !== key) continue;
      found.push({
        case: c, oz: p.oz, kurztext: p.kurztext ?? "",
        estimated: c.estimated_values.filter((m) => m.oz === p.oz), real: c.real_values.filter((m) => m.oz === p.oz),
        mark: c.marks.find((m) => m.oz === p.oz) ?? null,
      });
    }
  }
  return found.slice(0, limit);
}

export type TradeStat = { trade: string; projects: number; withActual: number; avgDeviation: number | null; deviationSpread?: number | null };

/** Sample standard deviation of percentage deviations; null with fewer than two observations. */
function streuung(devs: number[]): number | null {
  if (devs.length < 2) return null;
  const mean = devs.reduce((a, b) => a + b, 0) / devs.length;
  const varianz = devs.reduce((s, x) => s + (x - mean) ** 2, 0) / (devs.length - 1);
  return Math.sqrt(varianz);
}

/** Average actual-vs-estimate deviation (%) per work type (first word of the short text), worst first. */
export function deviationByTrade(cases: HistoryCase[]): TradeStat[] {
  const stats = new Map<string, { projects: Set<string>; devs: number[] }>();
  for (const c of cases) {
    for (const p of c.lv.positionen) {
      const raw = (p.kurztext ?? "").split(/[^\p{L}\p{N}]+/u).find((w) => w.length >= 4);
      if (!raw) continue;
      const trade = raw[0].toUpperCase() + raw.slice(1).toLowerCase();
      const s = stats.get(trade) ?? { projects: new Set(), devs: [] };
      s.projects.add(c.case_id);
      const est = c.estimated_values.find((m) => m.oz === p.oz);
      const real = c.real_values.find((m) => m.oz === p.oz && m.metric === est?.metric);
      if (est?.value && real?.value != null) s.devs.push(((real.value - est.value) / est.value) * 100);
      stats.set(trade, s);
    }
  }
  return [...stats].map(([trade, s]) => ({
    trade, projects: s.projects.size, withActual: s.devs.length,
    avgDeviation: s.devs.length ? s.devs.reduce((a, b) => a + b, 0) / s.devs.length : null,
    deviationSpread: streuung(s.devs),
  })).sort((a, b) => Math.abs(b.avgDeviation ?? 0) - Math.abs(a.avgDeviation ?? 0) || a.trade.localeCompare(b.trade));
}

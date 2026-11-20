// Server-only history storage behind the UI API. Uses the #18 history HTTP API when HISTORY_API_URL is set,
// otherwise an in-memory mock seeded with three synthetic cases (no real LVs).
// shortcut: the mock lives in server memory and resets on restart; drop it once #18 is merged and deployed.
import type { CaseLv, HistoryCase, Measurement } from "@/lib/history-api";

const HISTORY_URL = process.env.HISTORY_API_URL?.replace(/\/$/, "");
export const BACKEND = (process.env.API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

export class UpstreamError extends Error {
  constructor(message: string, readonly status = 502) { super(message); }
}

const hours = (oz: string, value: number | null, title: string): Measurement[] => [{ oz, title_path: [title], metric: "hours", value, unit: "h" }];
const lv = (name: string, positionen: CaseLv["positionen"]): CaseLv => ({ name, quelle: "synthetic: history mock (#24)", positionen });

function seed(): Map<string, HistoryCase> {
  const cases: HistoryCase[] = [
    {
      case_id: "H1", date: "2026-11-20", description: "Mock: bridge repair case.", tags: ["bridge"], source: "model_mock",
      estimated_values: hours("01.001", 100, "Bridge"), real_values: [], comments: [], marks: [],
      lv: lv("Synthetic bridge repair", [{ oz: "01.001", kurztext: "Concrete repair, bridge deck" }]),
    },
    {
      case_id: "H2", date: "2026-09-14", description: "Mock: bridge repair case.", tags: ["bridge"], source: "model_mock",
      estimated_values: hours("01.001", 80, "Bridge"), real_values: hours("01.001", 95, "Bridge"),
      comments: ["Joint replacement took longer than planned"],
      marks: [{ oz: "01.001", title_path: ["Bridge"], status: "deviation", what_happened: "Extra work on joints", reason: "Corrosion found after opening" }],
      lv: lv("Synthetic bridge joint replacement", [{ oz: "01.001", kurztext: "Replace expansion joint, bridge" }]),
    },
    {
      case_id: "H3", date: "2026-10-02", description: "Mock: parsed case with 2 positions.", tags: [], source: "model_mock",
      estimated_values: [...hours("02.001", 40, "Shell"), ...hours("02.002", 24, "Shell")], real_values: [], comments: [], marks: [],
      lv: lv("Synthetic office shell", [{ oz: "02.001", kurztext: "Masonry walls" }, { oz: "02.002", kurztext: "Ceiling formwork" }]),
    },
  ];
  return new Map(cases.map((c) => [c.case_id, c]));
}

// globalThis keeps the mock across dev hot reloads.
const memory = ((globalThis as { __historyMock?: Map<string, HistoryCase> }).__historyMock ??= seed());

async function upstream<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${HISTORY_URL}${path}`, { cache: "no-store", headers: { "Content-Type": "application/json" }, ...init });
  } catch {
    throw new UpstreamError("The history service is not reachable. Nothing was saved.");
  }
  const body = await response.json().catch(() => null);
  if (response.status === 404) throw new UpstreamError("This case does not exist.", 404);
  if (!response.ok || body === null) throw new UpstreamError(`The history service failed (HTTP ${response.status}). Nothing was saved.`);
  return body as T;
}

export const store = {
  async list(): Promise<HistoryCase[]> {
    return HISTORY_URL ? upstream<HistoryCase[]>("/history/records?limit=100") : [...memory.values()];
  },
  async get(caseId: string): Promise<HistoryCase | null> {
    if (!HISTORY_URL) return memory.get(caseId) ?? null;
    try { return await upstream<HistoryCase>(`/history/records/${encodeURIComponent(caseId)}`); } catch (e) {
      if (e instanceof UpstreamError && e.status === 404) return null;
      throw e;
    }
  },
  async save(record: HistoryCase, isNew: boolean): Promise<HistoryCase> {
    if (!HISTORY_URL) { memory.set(record.case_id, record); return record; }
    return isNew
      ? upstream<HistoryCase>("/history/records", { method: "POST", body: JSON.stringify(record) })
      : upstream<HistoryCase>(`/history/records/${encodeURIComponent(record.case_id)}`, { method: "PATCH", body: JSON.stringify(record) });
  },
  nextId: () => `H${memory.size + 1}`,
};

/** Asks the backend metadata endpoint (mock model) for description and tags; never calls a model provider directly. */
export async function enrich(record: HistoryCase): Promise<HistoryCase> {
  const body = {
    lv: { name: record.lv.name, quelle: record.lv.quelle, positionen: record.lv.positionen },
    estimated_values: record.estimated_values, real_values: record.real_values, comments: record.comments, marks: record.marks,
  };
  let response: Response;
  try {
    response = await fetch(`${BACKEND}/api/history/metadata`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), cache: "no-store",
    });
  } catch {
    throw new UpstreamError("The backend is not reachable, so no description could be generated. Nothing was saved; your input is kept.");
  }
  const data = await response.json().catch(() => null);
  if (response.status === 422) throw new UpstreamError("The backend rejected these values. Check the OZ and numbers; nothing was saved.", 422);
  if (!response.ok || !data) {
    throw new UpstreamError(data?.detail?.message ?? `Description generation failed (HTTP ${response.status}). Nothing was saved; your input is kept.`);
  }
  return { ...record, description: data.description, tags: data.tags, source: data.source };
}

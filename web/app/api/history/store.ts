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
const lv = (name: string, positionen: CaseLv["positionen"]): CaseLv => ({ name, quelle: "synthetic history (#24)", positionen });

function seed(): Map<string, HistoryCase> {
  const cases: HistoryCase[] = [
    {
      case_id: "H1", date: "2026-11-20", description: "Bridge repair case.", tags: ["bridge"], source: "model_mock",
      estimated_values: hours("01.001", 100, "Bridge"), real_values: [], comments: [], marks: [],
      lv: lv("Synthetic bridge repair", [{ oz: "01.001", kurztext: "Concrete repair, bridge deck" }]),
    },
    {
      case_id: "H2", date: "2026-09-14", description: "Bridge repair case.", tags: ["bridge"], source: "model_mock",
      estimated_values: hours("01.001", 80, "Bridge"), real_values: hours("01.001", 95, "Bridge"),
      comments: ["Joint replacement took longer than planned"],
      marks: [{ oz: "01.001", title_path: ["Bridge"], status: "deviation", what_happened: "Extra work on joints", reason: "Corrosion found after opening" }],
      lv: lv("Synthetic bridge joint replacement", [{ oz: "01.001", kurztext: "Expansion joint replacement, bridge" }]),
    },
    {
      case_id: "H3", date: "2026-10-02", description: "Parsed case with 2 positions.", tags: [], source: "model_mock",
      estimated_values: [...hours("02.001", 40, "Shell"), ...hours("02.002", 24, "Shell")], real_values: [], comments: [], marks: [],
      lv: lv("Synthetic office shell", [{ oz: "02.001", kurztext: "Masonry walls" }, { oz: "02.002", kurztext: "Ceiling formwork" }]),
    },
    {
      case_id: "H4", date: "2026-06-12", description: "Residential shell works.", tags: ["shell"], source: "model_mock",
      estimated_values: [...hours("01.001", 60, "Earthworks"), ...hours("02.001", 120, "Concrete"), ...hours("03.001", 90, "Masonry")],
      real_values: [...hours("01.001", 63, "Earthworks"), ...hours("02.001", 158, "Concrete"), ...hours("03.001", 101, "Masonry")],
      comments: ["Concrete pours delayed by rain"],
      marks: [{ oz: "02.001", title_path: ["Concrete"], status: "deviation", what_happened: "Extra formwork days", reason: "Weather" }],
      lv: lv("Synthetic residential shell A", [
        { oz: "01.001", kurztext: "Erdarbeiten Baugrube" }, { oz: "02.001", kurztext: "Betonarbeiten Bodenplatte" }, { oz: "03.001", kurztext: "Mauerarbeiten Außenwände" },
      ]),
    },
    {
      case_id: "H5", date: "2025-09-03", description: "Small shell works.", tags: ["shell"], source: "model_mock",
      estimated_values: [...hours("01.001", 40, "Earthworks"), ...hours("02.001", 80, "Concrete")],
      real_values: hours("01.001", 52, "Earthworks"), comments: [],
      marks: [{ oz: "01.001", title_path: ["Earthworks"], status: "confirmed" }],
      lv: lv("Synthetic residential shell B", [{ oz: "01.001", kurztext: "Erdarbeiten Fundamente" }, { oz: "02.001", kurztext: "Betonarbeiten Decken" }]),
    },
  ];
  return new Map([...cases, ...generated(40)].map((c) => [c.case_id, c]));
}

// Trades as in data/beispiel_lv_gross.json, with a typical overrun bias (%) so the dashboard shows a pattern.
// [trade, work, overrun bias %, unit, typical unit price in EUR] – synthetic, roughly the ranges of tools/beispiel_gross.py.
const TRADES: [string, string, number, string, number][] = [
  ["Erdarbeiten", "Baugrube", 8, "m³", 26], ["Betonarbeiten", "Bodenplatte", 18, "m³", 255], ["Bewehrung", "Betonstahl", 5, "t", 1700],
  ["Mauerarbeiten", "Außenwand", 10, "m²", 72], ["Abdichtung", "Kellerwand", 28, "m²", 44], ["Dacharbeiten", "Flachdach", 22, "m²", 92],
  ["Fenster", "Kunststoff", 3, "St", 980], ["Putzarbeiten", "Innenputz", 6, "m²", 29], ["Estricharbeiten", "Zementestrich", 12, "m²", 34],
  ["Fliesenarbeiten", "Bad", 15, "m²", 78], ["Malerarbeiten", "Anstrich", -2, "m²", 11], ["Sanitär", "WC-Anlage", 20, "St", 540],
];
const PLACES = ["Munich", "Augsburg", "Ingolstadt", "Rosenheim", "Freising", "Landshut", "Regensburg", "Erding"];
const KINDS = ["housing estate", "single-family house", "office building", "school extension", "underground car park"];

/** Deterministic synthetic past projects (no real data): each covers 5–9 trades, ~70 % with actual hours. */
function generated(count: number): HistoryCase[] {
  let state = 42;
  const rnd = () => ((state = (state * 1103515245 + 12345) % 2147483648) / 2147483648);
  return Array.from({ length: count }, (_, i) => {
    const id = `G${String(i + 1).padStart(2, "0")}`;
    const trades = [...TRADES].sort(() => rnd() - .5).slice(0, 5 + Math.floor(rnd() * 5));
    const finished = rnd() < .7;
    const est: Measurement[] = [];
    const real: Measurement[] = [];
    const marks: HistoryCase["marks"] = [];
    const prices: Measurement[] = [];
    const positionen = trades.map(([trade, work, bias, unit, price], n) => {
      const oz = `${String(n + 1).padStart(2, "0")}.001`;
      const planned = Math.round(20 + rnd() * 300);
      est.push(...hours(oz, planned, trade));
      // Hours first: the history panel and accuracy stats read the hours pair; unit prices feed the price comparison.
      prices.push({ oz, title_path: [trade], metric: "unit_price", value: Math.round(price * (0.85 + rnd() * 0.3) * 100) / 100, unit: `EUR/${unit}` });
      if (finished) {
        const dev = bias + (rnd() - .5) * 30;
        real.push(...hours(oz, Math.round(planned * (1 + dev / 100)), trade));
        if (Math.abs(dev) > 25) marks.push({ oz, title_path: [trade], status: "deviation", what_happened: `${trade} took ${Math.round(dev)} % longer than planned` });
        else if (rnd() < .3) marks.push({ oz, title_path: [trade], status: "confirmed" });
      }
      return { oz, kurztext: `${trade} ${work}` };
    });
    const month = 1 + Math.floor(rnd() * 12);
    const year = 2023 + Math.floor(rnd() * 3);
    const name = `Synthetic ${KINDS[Math.floor(rnd() * KINDS.length)]} ${PLACES[Math.floor(rnd() * PLACES.length)]}`;
    return {
      case_id: id, date: `${year}-${String(month).padStart(2, "0")}-${String(1 + Math.floor(rnd() * 28)).padStart(2, "0")}`,
      description: `${name}.`, tags: [], source: "model_mock",
      estimated_values: [...est, ...prices], real_values: real, comments: [], marks, lv: lv(name, positionen),
    };
  });
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

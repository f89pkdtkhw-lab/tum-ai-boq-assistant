import { filterCases, type CaseLv, type HistoryCase, type Measurement } from "@/lib/history-api";
import { enrich, store, UpstreamError } from "./store";

const fail = (status: number, error: string) => Response.json({ error }, { status });

export async function GET(request: Request) {
  const params = new URL(request.url).searchParams;
  const limit = Math.min(Math.max(Number(params.get("limit")) || 20, 1), 100);
  try {
    return Response.json({ items: filterCases(await store.list(), params.get("tag"), limit) });
  } catch (e) {
    return fail(e instanceof UpstreamError ? e.status : 500, e instanceof Error ? e.message : "History could not be loaded.");
  }
}

/** Creates a case from a parsed LV and its estimates; description and tags come from the metadata endpoint. */
export async function POST(request: Request) {
  const body = await request.json().catch(() => undefined) as { date?: unknown; lv?: CaseLv; estimated_values?: Measurement[] } | undefined;
  if (!body || typeof body.date !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(body.date)) return fail(400, "A case needs a date (YYYY-MM-DD).");
  if (!body.lv || typeof body.lv.name !== "string" || !Array.isArray(body.lv.positionen) || body.lv.positionen.length === 0) {
    return fail(400, "A case needs an LV with at least one position.");
  }
  const draft: HistoryCase = {
    case_id: store.nextId(), date: body.date, description: "", tags: [], source: "",
    estimated_values: Array.isArray(body.estimated_values) ? body.estimated_values : [], real_values: [], comments: [], marks: [],
    lv: { name: body.lv.name, quelle: String(body.lv.quelle ?? "user upload"), positionen: body.lv.positionen.map((p) => ({ oz: String(p.oz), kurztext: p.kurztext })) },
  };
  try {
    return Response.json(await store.save(await enrich(draft), true), { status: 201 });
  } catch (e) {
    return fail(e instanceof UpstreamError ? e.status : 500, e instanceof Error ? e.message : "The case could not be saved.");
  }
}

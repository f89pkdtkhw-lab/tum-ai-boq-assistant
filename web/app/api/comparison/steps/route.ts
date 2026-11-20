import { STEPS } from "@/lib/comparison-api";

// Same base URL resolution as the /backend rewrite in next.config.mjs.
const BACKEND = (process.env.API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const LIST_FIELDS = ["specifications", "history_records", "previous_notes"] as const;

const fail = (status: number, error: string) => Response.json({ error }, { status });

function invalid(body: unknown): string | null {
  if (!body || typeof body !== "object" || Array.isArray(body)) return "The request body must be a JSON object.";
  const b = body as Record<string, unknown>;
  if (!STEPS.includes(b.step as never)) return `Unknown step. Use one of: ${STEPS.join(", ")}.`;
  const lv = b.lv as Record<string, unknown> | undefined;
  if (!lv || typeof lv !== "object" || !Array.isArray(lv.positionen)) return "The request needs an LV with a positionen list.";
  const notList = LIST_FIELDS.find((field) => b[field] !== undefined && !Array.isArray(b[field]));
  return notList ? `${notList} must be a list.` : null;
}

// FastAPI 422 detail is a string or a list of {loc, msg}; turn it into one sentence.
function describe422(detail: unknown): string {
  const items = Array.isArray(detail) ? detail : [detail];
  const messages = items.map((item) => {
    if (typeof item === "string") return item;
    const { loc, msg } = (item ?? {}) as { loc?: unknown[]; msg?: string };
    const where = Array.isArray(loc) ? loc.filter((part) => part !== "body").join(".") : "";
    return `${where ? `${where}: ` : ""}${(msg ?? "invalid value").replace(/^Value error, /, "")}`;
  });
  return `The backend rejected the step input: ${messages.join("; ")}`;
}

export async function POST(request: Request) {
  const body = await request.json().catch(() => undefined);
  const problem = invalid(body);
  if (problem) return fail(400, problem);

  let upstream: Response;
  try {
    upstream = await fetch(`${BACKEND}/api/comparison/steps`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), cache: "no-store",
    });
  } catch {
    return fail(502, "The backend is not reachable. Start it with `python3 tools/dev.py` and try again.");
  }
  const data = await upstream.json().catch(() => null);
  if (upstream.status === 422) return fail(422, describe422(data?.detail));
  if (!upstream.ok || !data) return fail(502, `The backend could not run this step (HTTP ${upstream.status}). Earlier notes are unchanged.`);
  return Response.json(data);
}

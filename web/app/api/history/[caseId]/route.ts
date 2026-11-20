import { applyUpdate, validateUpdate, type CaseUpdate } from "@/lib/history-api";
import { enrich, store, UpstreamError } from "../store";

type Context = { params: Promise<{ caseId: string }> };
const fail = (status: number, error: string) => Response.json({ error }, { status });
const failure = (e: unknown) => fail(e instanceof UpstreamError ? e.status : 500, e instanceof Error ? e.message : "Request failed.");

export async function GET(_request: Request, { params }: Context) {
  const { caseId } = await params;
  try {
    const found = await store.get(caseId);
    return found ? Response.json(found) : fail(404, `Case ${caseId} does not exist.`);
  } catch (e) {
    return failure(e);
  }
}

/** Saves actual values, comments and marks; description and tags are regenerated server-side. */
export async function PATCH(request: Request, { params }: Context) {
  const { caseId } = await params;
  const update = await request.json().catch(() => undefined);
  try {
    const current = await store.get(caseId);
    if (!current) return fail(404, `Case ${caseId} does not exist.`);
    const problem = validateUpdate(current, update);
    if (problem) return fail(400, problem);
    const merged = applyUpdate(current, update as CaseUpdate);
    return Response.json(await store.save(await enrich(merged), false));
  } catch (e) {
    return failure(e);
  }
}

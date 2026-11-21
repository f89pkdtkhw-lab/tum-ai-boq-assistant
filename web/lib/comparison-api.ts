// Client side of the offline step contract (docs/comparison-api.md, api/app/ai/step_api.py).
// The browser only talks to the Next route /api/comparison/steps, which forwards to FastAPI.

export const STEPS = ["comparison", "standards", "historical_adjustment", "what_if"] as const;
export type Step = (typeof STEPS)[number];

export type Specification = { id: string; oz: string; text: string; source: "user" | "internet" | "standard"; verified_applicable?: boolean };
export type Measurement = { oz: string; title_path?: string[]; metric: string; value: number | null; unit: string };
export type HistoryRecord = {
  case_id: string; date: string; description: string; tags?: string[];
  estimated_values?: Measurement[]; real_values?: Measurement[];
};
export type Evidence = { reference_id: string; oz: string; source: string; detail: string };
export type Note = {
  id: string; step: Step; oz: string; source: "model_mock" | "rule"; placeholder: boolean; text: string; manual_review: boolean;
  evidence: Evidence[]; case_ids: string[]; case_count: number; selection_reason: string | null;
  base_value: number | null; estimated_value: number | null; unit: string | null;
  assumption: string | null; uncertainty: string | null; approval_required: boolean;
};
export type StepError = { step: Step; code: string; message: string; retryable: boolean };
export type StepResponse = {
  step: Step; status: "placeholder" | "complete" | "error"; notes: Note[]; findings: unknown[]; evidence: Evidence[]; errors: StepError[];
};
export type StepRequest = {
  step: Step;
  lv: { name: string; quelle: string; positionen: { oz: string }[] };
  specifications?: Specification[];
  history_records?: HistoryRecord[];
  previous_notes?: Note[];
};

// Fixtures copied from the contract-fixtures block in docs/comparison-api.md; any change disables the synthetic notes.
const LV_FIXTURE = { name: "Synthetic bridge repair", quelle: "synthetic:comparison-v1", positionen: [{ oz: "01.001" }] };
const SPECIFICATIONS: Specification[] = [
  { id: "S10", oz: "01.001", text: "10 cm", source: "user" },
  { id: "S12", oz: "01.001", text: "12 cm", source: "internet" },
];
const hours = (value: number): Measurement[] => [{ oz: "01.001", metric: "hours", value, unit: "h" }];
const record = (case_id: string, real: number): HistoryRecord => ({
  case_id, date: "2026-11-20", description: "Synthetic history fixture", tags: ["bridge"],
  estimated_values: hours(100), real_values: hours(real),
});

export const STEP_FIXTURES: Record<Step, StepRequest> = {
  comparison: { step: "comparison", lv: LV_FIXTURE, specifications: SPECIFICATIONS },
  standards: { step: "standards", lv: LV_FIXTURE, specifications: SPECIFICATIONS },
  historical_adjustment: { step: "historical_adjustment", lv: LV_FIXTURE, history_records: ["H1", "H2", "H3"].map((id) => record(id, 120)) },
  what_if: { step: "what_if", lv: LV_FIXTURE, history_records: ["W1", "W2", "W3"].map((id) => record(id, 140)) },
};

/** Runs one step; returns the contract response (status may be "error") or throws with a readable message. */
export async function runStep(request: StepRequest): Promise<StepResponse> {
  let response: Response;
  try {
    response = await fetch("/api/comparison/steps", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(request),
    });
  } catch {
    throw new Error("The UI server is not reachable. Check that the web app is running.");
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new Error(typeof body?.error === "string" ? body.error : `Step request failed (HTTP ${response.status}).`);
  return body as StepResponse;
}

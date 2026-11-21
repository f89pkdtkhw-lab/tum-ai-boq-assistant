// Specification source records and the §3 status preview from docs/spezifikationen.md.
// The backend decides; this only mirrors the documented fixed rules so the UI can show them before sending.
import type { Specification } from "./comparison-api";

export type SourceType = "user" | "internet";
export type Category = "german_standard" | "user_requirement" | "external_other";
export type Requirement = { parameter: string; comparator: "eq" | "min" | "max"; value: number | null; unit: string };
export type SourceRecord = {
  spec_id: string; source_type: SourceType; category: Category; title: string;
  source_url: string | null; document_ref: string | null; location: string | null; as_of: string | null;
  scope: { oz: string[]; description: string }; text: string; requirement: Requirement | null;
  verified: boolean;
};
export type UnverifiedReason =
  "missing_source_reference" | "missing_location" | "missing_as_of" | "invalid_as_of" | "as_of_in_future" | "not_confirmed";
export type Rejection = "duplicate_spec_id" | "missing_scope" | "unknown_oz";
export type SourceStatus = {
  verification: "verified" | "unverified"; unverified_reasons: UnverifiedReason[];
  priority: 1 | 2 | 3 | 4 | null; rejection: Rejection | null;
};

// Editing any of these means the person has not confirmed the new reference yet.
export const REFERENCE_FIELDS = ["source_url", "document_ref", "location", "as_of", "scope"] as const;
const PRIORITY: Record<Category, 1 | 2 | 3> = { german_standard: 1, user_requirement: 2, external_other: 3 };

const present = (v: string | null) => Boolean(v?.trim());
const isCalendarDate = (v: string) =>
  /^\d{4}-\d{2}-\d{2}$/.test(v) && new Date(`${v}T00:00:00Z`).toISOString().startsWith(v);

/** Verification reasons in the documented order; `checkedOn` is YYYY-MM-DD. */
export function unverifiedReasons(record: SourceRecord, checkedOn: string): UnverifiedReason[] {
  const reasons: UnverifiedReason[] = [];
  if (!present(record.source_url) && !present(record.document_ref)) reasons.push("missing_source_reference");
  if (!present(record.location)) reasons.push("missing_location");
  const asOf = record.as_of?.trim() ?? "";
  if (!asOf) reasons.push("missing_as_of");
  else if (!isCalendarDate(asOf)) reasons.push("invalid_as_of");
  else if (asOf > checkedOn) reasons.push("as_of_in_future");
  if (record.verified !== true) reasons.push("not_confirmed");
  return reasons;
}

/** Status of every record, in input order. The first record with a spec_id wins; later duplicates are rejected. */
export function sourceStatuses(records: SourceRecord[], lvOz: string[], checkedOn: string): SourceStatus[] {
  const known = new Set(lvOz);
  const seen = new Set<string>();
  return records.map((record) => {
    const id = record.spec_id.trim();
    const rejection: Rejection | null = seen.has(id) ? "duplicate_spec_id"
      : record.scope.oz.length === 0 ? "missing_scope"
      : record.scope.oz.some((oz) => !known.has(oz)) ? "unknown_oz" : null;
    seen.add(id);
    const unverified_reasons = unverifiedReasons(record, checkedOn);
    const verified = unverified_reasons.length === 0;
    return {
      verification: verified ? "verified" : "unverified", unverified_reasons, rejection,
      priority: rejection ? null : verified ? PRIORITY[record.category] : 4,
    };
  });
}

/** One Specification per scope OZ for every non-rejected record, in LV order, then priority, then input order (§4). */
export function toSpecifications(records: SourceRecord[], lvOz: string[], checkedOn: string): Specification[] {
  const statuses = sourceStatuses(records, lvOz, checkedOn);
  const attached = records.map((record, index) => ({ record, status: statuses[index], index }))
    .filter(({ status }) => status.rejection === null)
    .sort((a, b) => (a.status.priority as number) - (b.status.priority as number) || a.index - b.index);
  return lvOz.flatMap((oz) => attached.filter(({ record }) => record.scope.oz.includes(oz)).map(({ record, status }) => ({
    id: record.spec_id.trim(), oz, text: record.text,
    source: record.category === "german_standard" ? "standard" : record.source_type,
    verified_applicable: record.category === "german_standard" && status.verification === "verified",
  })));
}

/** Applies an edit; a changed reference field resets the person's confirmation. */
export function updateSource(record: SourceRecord, patch: Partial<SourceRecord>): SourceRecord {
  const changed = REFERENCE_FIELDS.some((field) =>
    field in patch && JSON.stringify(patch[field]) !== JSON.stringify(record[field]));
  return { ...record, ...patch, ...(changed ? { verified: false } : {}) };
}

export const emptySource = (spec_id: string): SourceRecord => ({
  spec_id, source_type: "user", category: "user_requirement", title: "", source_url: null, document_ref: null,
  location: null, as_of: null, scope: { oz: [], description: "" }, text: "", requirement: null, verified: false,
});

// S10/S12 from data/architektur/spezifikationen.json (acceptance_conflict_unverified); they project onto the
// step fixture in comparison-api.ts, so Notes 1/2 keep working unchanged.
export const FIXTURE_SOURCES: SourceRecord[] = [
  {
    spec_id: "S10", source_type: "user", category: "user_requirement", title: "User requirement A (synthetic)",
    source_url: null, document_ref: "Synthetic client requirement sheet A", location: "Item 1", as_of: "2026-11-01",
    scope: { oz: ["01.001"], description: "Synthetic bridge repair, OZ 01.001 only" }, text: "10 cm",
    requirement: { parameter: "thickness", comparator: "eq", value: 10, unit: "cm" }, verified: true,
  },
  {
    spec_id: "S12", source_type: "internet", category: "external_other",
    title: "External requirement B (explicitly fictional, not a real publication)",
    source_url: "https://fictional-requirements.example.invalid/requirement-b", document_ref: null,
    location: "Paragraph B (fictional)", as_of: "2026-06-01",
    scope: { oz: ["01.001"], description: "Fictional; claimed to cover OZ 01.001" }, text: "12 cm",
    requirement: { parameter: "thickness", comparator: "eq", value: 12, unit: "cm" }, verified: false,
  },
];

// ---------- automation: fields the editor fills in by itself (the person still confirms the source) ----------

const KOMPARATOR: [RegExp, Requirement["comparator"]][] = [
  [/(\bmin(?:imum|\.)?|\bmindestens\b|\bat least\b|≥|>=)/i, "min"],
  [/(\bmax(?:imum|\.)?|\bhöchstens\b|\bat most\b|≤|<=)/i, "max"],
];
const PARAMETER: [RegExp, string][] = [
  [/dick|stärke|staerke|thick/i, "thickness"], [/breit|width/i, "width"], [/höhe|hoehe|height/i, "height"],
  [/länge|laenge|length/i, "length"], [/tiefe|depth/i, "depth"], [/druckfestigkeit|strength/i, "strength"],
  [/überdeckung|ueberdeckung|cover/i, "concrete_cover"], [/gefälle|gefaelle|slope/i, "slope"],
];

/** Reads "min. 12,5 cm Dicke" as { parameter: "thickness", comparator: "min", value: 12.5, unit: "cm" }; null without a number. */
export function leseAnforderung(text: string): Requirement | null {
  const m = text.match(/(-?\d+(?:[.,]\d+)?)\s*([A-Za-zµ°%²³/]+[²³]?)?/);
  if (!m) return null;
  const value = Number(m[1].replace(",", "."));
  if (!Number.isFinite(value)) return null;
  const comparator = KOMPARATOR.find(([re]) => re.test(text))?.[1] ?? "eq";
  const parameter = PARAMETER.find(([re]) => re.test(text))?.[1] ?? "";
  return { parameter, comparator, value, unit: m[2] ?? "" };
}

const NORM = /\b(DIN|EN|ISO|VOB|ATV|DIN\s?EN)\b/;
export const hatNorm = (r: Pick<SourceRecord, "title" | "document_ref" | "source_url">) =>
  NORM.test(`${r.title} ${r.document_ref ?? ""} ${r.source_url ?? ""}`);
export const scopeText = (oz: string[]) => (oz.length ? `OZ ${oz.join(", ")}` : "");

/** Fields derived from an edit. Only fields the person has not set by hand are filled; `verified` is never touched. */
export function autoFelder(record: SourceRecord, patch: Partial<SourceRecord>): Partial<SourceRecord> {
  const neu = { ...record, ...patch };
  const auto: Partial<SourceRecord> = {};
  if ("text" in patch && !("requirement" in patch)) {
    const vorher = leseAnforderung(record.text);
    if (record.requirement === null || JSON.stringify(record.requirement) === JSON.stringify(vorher)) {
      auto.requirement = leseAnforderung(neu.text);
    }
  }
  if (("title" in patch || "document_ref" in patch || "source_url" in patch) && !("category" in patch) && hatNorm(neu)) {
    auto.category = "german_standard";
  } else if ("source_type" in patch && !("category" in patch) && !hatNorm(neu)) {
    auto.category = neu.source_type === "internet" ? "external_other" : "user_requirement";
  }
  if (patch.scope && JSON.stringify(patch.scope.oz) !== JSON.stringify(record.scope.oz)
    && (record.scope.description.trim() === "" || record.scope.description === scopeText(record.scope.oz))) {
    auto.scope = { ...patch.scope, description: scopeText(patch.scope.oz) };
  }
  return auto;
}

/** "thickness ≥ 12.5 cm" for the collapsed summary. */
export const anforderungText = (r: Requirement | null) =>
  r && r.value !== null ? `${r.parameter || "value"} ${{ eq: "=", min: "≥", max: "≤" }[r.comparator]} ${r.value} ${r.unit}`.trim() : "";

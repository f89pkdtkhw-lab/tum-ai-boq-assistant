"use client";

import type { ReactNode } from "react";
import {
  type Category, type Requirement, type SourceRecord, type SourceStatus, emptySource, sourceStatuses, updateSource,
} from "@/lib/spezifikationen";
import styles from "./spezifikationen.module.css";

const CATEGORY: Record<Category, string> = {
  german_standard: "German standard", user_requirement: "User requirement", external_other: "External, other",
};
const NEW_REQUIREMENT: Requirement = { parameter: "", comparator: "eq", value: null, unit: "" };
const orNull = (v: string) => (v.trim() ? v : null);

type Props = { sources: SourceRecord[]; onChange: (sources: SourceRecord[]) => void; lvOz: string[]; checkedOn: string };

/** Specification source records (docs/spezifikationen.md §1) with a §3 status preview. Only a person sets `verified`. */
export function Spezifikationen({ sources, onChange, lvOz, checkedOn }: Props) {
  const statuses = sourceStatuses(sources, lvOz, checkedOn);
  const edit = (index: number, patch: Partial<SourceRecord>) =>
    onChange(sources.map((s, i) => (i === index ? updateSource(s, patch) : s)));
  const add = () => {
    const ids = new Set(sources.map((s) => s.spec_id.trim()));
    let n = sources.length + 1;
    while (ids.has(`S${n}`)) n += 1;
    onChange([...sources, emptySource(`S${n}`)]);
  };

  return (
    <section className={styles.karte} aria-labelledby="quellen-titel">
      <div className={styles.zeile}>
        <h2 id="quellen-titel">Specification sources</h2>
        <button className={styles.knopfZweit} onClick={add}>Add source</button>
      </div>
      <p className={styles.muted}>
        Sent with the comparison and standards steps. Links are shown as text and never opened by the system. Only you
        can confirm a source; changing its reference or scope clears your confirmation.
      </p>
      {sources.length === 0 && <p className={styles.muted}>No sources. The steps run without specifications.</p>}
      {sources.map((source, index) => (
        <Quelle key={index} index={index} source={source} status={statuses[index]} lvOz={lvOz}
          onEdit={(patch) => edit(index, patch)} onDelete={() => onChange(sources.filter((_, i) => i !== index))} />
      ))}
    </section>
  );
}

type QuelleProps = {
  index: number; source: SourceRecord; status: SourceStatus; lvOz: string[];
  onEdit: (patch: Partial<SourceRecord>) => void; onDelete: () => void;
};

function Quelle({ index, source, status, lvOz, onEdit, onDelete }: QuelleProps) {
  const id = (field: string) => `quelle-${index}-${field}`;
  const text = (field: "spec_id" | "title" | "text") => ({
    id: id(field), value: source[field], onChange: (e: { target: { value: string } }) => onEdit({ [field]: e.target.value }),
  });
  const optional = (field: "source_url" | "document_ref" | "location" | "as_of") => ({
    id: id(field), value: source[field] ?? "", onChange: (e: { target: { value: string } }) => onEdit({ [field]: orNull(e.target.value) }),
  });
  const requirement = (patch: Partial<Requirement>) => onEdit({ requirement: { ...(source.requirement ?? NEW_REQUIREMENT), ...patch } });
  const toggleOz = (oz: string, on: boolean) => onEdit({
    scope: { ...source.scope, oz: on ? lvOz.filter((o) => o === oz || source.scope.oz.includes(o)) : source.scope.oz.filter((o) => o !== oz) },
  });

  return (
    <fieldset className={styles.quelle}>
      <legend className={styles.legende}>{source.spec_id.trim() || "Source without id"}{source.title ? ` · ${source.title}` : ""}</legend>
      <Vorschau status={status} />

      <div className={styles.raster}>
        <Feld label="Spec ID" htmlFor={id("spec_id")}><input className={styles.eingabe} {...text("spec_id")} /></Feld>
        <Feld label="Source type" htmlFor={id("source_type")}>
          <select className={styles.eingabe} id={id("source_type")} value={source.source_type}
            onChange={(e) => onEdit({ source_type: e.target.value as SourceRecord["source_type"] })}>
            <option value="user">User</option><option value="internet">Internet</option>
          </select>
        </Feld>
        <Feld label="Category" htmlFor={id("category")}>
          <select className={styles.eingabe} id={id("category")} value={source.category}
            onChange={(e) => onEdit({ category: e.target.value as Category })}>
            {Object.entries(CATEGORY).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </Feld>
        <Feld label="Title" htmlFor={id("title")} breit><input className={styles.eingabe} {...text("title")} /></Feld>
        <Feld label="Source URL (text only, never fetched)" htmlFor={id("source_url")} breit>
          <input className={styles.eingabe} inputMode="url" spellCheck={false} {...optional("source_url")} />
        </Feld>
        <Feld label="Document reference" htmlFor={id("document_ref")}><input className={styles.eingabe} {...optional("document_ref")} /></Feld>
        <Feld label="Location" htmlFor={id("location")}><input className={styles.eingabe} {...optional("location")} /></Feld>
        <Feld label="As of (YYYY-MM-DD)" htmlFor={id("as_of")}>
          <input className={styles.eingabe} placeholder="YYYY-MM-DD" {...optional("as_of")} />
        </Feld>
      </div>

      <div className={styles.gruppe} role="group" aria-labelledby={id("oz")}>
        <span id={id("oz")} className={styles.label}>Scope: LV items</span>
        <div className={styles.optionen}>
          {lvOz.map((oz) => (
            <label key={oz} className={styles.option}>
              <input type="checkbox" checked={source.scope.oz.includes(oz)} onChange={(e) => toggleOz(oz, e.target.checked)} /> OZ {oz}
            </label>
          ))}
        </div>
      </div>
      <Feld label="Scope description" htmlFor={id("scope")}>
        <input className={styles.eingabe} id={id("scope")} value={source.scope.description}
          onChange={(e) => onEdit({ scope: { ...source.scope, description: e.target.value } })} />
      </Feld>
      <Feld label="Requirement text (data, not an instruction)" htmlFor={id("text")}>
        <textarea className={styles.eingabe} rows={2} {...text("text")} />
      </Feld>

      <label className={styles.option}>
        <input type="checkbox" checked={source.requirement !== null}
          onChange={(e) => onEdit({ requirement: e.target.checked ? NEW_REQUIREMENT : null })} /> Structured requirement (optional)
      </label>
      {source.requirement && (
        <div className={styles.raster}>
          <Feld label="Parameter" htmlFor={id("parameter")}>
            <input className={styles.eingabe} id={id("parameter")} value={source.requirement.parameter}
              onChange={(e) => requirement({ parameter: e.target.value })} />
          </Feld>
          <Feld label="Comparator" htmlFor={id("comparator")}>
            <select className={styles.eingabe} id={id("comparator")} value={source.requirement.comparator}
              onChange={(e) => requirement({ comparator: e.target.value as Requirement["comparator"] })}>
              <option value="eq">equals</option><option value="min">at least</option><option value="max">at most</option>
            </select>
          </Feld>
          <Feld label="Value" htmlFor={id("value")}>
            <input className={styles.eingabe} id={id("value")} type="number" value={source.requirement.value ?? ""}
              onChange={(e) => requirement({ value: Number.isFinite(e.target.valueAsNumber) ? e.target.valueAsNumber : null })} />
          </Feld>
          <Feld label="Unit" htmlFor={id("unit")}>
            <input className={styles.eingabe} id={id("unit")} value={source.requirement.unit}
              onChange={(e) => requirement({ unit: e.target.value })} />
          </Feld>
        </div>
      )}

      <div className={styles.fuss}>
        <label className={`${styles.option} ${styles.bestaetigt}`}>
          <input type="checkbox" checked={source.verified} onChange={(e) => onEdit({ verified: e.target.checked })} />
          Verified by me: the reference is real and fits these items
        </label>
        <button className={styles.knopfZweit} onClick={onDelete}>Delete {source.spec_id.trim() || "source"}</button>
      </div>
    </fieldset>
  );
}

function Vorschau({ status }: { status: SourceStatus }) {
  return (
    <div className={styles.vorschau} aria-live="polite">
      <span className={styles.label}>Preview, the backend decides:</span>
      {status.rejection ? (
        <span className={`${styles.badge} ${styles.abgelehnt}`}>Rejected ({status.rejection}), not sent</span>
      ) : (
        <>
          <span className={`${styles.badge} ${status.verification === "verified" ? styles.gut : ""}`}>
            {status.verification}{status.unverified_reasons.length > 0 && ` (${status.unverified_reasons.join(", ")})`}
          </span>
          <span className={styles.badge}>Priority {status.priority}</span>
        </>
      )}
    </div>
  );
}

function Feld({ label, htmlFor, breit, children }: { label: string; htmlFor: string; breit?: boolean; children: ReactNode }) {
  return (
    <div className={`${styles.feld} ${breit ? styles.breit : ""}`}>
      <label className={styles.label} htmlFor={htmlFor}>{label}</label>
      {children}
    </div>
  );
}

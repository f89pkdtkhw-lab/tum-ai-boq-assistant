"use client";

import { useState } from "react";
import { type Note, type Step, type StepRequest, STEP_FIXTURES, STEPS, runStep } from "@/lib/comparison-api";
import styles from "./schritte.module.css";

const LABEL: Record<Step, string> = {
  comparison: "Comparison", standards: "Standards", historical_adjustment: "Historical adjustment", what_if: "What-if",
};
const number = new Intl.NumberFormat("en-US", { maximumFractionDigits: 3 });
const value = (v: number | null, unit: string | null) => (v === null ? "–" : `${number.format(v)}${unit ? ` ${unit}` : ""}`);

// Deliberately broken request: a specification on an OZ that is not in the LV, which the backend rejects.
const withUnknownOz = (request: StepRequest): StepRequest => ({
  ...request,
  specifications: [...(request.specifications ?? []), { id: "SX", oz: "99.999", text: "unknown position", source: "user" }],
});

export function Schritte() {
  const [loaded, setLoaded] = useState(false);
  const [notes, setNotes] = useState<Note[]>([]);
  const [done, setDone] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const next: Step | undefined = STEPS[done];

  async function run(broken: boolean) {
    if (!next) return;
    setBusy(true);
    setError(null);
    try {
      const request = { ...STEP_FIXTURES[next], previous_notes: notes };
      const response = await runStep(broken ? withUnknownOz(request) : request);
      setNotes(response.notes);
      if (response.status === "error") {
        setError(response.errors.map((e) => `${e.message} (${e.code})`).join(" ") || "The step returned an error.");
      } else setDone(done + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    setNotes([]); setDone(0); setError(null);
  }

  return (
    <main className={styles.seite}>
      <header className={styles.kopf}>
        <a className={styles.zurueck} href="/">‹ Back to review</a>
        <h1>Step reports</h1>
        <p className={styles.muted}>
          Runs the four comparison steps against the offline contract. Every note is a synthetic placeholder from a fixed
          fixture, not a real calculation; estimates need approval by a calculator.
        </p>
      </header>

      <section className={styles.karte} aria-labelledby="input-titel">
        <h2 id="input-titel">Input</h2>
        {loaded ? (
          <ul className={styles.liste}>
            <li>LV <b>{STEP_FIXTURES.comparison.lv.name}</b>, position OZ 01.001</li>
            <li>Specifications S10 (user: 10 cm) and S12 (internet: 12 cm)</li>
            <li>History pool H1–H3 (100 h estimated, 120 h real) and what-if pool W1–W3 (100 h estimated, 140 h real)</li>
          </ul>
        ) : (
          <p className={styles.muted}>No input loaded.</p>
        )}
        <div className={styles.aktionen}>
          {!loaded && <button className={styles.knopf} onClick={() => setLoaded(true)}>Load synthetic fixture</button>}
          {loaded && next && (
            <>
              <button className={styles.knopf} disabled={busy} onClick={() => run(false)}>
                {busy ? "Running…" : `Run step ${done + 1}: ${LABEL[next]}`}
              </button>
              <button className={styles.knopfZweit} disabled={busy} onClick={() => run(true)}>Run with unknown OZ (fails)</button>
            </>
          )}
          {loaded && !next && <p className={styles.muted}>All four steps done.</p>}
          {(notes.length > 0 || error) && <button className={styles.knopfZweit} disabled={busy} onClick={reset}>Reset</button>}
        </div>
        {error && <p className={styles.fehler} role="alert">{next ? `${LABEL[next]} failed: ` : ""}{error} Earlier notes are kept.</p>}
      </section>

      {notes.map((note) => <NoteCard key={note.id} note={note} />)}
    </main>
  );
}

function NoteCard({ note }: { note: Note }) {
  const estimate = note.base_value !== null || note.estimated_value !== null;
  return (
    <article className={styles.karte} aria-labelledby={`${note.id}-titel`}>
      <div className={styles.zeile}>
        <h2 id={`${note.id}-titel`}>{note.id} · {LABEL[note.step]}</h2>
        <span className={styles.muted}>OZ {note.oz}</span>
      </div>
      <div className={styles.badges}>
        {(note.placeholder || note.source === "model_mock") && <span className={`${styles.badge} ${styles.mock}`}>Mock / Placeholder</span>}
        {note.manual_review && <span className={styles.badge}>Manual review</span>}
        {note.approval_required && <span className={`${styles.badge} ${styles.freigabe}`}>Approval required</span>}
      </div>
      <p>{note.text}</p>
      {estimate && (
        <p className={styles.schaetzung}>
          {value(note.base_value, note.unit)} → <b>{value(note.estimated_value, note.unit)}</b>
          <span className={styles.muted}> (estimate, not approved)</span>
        </p>
      )}
      <dl className={styles.details}>
        {note.evidence.length > 0 && (<>
          <dt>Sources</dt>
          <dd>{note.evidence.map((e) => `${e.reference_id} (${e.source}: ${e.detail})`).join(", ")}</dd>
        </>)}
        {note.case_ids.length > 0 && (<>
          <dt>Cases</dt>
          <dd>{note.case_ids.join(", ")} · count {note.case_count}</dd>
        </>)}
        {note.selection_reason && (<><dt>Selection</dt><dd>{note.selection_reason}</dd></>)}
        {note.assumption && (<><dt>Assumption</dt><dd>{note.assumption}</dd></>)}
        {note.uncertainty && (<><dt>Uncertainty</dt><dd>{note.uncertainty}</dd></>)}
      </dl>
    </article>
  );
}

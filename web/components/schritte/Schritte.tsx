"use client";

import { useState } from "react";
import { type Note, type Step, type StepRequest, STEP_FIXTURES, STEPS, runStep } from "@/lib/comparison-api";
import { FIXTURE_SOURCES, toSpecifications } from "@/lib/spezifikationen";
import { Spezifikationen } from "@/components/spezifikationen/Spezifikationen";
import styles from "./schritte.module.css";
import { useT } from "@/lib/einstellungen";
import { istAnnahme } from "@/lib/normen"; // #83: assumption marker

const LABEL: Record<Step, string> = {
  comparison: "Comparison", standards: "Standards", historical_adjustment: "Historical adjustment", what_if: "What-if",
};
const number = new Intl.NumberFormat("en-US", { maximumFractionDigits: 3 });
const LV_OZ = STEP_FIXTURES.comparison.lv.positionen.map((p) => p.oz);
const value = (v: number | null, unit: string | null) => (v === null ? "–" : `${number.format(v)}${unit ? ` ${unit}` : ""}`);

// Deliberately broken request: a specification on an OZ that is not in the LV, which the backend rejects.
const withUnknownOz = (request: StepRequest): StepRequest => ({
  ...request,
  specifications: [...(request.specifications ?? []), { id: "SX", oz: "99.999", text: "unknown position", source: "user" }],
});

export function Schritte() {
  const t = useT();
  const [loaded, setLoaded] = useState(false);
  const [notes, setNotes] = useState<Note[]>([]);
  const [done, setDone] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [sources, setSources] = useState(FIXTURE_SOURCES);
  const [checkedOn] = useState(() => new Date().toLocaleDateString("sv-SE")); // local YYYY-MM-DD
  const specifications = toSpecifications(sources, LV_OZ, checkedOn);
  const next: Step | undefined = STEPS[done];

  async function run(broken: boolean) {
    if (!next) return;
    setBusy(true);
    setError(null);
    try {
      const fixture = STEP_FIXTURES[next];
      // Steps that take specifications get the editor's records instead of the fixed fixture list.
      const request = { ...fixture, ...(fixture.specifications && { specifications }), previous_notes: notes };
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
        <a className={styles.zurueck} href="/">{t("‹ Back to review")}</a>
        <h1>{t("Step reports")}</h1>
        <p className={styles.muted}>
          Runs the four comparison steps against the offline contract. Every note is a synthetic placeholder from a fixed
          fixture, not a real calculation; estimates need approval by a calculator.
        </p>
      </header>

      <Spezifikationen sources={sources} onChange={setSources} lvOz={LV_OZ} checkedOn={checkedOn} />

      <section className={styles.karte} aria-labelledby="input-titel">
        <h2 id="input-titel">{t("Input")}</h2>
        {loaded ? (
          <ul className={styles.liste}>
            <li>{t("LV")} <b>{STEP_FIXTURES.comparison.lv.name}</b>{t(", position OZ 01.001")}</li>
            <li>
              {specifications.length > 0
                ? <>Specifications {specifications.map((s) => `${s.id} (${s.source}: ${s.text})`).join(", ")} from the sources above</>
                : "No specifications sent (all sources deleted or rejected)"}
            </li>
            <li>History pool H1–H3 (100 h estimated, 120 h real) and what-if pool W1–W3 (100 h estimated, 140 h real)</li>
          </ul>
        ) : (
          <p className={styles.muted}>{t("No input loaded.")}</p>
        )}
        <div className={styles.aktionen}>
          {!loaded && <button className={styles.knopf} onClick={() => setLoaded(true)}>{t("Load synthetic fixture")}</button>}
          {loaded && next && (
            <>
              <button className={styles.knopf} disabled={busy} onClick={() => run(false)}>
                {busy ? t("Running…") : t("Run step {n}: {name}", { n: done + 1, name: t(LABEL[next]) })}
              </button>
              <button className={styles.knopfZweit} disabled={busy} onClick={() => run(true)}>Run with unknown OZ (fails)</button>
            </>
          )}
          {loaded && !next && <p className={styles.muted}>{t("All four steps done.")}</p>}
          {(notes.length > 0 || error) && <button className={styles.knopfZweit} disabled={busy} onClick={reset}>{t("Reset")}</button>}
        </div>
        {error && <p className={styles.fehler} role="alert">{next ? `${t(LABEL[next])}: ${t("failed")} – ` : ""}{error} {t("Earlier notes are kept.")}</p>}
      </section>

      {notes.map((note) => <NoteCard key={note.id} note={note} />)}
    </main>
  );
}

function NoteCard({ note }: { note: Note }) {
  const t = useT();
  const estimate = note.base_value !== null || note.estimated_value !== null;
  return (
    <article className={styles.karte} aria-labelledby={`${note.id}-titel`}>
      <div className={styles.zeile}>
        <h2 id={`${note.id}-titel`}>{note.id} · {t(LABEL[note.step])}</h2>
        <span className={styles.muted}>OZ {note.oz}</span>
      </div>
      <div className={styles.badges}>
        {(note.placeholder || note.source === "model_mock") && <span className={`${styles.badge} ${styles.mock}`}>{t("Placeholder")}</span>}
        {note.manual_review && <span className={styles.badge}>{t("Manual review")}</span>}
        {istAnnahme(note) && <span className={`${styles.badge} ${styles.freigabe}`}>{t("Approval required")}</span>}
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
          <dt>{t("Sources")}</dt>
          <dd>{note.evidence.map((e) => `${e.reference_id} (${e.source}: ${e.detail})`).join(", ")}</dd>
        </>)}
        {note.case_ids.length > 0 && (<>
          <dt>{t("Cases")}</dt>
          <dd>{note.case_ids.join(", ")} · count {note.case_count}</dd>
        </>)}
        {note.selection_reason && (<><dt>{t("Selection")}</dt><dd>{note.selection_reason}</dd></>)}
        {note.assumption && (<><dt>{t("Assumption")}</dt><dd>{note.assumption}</dd></>)}
        {note.uncertainty && (<><dt>{t("Uncertainty")}</dt><dd>{note.uncertainty}</dd></>)}
      </dl>
    </article>
  );
}

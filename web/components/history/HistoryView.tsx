"use client";

import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { historyApi, MARK_STATUSES, type CaseUpdate, type HistoryCase, type Measurement } from "@/lib/history-api";
import { Abschluss } from "./Abschluss";
import styles from "./history.module.css";
import { useT } from "@/lib/einstellungen";
import { ProjektAbschluss } from "./ProjektAbschluss";

const zahl = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 2 });
const datum = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric" });
const key = (m: Measurement) => `${m.oz}|${m.metric}`;

type MarkDraft = { status: string; what_happened: string; reason: string };
type Draft = { actuals: Record<string, string>; comment: string; marks: Record<string, MarkDraft> };

function draftFor(c: HistoryCase): Draft {
  const actuals: Record<string, string> = {};
  for (const m of c.real_values) actuals[key(m)] = m.value === null ? "" : String(m.value);
  const marks: Record<string, MarkDraft> = {};
  for (const p of c.lv.positionen) {
    const k = c.marks.find((x) => x.oz === p.oz);
    marks[p.oz] = { status: k?.status ?? "", what_happened: k?.what_happened ?? "", reason: k?.reason ?? "" };
  }
  return { actuals, comment: "", marks };
}

export function HistoryView() {
  const t = useT();
  const [cases, setCases] = useState<HistoryCase[] | null>(null);
  const [tag, setTag] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [loadError, setLoadError] = useState("");
  const [saveState, setSaveState] = useState<{ kind: "idle" | "busy" | "ok" | "error"; text: string }>({ kind: "idle", text: "" });

  const load = useCallback(async () => {
    try {
      setCases(await historyApi.list(null, 100));
      setLoadError("");
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "History could not be loaded.");
    }
  }, []);
  useEffect(() => { void load(); }, [load]);
  // /history?fall=<id> opens that case (used after "Final bill" on the Submit page).
  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("fall");
    const fall = id && cases?.find((c) => c.case_id === id);
    if (fall && selected !== fall.case_id) open(fall);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cases]);

  const tags = useMemo(() => [...new Set((cases ?? []).flatMap((c) => c.tags))].sort(), [cases]);
  const shown = useMemo(
    () => (cases ?? []).filter((c) => !tag || c.tags.includes(tag)).sort((a, b) => b.date.localeCompare(a.date)),
    [cases, tag],
  );
  const current = cases?.find((c) => c.case_id === selected) ?? null;

  function open(c: HistoryCase) {
    setSelected(c.case_id);
    setDraft(draftFor(c));
    setSaveState({ kind: "idle", text: "" });
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!current || !draft) return;
    const real_values = current.estimated_values
      .filter((m) => draft.actuals[key(m)] !== undefined && (draft.actuals[key(m)].trim() !== "" || current.real_values.some((r) => key(r) === key(m))))
      .map((m) => {
        const raw = draft.actuals[key(m)].trim().replace(",", ".");
        return { oz: m.oz, title_path: m.title_path ?? [], metric: m.metric, unit: m.unit, value: raw === "" ? null : Number(raw) };
      });
    const update: CaseUpdate = {
      real_values,
      comments: draft.comment.trim() ? [draft.comment.trim()] : [],
      marks: Object.entries(draft.marks).filter(([, k]) => k.status).map(([oz, k]) => ({
        oz, title_path: current.estimated_values.find((m) => m.oz === oz)?.title_path ?? [], status: k.status,
        what_happened: k.what_happened, reason: k.reason,
      })),
    };
    setSaveState({ kind: "busy", text: "Saving …" });
    try {
      const saved = await historyApi.update(current.case_id, update);
      setCases((all) => (all ?? []).map((c) => (c.case_id === saved.case_id ? saved : c)));
      setDraft(draftFor(saved));
      setSaveState({ kind: "ok", text: "Saved. Description and tags were regenerated." });
    } catch (e) {
      setSaveState({ kind: "error", text: e instanceof Error ? e.message : "Saving failed; your input is kept." });
    }
  }

  const setActual = (k: string, v: string) => setDraft((d) => d && { ...d, actuals: { ...d.actuals, [k]: v } });
  const setMark = (oz: string, field: keyof MarkDraft, v: string) =>
    setDraft((d) => d && { ...d, marks: { ...d.marks, [oz]: { ...d.marks[oz], [field]: v } } });

  return (
    <div className={styles.seite}>
      <section className={styles.einleitung}>
        <p className={styles.eyebrow}>{t("Learn from past jobs")}</p>
        <h1>{t("Find comparable cases, then record what really happened.")}</h1>
        <p className={styles.lead}>{t("Filter by tag, check the description, and enter actual values, comments and marks. Estimates and actuals stay separate.")}</p>
      </section>

      <ProjektAbschluss onFertig={(fall) => { void load().then(() => open(fall)); }} />
      {/* Server-side project close (#157): files → DB record used by reports 2 and 3. */}
      <Abschluss />

      {loadError && (
        <div className={styles.banner} role="alert">
          <span>{loadError}</span>
          <button type="button" className={styles.knopfZweit} onClick={() => void load()}>{t("Try again")}</button>
        </div>
      )}

      <div className={styles.filter} role="group" aria-label={t("Filter by tag")}>
        <button type="button" className={styles.chip} aria-pressed={tag === null} onClick={() => setTag(null)}>{t("All")} <span>{cases?.length ?? 0}</span></button>
        {tags.map((t) => (
          <button key={t} type="button" className={styles.chip} aria-pressed={tag === t} onClick={() => setTag(tag === t ? null : t)}>
            {t} <span>{cases?.filter((c) => c.tags.includes(t)).length}</span>
          </button>
        ))}
        <span className={styles.sortiert}>{t("Newest first")}</span>
      </div>

      <div className={styles.layout}>
        <ul className={styles.liste} aria-label={t("Cases")}>
          {cases === null && !loadError && <li className={styles.leer}>{t("Loading cases …")}</li>}
          {cases !== null && shown.length === 0 && <li className={styles.leer}>{t("No cases with this tag.")}</li>}
          {shown.map((c) => (
            <li key={c.case_id}>
              <button type="button" className={`${styles.glas} ${styles.karte}`} aria-current={c.case_id === selected} onClick={() => open(c)}>
                <span className={styles.karteKopf}>
                  <span className={styles.id}>{c.case_id}</span>
                  <time dateTime={c.date}>{datum.format(new Date(c.date))}</time>
                </span>
                <span className={styles.titel}>{c.lv.name}</span>
                <span className={styles.beschreibung}>
                  {c.description}
                </span>
                {c.tags.length > 0 && <span className={styles.tags}>{c.tags.map((t) => <span key={t}>{t}</span>)}</span>}
              </button>
            </li>
          ))}
        </ul>

        <section className={`${styles.glas} ${styles.detail}`} aria-live="polite" aria-label={t("Case details")}>
          {!current || !draft ? (
            <p className={styles.hinweis}>{t("Select a case to see its estimates and record actual values.")}</p>
          ) : (
            <form onSubmit={save} className={styles.formular}>
              <header className={styles.detailKopf}>
                <p className={styles.eyebrow}>{current.case_id} · {datum.format(new Date(current.date))}</p>
                <h2>{current.lv.name}</h2>
                <p className={styles.beschreibung}>
                  {current.description}
                </p>
              </header>

              <fieldset className={styles.gruppe}>
                <legend>{t("Estimate and actual")}</legend>
                <div className={styles.rahmen}>
                  <table className={styles.tabelle}>
                    <thead><tr><th>{t("OZ")}</th><th>{t("Position")}</th><th>{t("Metric")}</th><th className={styles.rechts}>{t("Estimated")}</th><th>{t("Actual")}</th><th className={styles.rechts}>{t("Difference")}</th></tr></thead>
                    <tbody>
                      {current.estimated_values.map((m) => {
                        const k = key(m);
                        const raw = (draft.actuals[k] ?? "").trim().replace(",", ".");
                        const diff = raw !== "" && m.value !== null && !Number.isNaN(Number(raw)) ? Number(raw) - m.value : null;
                        return (
                          <tr key={k}>
                            <td className={styles.oz}>{m.oz}</td>
                            <td>{current.lv.positionen.find((p) => p.oz === m.oz)?.kurztext ?? ""}</td>
                            <td>{m.metric}</td>
                            <td className={styles.rechts}>{m.value === null ? "unknown" : `${zahl.format(m.value)} ${m.unit}`}</td>
                            <td>
                              <span className={styles.eingabe}>
                                <input
                                  id={`actual-${k}`} inputMode="decimal" aria-label={`Actual ${m.metric} for OZ ${m.oz} in ${m.unit}`}
                                  value={draft.actuals[k] ?? ""} placeholder="—" onChange={(e) => setActual(k, e.target.value)}
                                />
                                {m.unit}
                              </span>
                            </td>
                            <td className={`${styles.rechts} ${diff !== null && diff > 0 ? styles.mehr : ""}`}>
                              {diff === null ? "" : `${diff > 0 ? "+" : ""}${zahl.format(diff)} ${m.unit}`}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </fieldset>

              <fieldset className={styles.gruppe}>
                <legend>{t("Marks per position")}</legend>
                {current.lv.positionen.map((p) => (
                  <div key={p.oz} className={styles.mark} data-status={draft.marks[p.oz]?.status || undefined}>
                    <label className={styles.feld}>
                      <span><span className={styles.oz}>{p.oz}</span> {t("status")}</span>
                      <select value={draft.marks[p.oz]?.status ?? ""} onChange={(e) => setMark(p.oz, "status", e.target.value)}>
                        <option value="">{t("No mark")}</option>
                        {MARK_STATUSES.map((s) => <option key={s} value={s}>{t(s)}</option>)}
                      </select>
                    </label>
                    <label className={styles.feld}>
                      <span>{t("What happened")} <i>{t("optional")}</i></span>
                      <input value={draft.marks[p.oz]?.what_happened ?? ""} onChange={(e) => setMark(p.oz, "what_happened", e.target.value)} />
                    </label>
                    <label className={styles.feld}>
                      <span>{t("Why")} <i>{t("optional")}</i></span>
                      <input value={draft.marks[p.oz]?.reason ?? ""} onChange={(e) => setMark(p.oz, "reason", e.target.value)} />
                    </label>
                  </div>
                ))}
              </fieldset>

              <fieldset className={styles.gruppe}>
                <legend>{t("Comments")}</legend>
                {current.comments.length > 0 && <ul className={styles.kommentare}>{current.comments.map((c) => <li key={c}>{c}</li>)}</ul>}
                <label className={styles.feld}>
                  <span>{t("Add a comment")} <i>{t("optional")}</i></span>
                  <textarea rows={2} value={draft.comment} onChange={(e) => setDraft((d) => d && { ...d, comment: e.target.value })} />
                </label>
              </fieldset>

              {saveState.kind === "error" && <p className={styles.banner} role="alert">{saveState.text}</p>}
              <div className={styles.aktionen}>
                <button type="submit" className={styles.knopf} disabled={saveState.kind === "busy"}>{saveState.kind === "busy" ? "Saving …" : "Save"}</button>
                {saveState.kind === "ok" && <span className={styles.ok} role="status">{saveState.text}</span>}
              </div>
            </form>
          )}
        </section>
      </div>
    </div>
  );
}

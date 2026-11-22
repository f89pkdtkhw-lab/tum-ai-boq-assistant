"use client";

import type { AiEvaluation } from "@/lib/api";
import { useT } from "@/lib/einstellungen";
import { Info } from "../info/Info";
import styles from "./ki.module.css";

const ENTSCHEIDUNG = {
  go: { name: "Go", farbe: "var(--sev-ok)" },
  go_with_conditions: { name: "Go with conditions", farbe: "var(--sev-mittel-text)" },
  no_go: { name: "No go", farbe: "var(--sev-kritisch)" },
} as const;
const PRIORITAET: { wert: AiEvaluation["recommendations"][number]["priority"]; name: string }[] = [
  { wert: "now", name: "Now" }, { wert: "before_bid", name: "Before the bid" }, { wert: "pricing", name: "Pricing" }, { wert: "negotiation", name: "Negotiation" },
];
const euro = new Intl.NumberFormat("en-GB", { style: "currency", currency: "EUR", notation: "compact", maximumFractionDigits: 2 });

function wert(low: number | null, high: number | null, einheit: string) {
  const f = (v: number) => (einheit === "EUR" ? euro.format(v) : `${v} ${einheit}`);
  if (low === null && high === null) return "–";
  if (low === null || high === null || low === high) return f((low ?? high)!);
  return `${f(low)} – ${f(high)}`;
}

/** AI evaluation of the whole BoQ: decision, predictions with their basis, and recommendations by priority. */
export function KiBewertung({ daten, fehler }: { daten: AiEvaluation | null; fehler: string }) {
  const t = useT();
  return (
    <div className={styles.ki} aria-live="polite">
      <div className={styles.kopf}>
        <h4 className={styles.titel}><span className={styles.symbol} aria-hidden="true">✦</span>{t("AI evaluation")}</h4>
        {daten?.source === "model" ? (
          <span className={styles.quelle} title={t("Answered by the configured model from the evidence above; numbers outside the evidence are dropped.")}>
            {t("model")} · {daten.model ?? "live"}
          </span>
        ) : (
          <span className={styles.quelle} title={t("Derived only from the evidence above, without an AI model.")}>
            {t("evidence-based")}
          </span>
        )}
      </div>
      {!fehler && daten?.reason && <p className={styles.fehler} role="note">{t("AI model unavailable")}: {daten.reason}</p>}
      {fehler ? <p className={styles.fehler} role="alert">{t("AI evaluation unavailable")}: {fehler}</p>
        : !daten ? <p className={styles.hinweis}>{t("Evaluating the whole BoQ…")}</p>
        : (
          <>
            <div className={styles.urteil}>
              <span className={styles.entscheidung} style={{ background: ENTSCHEIDUNG[daten.decision].farbe }}>{t(ENTSCHEIDUNG[daten.decision].name)}</span>
              <div>
                <p className={styles.headline}>{daten.headline}</p>
                <p className={styles.summary}>{daten.summary}</p>
              </div>
            </div>

            {daten.predictions.length > 0 && (
              <>
                <h5 className={styles.unter}>{t("Predictions")}</h5>
                <ul className={styles.vorhersagen}>
                  {daten.predictions.map((p) => (
                    <li key={p.title}>
                      <span className={styles.vTitel}>{p.title} <Info text={p.basis} /></span>
                      <strong className={styles.vWert}>{wert(p.low, p.high, p.unit)}</strong>
                      <span className={`${styles.sicherheit} ${styles[`s_${p.confidence}`]}`}>{t("confidence")}: {t(p.confidence)}</span>
                    </li>
                  ))}
                </ul>
              </>
            )}

            <h5 className={styles.unter}>{t("Recommendations")}</h5>
            <div className={styles.empfehlungen}>
              {PRIORITAET.filter((g) => daten.recommendations.some((r) => r.priority === g.wert)).map((g) => (
                <div key={g.wert} className={styles.gruppe}>
                  <p className={styles.gruppenTitel}>{t(g.name)}</p>
                  <ul>
                    {daten.recommendations.filter((r) => r.priority === g.wert).map((r) => (
                      <li key={r.title}><strong>{r.title}</strong><span>{r.why}</span></li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </>
        )}
    </div>
  );
}

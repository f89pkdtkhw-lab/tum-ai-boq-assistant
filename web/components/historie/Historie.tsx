"use client";

import { useDok } from "@/components/dok/useDok";
import { useEffect, useState } from "react";
import { historyApi, similarPositions, type HistoryCase, type Measurement } from "@/lib/history-api";
import styles from "./historie.module.css";
import { useT } from "@/lib/einstellungen";

const zahl = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 1 });
const MARK_FARBE: Record<string, string> = { confirmed: "ok", open: "mittel", deviation: "hoch" };

/** Actual vs. estimate as a danger colour: within 10 % green, within 25 % yellow, else red. */
function abweichung(est: Measurement | undefined, real: Measurement | undefined) {
  if (!est?.value || real?.value == null) return null;
  const prozent = ((real.value - est.value) / est.value) * 100;
  const stufe = Math.abs(prozent) <= 10 ? "ok" : Math.abs(prozent) <= 25 ? "mittel" : "kritisch";
  return { prozent, stufe };
}

/** Past cases from the history store with the same work type as the selected item. */
export function Historie({ oz, kurztext }: { oz: string; kurztext: string | null }) {
  const d = useDok();
  const [faelle, setFaelle] = useState<HistoryCase[] | null>(null);
  const [fehler, setFehler] = useState("");
  const t = useT();

  useEffect(() => {
    historyApi.list(null, 100).then(setFaelle).catch((e: Error) => setFehler(e.message));
  }, []);

  const treffer = faelle ? similarPositions(faelle, kurztext) : [];
  return (
    <details className={styles.historie} aria-label={t("History for OZ {oz}", { oz })}>
      <summary>{t("History from past projects")}{faelle ? ` (${treffer.length})` : ""}</summary>
      {fehler ? <p className={styles.fehler} role="alert">{t("History could not be loaded:")} {fehler}</p>
        : faelle === null ? <p className={styles.hinweis}>{t("Loading history…")}</p>
        : treffer.length === 0 ? <p className={styles.hinweis}>{t("No past project has an item of this work type yet.")}</p>
        : (
          <ul className={styles.liste}>
            {treffer.map((p) => {
              const est = p.estimated[0];
              const real = p.real.find((r) => r.metric === est?.metric) ?? p.real[0];
              const dev = abweichung(est, real);
              const farbe = dev?.stufe ?? (p.mark ? MARK_FARBE[p.mark.status] : undefined);
              return (
                <li key={`${p.case.case_id}-${p.oz}`} className={styles.fall} style={{ "--sev": farbe ? `var(--sev-${farbe})` : undefined } as React.CSSProperties}>
                  <p className={styles.kopf}>
                    <strong>{p.case.lv.name}</strong>
                    <span className={styles.klein}>{p.case.date} · OZ {p.oz}</span>
                  </p>
                  <p className={styles.klein}>{d(p.kurztext)}</p>
                  <dl className={styles.werte}>
                    <div><dt>{t("Estimate")}</dt><dd>{est?.value != null ? `${zahl.format(est.value)} ${est.unit}` : "–"}</dd></div>
                    <div><dt>{t("Actual")}</dt><dd>{real?.value != null ? `${zahl.format(real.value)} ${real.unit}` : t("not recorded")}</dd></div>
                    {dev && <div><dt>{t("Deviation")}</dt><dd>{dev.prozent > 0 ? "+" : ""}{zahl.format(dev.prozent)} %</dd></div>}
                  </dl>
                  {p.mark && (
                    <p className={styles.klein}>
                      {t("Marked")} <strong>{t(p.mark.status)}</strong>{p.mark.what_happened ? `: ${p.mark.what_happened}` : ""}{p.mark.reason ? ` (${p.mark.reason})` : ""}
                    </p>
                  )}
                  {p.case.comments.map((c) => <p key={c} className={styles.kommentar}>{t("Project note:")} “{c}”</p>)}
                </li>
              );
            })}
          </ul>
        )}
    </details>
  );
}

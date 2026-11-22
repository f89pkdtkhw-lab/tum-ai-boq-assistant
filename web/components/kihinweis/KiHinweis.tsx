"use client";

import type { KiHinweis as Hinweis } from "@/lib/kischritte";
import { useT } from "@/lib/einstellungen";
import { Icon } from "../icon/Icon";
import styles from "./kihinweis.module.css";

/**
 * D (#168): visible notice per AI step that failed or could not use the configured model, e.g.
 * "AI position review failed: <reason>". Renders nothing when every AI step ran as configured.
 */
export function KiHinweis({ hinweise }: { hinweise: Hinweis[] }) {
  const t = useT();
  if (!hinweise.length) return null;
  const fehler = hinweise.some((h) => h.status === "fehler");
  return (
    <div className={`${styles.glas} ${fehler ? styles.fehler : styles.mock}`} role="alert">
      <p className={styles.kopf}>
        <Icon name={fehler ? "alert" : "warning"} />
        <strong>{t(hinweise.length === 1 ? "An AI step did not run as configured" : "{n} AI steps did not run as configured", { n: hinweise.length })}</strong>
      </p>
      <ul className={styles.liste}>
        {hinweise.map((h) => (
          <li key={h.schritt} className={h.status === "fehler" ? styles.fehler : styles.mock}>
            <b>{t(h.status === "fehler" ? "{step} failed" : "{step} ran without the AI model", { step: t(h.titel) })}</b>
            {h.grund && <>: <span className={styles.grund}>{h.grund}</span></>}
          </li>
        ))}
      </ul>
      <p className={styles.unter}>{t("The rest of the report is complete. Results of these steps are missing or incomplete.")}</p>
    </div>
  );
}

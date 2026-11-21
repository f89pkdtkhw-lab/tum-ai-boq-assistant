"use client";
// E #169: deep web research. A short status note for the report and the sources of one finding.
import type { Recherche, RechercheErgebnis } from "@/lib/api";
import { useT } from "@/lib/einstellungen";
import styles from "./recherche.module.css";

const EINSCHAETZUNG: Record<RechercheErgebnis["einschaetzung"], string> = {
  bestaetigt: "confirmed", abgeschwaecht: "weakened", unklar: "unclear",
  plausibel: "plausible", zu_hoch: "above market", zu_niedrig: "below market",
};

export function RechercheHinweis({ recherche }: { recherche: Recherche }) {
  const t = useT();
  const art = recherche.status === "ok" ? styles.ok : recherche.status === "aus" ? styles.aus : styles.problem;
  return (
    <p className={`${styles.hinweis} ${art}`} role={recherche.status === "fehler" ? "alert" : "note"}>
      <strong>{t("Web research:")}</strong> {recherche.meldung}
    </p>
  );
}

export function RechercheQuellen({ ergebnisse }: { ergebnisse: RechercheErgebnis[] }) {
  const t = useT();
  if (ergebnisse.length === 0) return null;
  return (
    <>
      <dt>{t("Web research")}</dt>
      <dd>
        <ul className={styles.liste}>
          {ergebnisse.map((r, i) => (
            <li key={`${r.schritt}-${i}`}>
              <span className={styles.marke}>{t(EINSCHAETZUNG[r.einschaetzung])}</span> {r.text}
              <ul className={styles.quellen}>
                {r.quellen.map((q) => (
                  <li key={q.url}><a href={q.url} target="_blank" rel="noopener noreferrer">{q.titel || q.url}</a></li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      </dd>
    </>
  );
}

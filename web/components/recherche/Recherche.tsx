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
  // Failures (fehler/teilweise) are also an AI step status (ki_schritte, D #168) and shown by KiHinweis there.
  if (recherche.status === "fehler" || recherche.status === "teilweise") return null;
  return (
    <p className={`${styles.hinweis} ${recherche.status === "ok" ? styles.ok : styles.aus}`} role="note">
      <strong>{t("Web research:")}</strong> {recherche.meldung}
    </p>
  );
}

function Liste({ ergebnisse }: { ergebnisse: RechercheErgebnis[] }) {
  const t = useT();
  return (
    <div className={styles.liste}>
      {ergebnisse.map((r, i) => (
        <div key={`${r.schritt}-${i}`} className={styles.eintrag}>
          <span><span className={styles.marke}>{t(EINSCHAETZUNG[r.einschaetzung])}</span> {r.text}</span>
          <span className={styles.quellen}>
            {t("Sources")}:{" "}
            {r.quellen.map((q, k) => (
              <span key={q.url}>{k > 0 && " · "}<a href={q.url} target="_blank" rel="noopener noreferrer">{q.titel || q.url}</a></span>
            ))}
          </span>
        </div>
      ))}
    </div>
  );
}

/** Sources of one finding as a `<dt>/<dd>` pair inside a definition list (finding detail). */
export function RechercheQuellen({ ergebnisse }: { ergebnisse: RechercheErgebnis[] }) {
  const t = useT();
  if (ergebnisse.length === 0) return null;
  return (<><dt>{t("Web research")}</dt><dd><Liste ergebnisse={ergebnisse} /></dd></>);
}

/** Sources of one finding as a block (expanded row of the report list). */
export function RechercheAbsatz({ ergebnisse }: { ergebnisse: RechercheErgebnis[] }) {
  const t = useT();
  if (ergebnisse.length === 0) return null;
  return (<div className={styles.absatz}><b>{t("Web research")}:</b><Liste ergebnisse={ergebnisse} /></div>);
}

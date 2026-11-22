"use client";

import Link from "next/link";
import styles from "./saas.module.css";
import { useKonto } from "@/lib/saas/client";
import { useEinstellungen } from "@/lib/einstellungen";

/** Soft quota banner above the upload. Shows only for signed-in users at or near their limit; never blocks. */
export function KontingentHinweis() {
  const { t } = useEinstellungen();
  const { konto } = useKonto();
  const k = konto?.kontingent;
  if (!konto?.angemeldet || !k || k.quota === null || k.remaining === null) return null;
  if (!k.ueber && k.remaining > 1) return null;
  const anteil = Math.min(100, (k.used / Math.max(1, k.quota)) * 100);
  return (
    <div className={styles.banner} role="status">
      <div className={styles.bannerText}>
        <strong>
          {k.ueber
            ? t("You have used all {n} evaluations of your plan this month.", { n: k.quota })
            : t("{r} of {n} evaluations left this month.", { r: k.remaining, n: k.quota })}
        </strong>{" "}
        {k.ueber && <span className={styles.hinweis}>{t("You can keep evaluating for now; upgrade for more.")}</span>}
        <div className={styles.balken} style={{ marginTop: 6 }}><span style={{ width: `${anteil}%` }} /></div>
      </div>
      <Link href="/tarife" className={styles.knopf}>{t("Upgrade")}</Link>
    </div>
  );
}

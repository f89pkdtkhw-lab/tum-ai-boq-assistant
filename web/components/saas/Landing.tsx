"use client";

import Link from "next/link";
import styles from "./saas.module.css";
import { Icon, type IconName } from "@/components/icon/Icon";
import { Logo } from "@/components/logo/Logo";
import { useEinstellungen } from "@/lib/einstellungen";

const FEATURES: { icon: IconName; titel: string; text: string }[] = [
  { icon: "search", titel: "Find errors before the bid", text: "Rule, quantity and AI checks flag missing quantities, unclear specs and contradictions, each with its item number." },
  { icon: "warning", titel: "Spot change-order risks", text: "See where the BoQ leaves room for claims, with research links and the page in the PDF." },
  { icon: "euro", titel: "Price with your history", text: "Estimated bill from your price list and past projects, plus a margin slider against competitors." },
  { icon: "gauge", titel: "One clear score", text: "Risk score with five selectable rating styles, so the verdict fits how your company bids." },
  { icon: "download", titel: "Export the offer", text: "Excel and PDF export of the final offer, ready for the tender portal." },
  { icon: "history", titel: "Learn from final bills", text: "Upload estimate and final bill after the project; LV Scout learns your deviations per trade." },
];

export function Landing() {
  const { t } = useEinstellungen();
  return (
    <main className={styles.seite}>
      <section className={styles.hero}>
        <div style={{ display: "grid", gap: 14 }}>
          <span className={styles.marke}><Logo size={36} />LV Scout</span>
          <h1 className={styles.titel}>{t("Scout every bill of quantities before you bid.")}</h1>
          <p className={styles.lead}>{t("LV Scout reads GAEB, Excel and PDF tenders, checks every item against rules and standards, and shows risks, prices and margin in six simple steps.")}</p>
          <div className={styles.knoepfe}>
            <Link href="/" className={styles.knopf}>{t("Start free evaluation")}</Link>
            <Link href="/tarife" className={styles.knopfZweit}>{t("See plans")}</Link>
          </div>
          <p className={styles.hinweis}>{t("Free: 3 evaluations per month. No credit card needed.")}</p>
        </div>
        <div className={styles.heroBild} aria-hidden="true">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/logo-mark.png" alt="" />
        </div>
      </section>
      <section className={styles.features} aria-label={t("Features")}>
        {FEATURES.map((f) => (
          <article key={f.titel} className={styles.feature}>
            <span className={styles.featureIcon}><Icon name={f.icon} size={18} /></span>
            <h3>{t(f.titel)}</h3>
            <p>{t(f.text)}</p>
          </article>
        ))}
      </section>
      <section className={styles.karte} style={{ textAlign: "center", justifyItems: "center" }}>
        <h2 style={{ margin: 0 }}>{t("Built for estimators and bid teams")}</h2>
        <p className={styles.hinweis}>{t("Pro for single estimators, Company with seats for whole teams.")}</p>
        <Link href="/tarife" className={styles.knopf}>{t("Compare plans")}</Link>
      </section>
    </main>
  );
}

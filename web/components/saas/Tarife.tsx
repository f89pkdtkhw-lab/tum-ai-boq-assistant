"use client";

import Link from "next/link";
import { useState } from "react";
import styles from "./saas.module.css";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { PLAENE, type Intervall } from "@/lib/saas/plaene";
import { starteCheckout, useKonto } from "@/lib/saas/client";
import { useEinstellungen } from "@/lib/einstellungen";

const euro = (n: number, sprache: string) => new Intl.NumberFormat(sprache === "de" ? "de-DE" : "en-GB", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(n);

export function Tarife() {
  const { t, e } = useEinstellungen();
  const { konto } = useKonto();
  const [intervall, setIntervall] = useState<Intervall>("month");
  const [seats, setSeats] = useState(5);
  const [busy, setBusy] = useState("");
  const [fehler, setFehler] = useState("");
  const stripe = konto?.konfiguriert.stripe ?? false;

  const kaufen = async (plan: "pro" | "company") => {
    setFehler("");
    if (!konto?.angemeldet) { window.location.href = `/konto?weiter=${plan}`; return; }
    if (!stripe) { setFehler(t("Payments are not set up yet. Ask an admin to unlock your plan.")); return; }
    setBusy(plan);
    try { await starteCheckout(plan, intervall, plan === "company" ? seats : 1); }
    catch (err) { setFehler(err instanceof Error ? err.message : String(err)); setBusy(""); }
  };

  return (
    <main className={styles.seite}>
      <header className={styles.tarifKopf}>
        <p className={styles.kicker}>{t("Plans")}</p>
        <h1 className={styles.titel}>{t("Review every BoQ before you bid")}</h1>
        <p className={styles.lead}>{t("Start free. Upgrade when your team evaluates more tenders.")}</p>
        <SegmentedControl ariaLabel={t("Billing period")} value={intervall} onChange={setIntervall}
          options={[{ value: "month", label: t("Monthly") }, { value: "year", label: <>{t("Yearly")} <span className={styles.planTag}>−17%</span></> }]} />
      </header>
      {fehler && <p className={styles.fehler} role="alert">{fehler}</p>}
      <div className={styles.tarife}>
        {PLAENE.map((p) => {
          const aktuell = konto?.angemeldet && konto.plan === p.id;
          const preis = intervall === "year" ? p.preisJahr : p.preisMonat;
          return (
            <section key={p.id} className={`${styles.tarif} ${p.id === "pro" ? styles.tarifTop : ""}`}>
              {p.id === "pro" && <span className={styles.abzeichen}>{t("Most popular")}</span>}
              <h2 className={styles.tarifName}>{t(p.name)} {aktuell && <span className={styles.aktuell}>· {t("Your plan")}</span>}</h2>
              <p className={styles.preis}>
                <strong>{euro(preis, e.sprache)}</strong>
                <span>{p.id === "free" ? t("forever") : p.id === "company" ? t(intervall === "year" ? "per seat / year" : "per seat / month") : t(intervall === "year" ? "per year" : "per month")}</span>
              </p>
              <p className={styles.quota}>
                <strong>{p.quota}</strong>
                <span>{t(p.id === "company" ? "evaluations per seat / month" : "evaluations / month")}</span>
              </p>
              <ul className={styles.liste}>{p.features.map((f) => <li key={f}>{t(f)}</li>)}</ul>
              {p.id === "free" ? (
                <Link href={konto?.angemeldet ? "/" : "/konto"} className={styles.knopfZweit}>{t(konto?.angemeldet ? "Start evaluating" : "Sign up free")}</Link>
              ) : (
                <div style={{ display: "grid", gap: 8 }}>
                  {p.id === "company" && (
                    <label className={styles.feld}>{t("Seats")}
                      <input className={styles.eingabe} type="number" min={1} max={500} value={seats} onChange={(ev) => setSeats(Math.max(1, Number(ev.target.value) || 1))} />
                    </label>
                  )}
                  <button type="button" className={p.id === "pro" ? styles.knopf : styles.knopfZweit} disabled={Boolean(busy) || aktuell} onClick={() => void kaufen(p.id as "pro" | "company")}>
                    {busy === p.id ? t("Opening checkout …") : aktuell ? t("Your plan") : p.id === "company" ? t("Get Company · {n} seats", { n: seats }) : t("Upgrade to Pro")}
                  </button>
                </div>
              )}
            </section>
          );
        })}
      </div>
      <p className={styles.hinweis} style={{ textAlign: "center" }}>
        {t("Prices in EUR.")}{" "}
        {t("Larger company? We unlock company plans by hand.")}
      </p>
    </main>
  );
}

"use client";

import Link from "next/link";
import styles from "./saas.module.css";
import { useKonto } from "@/lib/saas/client";
import { useEinstellungen } from "@/lib/einstellungen";
import { useEffect } from "react";
import { setzeBesitzer } from "@/lib/vault";

export function planKlasse(plan: string): string {
  return plan === "pro" ? `${styles.planTag} ${styles.planPro}` : plan === "company" ? `${styles.planTag} ${styles.planCompany}` : styles.planTag;
}

export const PLAN_LABEL: Record<string, string> = { gast: "Guest", free: "Free", pro: "Pro", company: "Company" };

/** Top bar: avatar + plan, or "Sign in". Hidden until /api/saas/me answered, so nothing flickers when it is missing. */
export function KontoChip() {
  const { t } = useEinstellungen();
  const { konto } = useKonto();
  // t243: vault entries record the signed-in e-mail as owner (local vault on this machine, shared by all accounts).
  useEffect(() => { setzeBesitzer(konto?.angemeldet ? konto.email : null); }, [konto]);
  if (!konto) return null;
  if (!konto.angemeldet) {
    return (
      <Link href="/konto" className={styles.chip} title={t("Sign in")}>
        <span className={styles.avatar}>→</span>{t("Sign in")}<span className={planKlasse("gast")}>{t("Guest")}</span>
      </Link>
    );
  }
  const name = konto.name || konto.email || "";
  return (
    <Link href="/konto" className={styles.chip} title={konto.email ?? undefined}>
      <span className={styles.avatar}>{name.slice(0, 1).toUpperCase()}</span>
      <span>{name.length > 18 ? `${name.slice(0, 17)}…` : name}</span>
      <span className={planKlasse(konto.plan)}>{t(PLAN_LABEL[konto.plan])}</span>
    </Link>
  );
}

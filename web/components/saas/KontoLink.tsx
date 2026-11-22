"use client";
// Targets of the emailed links: confirm the email address, or set a new password.

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import styles from "./saas.module.css";
import { Logo } from "@/components/logo/Logo";
import { useEinstellungen } from "@/lib/einstellungen";

async function post(url: string, body: unknown): Promise<string | null> {
  const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (r.ok) return null;
  const j = (await r.json().catch(() => ({}))) as { fehler?: string };
  return j.fehler || `HTTP ${r.status}`;
}

function Rahmen({ titel, children }: { titel: string; children: React.ReactNode }) {
  return (
    <main className={`${styles.seite} ${styles.schmal}`} style={{ maxWidth: 440 }}>
      <header style={{ display: "grid", justifyItems: "center", gap: 8, textAlign: "center", paddingTop: 24 }}>
        <Logo size={48} />
        <h1 className={styles.titel} style={{ fontSize: 28 }}>{titel}</h1>
      </header>
      <section className={styles.karte}>{children}</section>
    </main>
  );
}

export function EmailBestaetigen() {
  const { t } = useEinstellungen();
  const params = useSearchParams();
  const [stand, setStand] = useState<"laeuft" | "ok" | string>("laeuft");
  const einmal = useRef(false);
  useEffect(() => {
    if (einmal.current) return;
    einmal.current = true;
    void post("/api/saas/bestaetigen", { email: params.get("email"), token: params.get("token") })
      .then((f) => setStand(f ?? "ok")).catch(() => setStand("This link is invalid or has expired."));
  }, [params]);
  return (
    <Rahmen titel={t("Confirm email")}>
      {stand === "laeuft" && <p className={styles.hinweis}>{t("Loading …")}</p>}
      {stand === "ok" && <p className={styles.ok} role="status">{t("Your email is confirmed. You can sign in now.")}</p>}
      {stand !== "laeuft" && stand !== "ok" && <p className={styles.fehler} role="alert">{t(stand)}</p>}
      <Link href="/konto" className={styles.knopf}>{t("Sign in")}</Link>
    </Rahmen>
  );
}

export function PasswortNeu() {
  const { t } = useEinstellungen();
  const params = useSearchParams();
  const [passwort, setPasswort] = useState("");
  const [busy, setBusy] = useState(false);
  const [fehler, setFehler] = useState("");
  const [fertig, setFertig] = useState(false);
  const absenden = async (ev: React.FormEvent) => {
    ev.preventDefault();
    setBusy(true);
    setFehler("");
    try {
      const f = await post("/api/saas/passwort-neu", { email: params.get("email"), token: params.get("token"), password: passwort });
      if (f) setFehler(t(f)); else setFertig(true);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Rahmen titel={t("Set a new password")}>
      {fertig ? (
        <>
          <p className={styles.ok} role="status">{t("Your password was changed. You can sign in now.")}</p>
          <Link href="/konto" className={styles.knopf}>{t("Sign in")}</Link>
        </>
      ) : (
        <form onSubmit={absenden} style={{ display: "grid", gap: 10 }}>
          <p className={styles.hinweis}>{params.get("email")}</p>
          <label className={styles.feld}>{t("New password")}
            <input className={styles.eingabe} type="password" required minLength={8} autoComplete="new-password" value={passwort} onChange={(ev) => setPasswort(ev.target.value)} />
          </label>
          <p className={styles.hinweis}>{t("At least 8 characters.")}</p>
          <button type="submit" className={styles.knopf} disabled={busy}>{busy ? t("Please wait …") : t("Save password")}</button>
          {fehler && <p className={styles.fehler} role="alert">{fehler}</p>}
        </form>
      )}
    </Rahmen>
  );
}

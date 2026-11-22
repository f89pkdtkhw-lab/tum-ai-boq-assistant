"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { signIn, signOut } from "next-auth/react";
import styles from "./saas.module.css";
import { Logo } from "@/components/logo/Logo";
import { oeffnePortal, synchronisiere, useKonto } from "@/lib/saas/client";
import { useEinstellungen } from "@/lib/einstellungen";
import { PLAN_LABEL, planKlasse } from "./KontoChip";

const GOOGLE = "M21.8 12.2c0-.7-.1-1.4-.2-2H12v3.8h5.5a4.7 4.7 0 0 1-2 3.1v2.6h3.3c1.9-1.8 3-4.4 3-7.5ZM12 22c2.7 0 5-.9 6.8-2.4l-3.3-2.6c-.9.6-2.1 1-3.5 1-2.7 0-4.9-1.8-5.7-4.2H2.9v2.6A10 10 0 0 0 12 22Zm-5.7-8.2a6 6 0 0 1 0-3.6V7.6H2.9a10 10 0 0 0 0 8.8l3.4-2.6ZM12 6c1.5 0 2.8.5 3.9 1.5l2.9-2.9A10 10 0 0 0 2.9 7.6l3.4 2.6C7.1 7.8 9.3 6 12 6Z";

export function KontoSeite() {
  const { t, e } = useEinstellungen();
  const { konto, neu } = useKonto();
  const params = useSearchParams();
  const [modus, setModus] = useState<"anmelden" | "registrieren" | "vergessen">("anmelden");
  const [email, setEmail] = useState("");
  const [passwort, setPasswort] = useState("");
  const [name, setName] = useState("");
  const [unbestaetigt, setUnbestaetigt] = useState(false);
  const [busy, setBusy] = useState(false);
  const [fehler, setFehler] = useState("");
  const [meldung, setMeldung] = useState("");
  const weiter = params.get("weiter");
  const checkout = params.get("checkout");

  useEffect(() => {
    if (checkout !== "ok" || !konto?.angemeldet) return;
    setMeldung(t("Thanks! Your subscription is being activated …"));
    synchronisiere().then(() => { setMeldung(t("Subscription active.")); neu(); }).catch((err) => setFehler(err instanceof Error ? err.message : String(err)));
    // run once after the redirect from Stripe
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [checkout, konto?.angemeldet]);

  const ziel = weiter === "pro" || weiter === "company" ? "/tarife" : "/konto";

  const postJson = async (url: string, body: unknown) => {
    const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const j = (await r.json().catch(() => ({}))) as { fehler?: string };
    return { ok: r.ok, fehler: j.fehler };
  };

  const absenden = async (ev: React.FormEvent) => {
    ev.preventDefault();
    setFehler("");
    setMeldung("");
    setUnbestaetigt(false);
    setBusy(true);
    try {
      if (modus === "vergessen") {
        await postJson("/api/saas/passwort-vergessen", { email: email.trim() });
        setMeldung(t("If an account with this email exists, we sent a link to reset the password."));
        return;
      }
      if (modus === "registrieren") {
        const r = await postJson("/api/saas/registrieren", { email: email.trim(), password: passwort, name: name.trim() });
        if (!r.ok) { setFehler(t(r.fehler || "Registration failed.")); return; }
        setModus("anmelden");
        setPasswort("");
        setMeldung(t("Almost done: we sent a confirmation link to {email}. Open it, then sign in.", { email: email.trim() }));
        return;
      }
      const r = await signIn("passwort", { email: email.trim(), password: passwort, redirect: false });
      if (r?.code === "unbestaetigt") { setUnbestaetigt(true); setFehler(t("Please confirm your email first. Check your inbox for the link.")); return; }
      if (r?.error) { setFehler(t("Email or password is wrong.")); return; }
      window.location.href = ziel;
    } finally {
      setBusy(false);
    }
  };

  const erneutSenden = async () => {
    setBusy(true);
    try {
      await postJson("/api/saas/bestaetigung-erneut", { email: email.trim() });
      setFehler("");
      setUnbestaetigt(false);
      setMeldung(t("We sent a new confirmation link to {email}.", { email: email.trim() }));
    } finally {
      setBusy(false);
    }
  };

  const portal = async () => {
    setFehler("");
    try { await oeffnePortal(); } catch (err) { setFehler(err instanceof Error ? err.message : String(err)); }
  };

  if (!konto) return <main className={`${styles.seite} ${styles.schmal}`}><p className={styles.hinweis}>{t("Loading …")}</p></main>;

  if (!konto.angemeldet) {
    const reg = modus === "registrieren";
    const vergessen = modus === "vergessen";
    const wechsel = (m: typeof modus) => { setModus(m); setFehler(""); setMeldung(""); setUnbestaetigt(false); };
    return (
      <main className={`${styles.seite} ${styles.schmal}`} style={{ maxWidth: 440 }}>
        <header style={{ display: "grid", justifyItems: "center", gap: 8, textAlign: "center", paddingTop: 24 }}>
          <Logo size={48} />
          <h1 className={styles.titel} style={{ fontSize: 28 }}>{t(reg ? "Create your LV Scout account" : vergessen ? "Reset your password" : "Sign in to LV Scout")}</h1>
          <p className={styles.hinweis}>{t("Your plan and evaluation quota follow your account.")}</p>
        </header>
        <section className={styles.karte}>
          <button type="button" className={styles.knopfZweit} disabled={!konto.konfiguriert.google} aria-disabled={!konto.konfiguriert.google}
            title={konto.konfiguriert.google ? undefined : t("Google sign-in is not set up")}
            style={konto.konfiguriert.google ? undefined : { opacity: 0.5, cursor: "not-allowed" }}
            onClick={() => { if (konto.konfiguriert.google) void signIn("google", { redirectTo: ziel }); }}>
            <svg viewBox="0 0 24 24" width={18} height={18} aria-hidden="true"><path d={GOOGLE} fill="currentColor" /></svg>
            {t("Continue with Google")}
          </button>
          {!konto.konfiguriert.google && <p className={styles.hinweis} style={{ textAlign: "center" }}>{t("Google sign-in is not set up (AUTH_GOOGLE_ID / AUTH_GOOGLE_SECRET in web/.env.local).")}</p>}
          <p className={styles.hinweis} style={{ textAlign: "center" }}>{t("or")}</p>
          <form onSubmit={absenden} style={{ display: "grid", gap: 10 }}>
            {reg && (
              <label className={styles.feld}>{t("Name")}
                <input className={styles.eingabe} type="text" autoComplete="name" value={name} onChange={(ev) => setName(ev.target.value)} />
              </label>
            )}
            <label className={styles.feld}>{t("Email")}
              <input className={styles.eingabe} type="email" required autoComplete="email" value={email} onChange={(ev) => setEmail(ev.target.value)} placeholder="name@firma.de" />
            </label>
            {!vergessen && (
              <label className={styles.feld}>{t("Password")}
                <input className={styles.eingabe} type="password" required minLength={reg ? 8 : undefined} autoComplete={reg ? "new-password" : "current-password"} value={passwort} onChange={(ev) => setPasswort(ev.target.value)} />
              </label>
            )}
            {reg && <p className={styles.hinweis}>{t("At least 8 characters.")}</p>}
            <button type="submit" className={styles.knopf} disabled={busy}>{busy ? t("Please wait …") : t(reg ? "Create account" : vergessen ? "Send reset link" : "Sign in")}</button>
            {modus === "anmelden" && <button type="button" className={styles.link} style={{ justifySelf: "start" }} onClick={() => wechsel("vergessen")}>{t("Forgot password?")}</button>}
          </form>
          <p className={styles.hinweis} style={{ textAlign: "center" }}>
            {reg || vergessen ? t("Already have an account?") : t("No account yet?")}{" "}
            <button type="button" className={styles.link} onClick={() => wechsel(reg || vergessen ? "anmelden" : "registrieren")}>{t(reg || vergessen ? "Sign in" : "Create account")}</button>
          </p>
          {meldung && <p className={styles.ok} role="status">{meldung}</p>}
          {fehler && <p className={styles.fehler} role="alert">{fehler}</p>}
          {unbestaetigt && <button type="button" className={styles.knopfZweit} disabled={busy} onClick={() => void erneutSenden()}>{t("Send confirmation link again")}</button>}
        </section>
        <p className={styles.hinweis} style={{ textAlign: "center" }}>
          <Link href="/">{t("Continue without an account")}</Link> · <Link href="/tarife">{t("See plans")}</Link>
        </p>
      </main>
    );
  }

  const k = konto.kontingent;
  const anteil = k.quota ? Math.min(100, (k.used / k.quota) * 100) : 0;
  const datum = (iso: string | null | undefined) => (iso ? new Date(iso).toLocaleDateString(e.sprache === "de" ? "de-DE" : "en-GB") : "–");

  return (
    <main className={`${styles.seite} ${styles.schmal}`}>
      <header>
        <p className={styles.kicker}>{t("Account")}</p>
        <h1 className={styles.titel}>{konto.name || konto.email}</h1>
        <p className={styles.hinweis}>{konto.email}</p>
      </header>
      {meldung && <p className={styles.ok} role="status">{meldung}</p>}
      {fehler && <p className={styles.fehler} role="alert">{fehler}</p>}
      <section className={styles.karte}>
        <div className={styles.knoepfe} style={{ justifyContent: "space-between" }}>
          <strong>{t("Plan")} <span className={planKlasse(konto.plan)}>{t(PLAN_LABEL[konto.plan])}</span></strong>
          <Link href="/tarife" className={styles.knopfZweit}>{t(konto.plan === "free" ? "Upgrade" : "Change plan")}</Link>
        </div>
        {k.quota !== null && (
          <div style={{ display: "grid", gap: 6 }}>
            <span>{t("{u} of {n} evaluations used this month", { u: k.used, n: k.quota })}</span>
            <div className={styles.balken}><span style={{ width: `${anteil}%` }} /></div>
          </div>
        )}
        {konto.firma && <p className={styles.hinweis}>{t("Company: {name} · {s} seats · valid until {d}", { name: konto.firma.name, s: konto.firma.seats, d: konto.firma.expiresAt ? datum(konto.firma.expiresAt) : t("unlimited") })}</p>}
        {konto.abo && <p className={styles.hinweis}>{t("Subscription: {s} · renews {d}", { s: konto.abo.status, d: datum(konto.abo.periodEnd) })}</p>}
        <div className={styles.knoepfe}>
          {konto.konfiguriert.stripe && konto.kunde && <button type="button" className={styles.knopfZweit} onClick={() => void portal()}>{t("Manage subscription")}</button>}
          {konto.admin && <Link href="/admin" className={styles.knopfZweit}>{t("Admin")}</Link>}
          <button type="button" className={styles.knopfZweit} onClick={() => void signOut({ redirectTo: "/konto" })}>{t("Sign out")}</button>
        </div>
      </section>
    </main>
  );
}

"use client";

import { useCallback, useEffect, useState } from "react";
import styles from "./saas.module.css";
import { useEinstellungen } from "@/lib/einstellungen";
import { PLAN_LABEL, planKlasse } from "./KontoChip";

type Firma = { id: string; name: string; seats: number; expiresAt: string | null; members: string[]; quelle: string; aktiv: boolean };
type Nutzer = { email: string; name: string | null; plan: string; used: number; companyId: string | null; subscriptionStatus: string | null };
type Daten = { users: Nutzer[]; companies: Firma[] };
const CODE = "lv-admin-code";

export function AdminSeite() {
  const { t, e } = useEinstellungen();
  const [code, setCode] = useState("");
  const [daten, setDaten] = useState<Daten | null>(null);
  const [gesperrt, setGesperrt] = useState(false);
  const [fehler, setFehler] = useState("");
  const [form, setForm] = useState({ id: "", name: "", seats: 5, expiresAt: "", members: "" });

  const anfrage = useCallback(async (methode: "GET" | "POST", body?: unknown, c?: string) => {
    const gespeichert = c ?? (typeof window !== "undefined" ? window.sessionStorage.getItem(CODE) ?? "" : "");
    const r = await fetch("/api/saas/admin", { method: methode, cache: "no-store", headers: { "Content-Type": "application/json", "x-admin-code": gespeichert }, body: body ? JSON.stringify(body) : undefined });
    const j = await r.json().catch(() => ({}));
    if (r.status === 403) { setGesperrt(true); setDaten(null); return; }
    if (!r.ok) throw new Error(j.fehler || `HTTP ${r.status}`);
    setGesperrt(false);
    setDaten(j as Daten);
  }, []);

  useEffect(() => { anfrage("GET").catch((err) => setFehler(String(err.message ?? err))); }, [anfrage]);

  const entsperren = async (ev: React.FormEvent) => {
    ev.preventDefault();
    try { window.sessionStorage.setItem(CODE, code.trim()); } catch { /* memory only */ }
    setFehler("");
    await anfrage("GET", undefined, code.trim()).catch((err) => setFehler(String(err.message ?? err)));
    setCode("");
  };

  const speichern = async (ev: React.FormEvent) => {
    ev.preventDefault();
    setFehler("");
    try {
      await anfrage("POST", { aktion: "firma", id: form.id || undefined, name: form.name, seats: form.seats, expiresAt: form.expiresAt || null, members: form.members.split(/[\s,;]+/).filter(Boolean) });
      setForm({ id: "", name: "", seats: 5, expiresAt: "", members: "" });
    } catch (err) { setFehler(err instanceof Error ? err.message : String(err)); }
  };

  const bearbeiten = (f: Firma) => setForm({ id: f.id, name: f.name, seats: f.seats, expiresAt: f.expiresAt ? f.expiresAt.slice(0, 10) : "", members: f.members.join(", ") });
  const loeschen = (f: Firma) => {
    if (!window.confirm(t("Remove the company plan for {name}?", { name: f.name }))) return;
    anfrage("POST", { aktion: "firma-loeschen", id: f.id }).catch((err) => setFehler(String(err.message ?? err)));
  };
  const datum = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString(e.sprache === "de" ? "de-DE" : "en-GB") : t("unlimited"));

  return (
    <main className={styles.seite}>
      <header>
        <p className={styles.kicker}>{t("Admin")}</p>
        <h1 className={styles.titel}>{t("Accounts and company plans")}</h1>
        <p className={styles.lead}>{t("Unlock company plans by hand, without payment.")}</p>
      </header>
      {fehler && <p className={styles.fehler} role="alert">{fehler}</p>}
      {gesperrt && (
        <form className={styles.karte} onSubmit={entsperren}>
          <p className={styles.hinweis}>{t("Only for admins: sign in with an admin email or enter the developer code.")}</p>
          <div className={styles.zeile}>
            <label className={styles.feld}>{t("Developer code")}
              <input className={styles.eingabe} type="password" inputMode="numeric" autoComplete="off" value={code} onChange={(ev) => setCode(ev.target.value)} />
            </label>
            <button type="submit" className={styles.knopf}>{t("Unlock")}</button>
          </div>
        </form>
      )}
      {daten && (
        <>
          <form className={styles.karte} onSubmit={speichern}>
            <h2 style={{ margin: 0, fontSize: 17 }}>{form.id ? t("Edit company plan") : t("Unlock company plan")}</h2>
            <div className={styles.zeile}>
              <label className={styles.feld}>{t("Company name")}<input className={styles.eingabe} required value={form.name} onChange={(ev) => setForm({ ...form, name: ev.target.value })} /></label>
              <label className={styles.feld} style={{ maxWidth: 120 }}>{t("Seats")}<input className={styles.eingabe} type="number" min={1} value={form.seats} onChange={(ev) => setForm({ ...form, seats: Number(ev.target.value) || 1 })} /></label>
              <label className={styles.feld} style={{ maxWidth: 180 }}>{t("Valid until")}<input className={styles.eingabe} type="date" value={form.expiresAt} onChange={(ev) => setForm({ ...form, expiresAt: ev.target.value })} /></label>
            </div>
            <label className={styles.feld}>{t("Member emails (comma separated)")}
              <input className={styles.eingabe} value={form.members} onChange={(ev) => setForm({ ...form, members: ev.target.value })} placeholder="anna@firma.de, ben@firma.de" />
            </label>
            <div className={styles.knoepfe}>
              <button type="submit" className={styles.knopf}>{form.id ? t("Save") : t("Unlock plan")}</button>
              {form.id && <button type="button" className={styles.knopfZweit} onClick={() => setForm({ id: "", name: "", seats: 5, expiresAt: "", members: "" })}>{t("Cancel")}</button>}
            </div>
          </form>
          <section className={styles.karte}>
            <h2 style={{ margin: 0, fontSize: 17 }}>{t("Company plans")} ({daten.companies.length})</h2>
            <div className={styles.scroll}>
              <table className={styles.tabelle}>
                <thead><tr><th>{t("Company")}</th><th>{t("Seats")}</th><th>{t("Valid until")}</th><th>{t("Members")}</th><th>{t("Source")}</th><th /></tr></thead>
                <tbody>
                  {daten.companies.map((f) => (
                    <tr key={f.id}>
                      <td><strong>{f.name}</strong>{!f.aktiv && <> · <span className={styles.fehler}>{t("expired")}</span></>}</td>
                      <td>{f.members.length}/{f.seats}</td>
                      <td>{datum(f.expiresAt)}</td>
                      <td>{f.members.join(", ") || "–"}</td>
                      <td>{f.quelle === "stripe" ? "Stripe" : t("Manual")}</td>
                      <td style={{ whiteSpace: "nowrap" }}>
                        <button type="button" className={styles.knopfZweit} onClick={() => bearbeiten(f)}>{t("Edit")}</button>{" "}
                        <button type="button" className={styles.knopfZweit} onClick={() => loeschen(f)}>{t("Remove")}</button>
                      </td>
                    </tr>
                  ))}
                  {daten.companies.length === 0 && <tr><td colSpan={6} className={styles.hinweis}>{t("No company plans yet.")}</td></tr>}
                </tbody>
              </table>
            </div>
          </section>
          <section className={styles.karte}>
            <h2 style={{ margin: 0, fontSize: 17 }}>{t("Accounts")} ({daten.users.length})</h2>
            <div className={styles.scroll}>
              <table className={styles.tabelle}>
                <thead><tr><th>{t("Email")}</th><th>{t("Plan")}</th><th>{t("This month")}</th><th>{t("Subscription")}</th></tr></thead>
                <tbody>
                  {daten.users.map((n) => (
                    <tr key={n.email}>
                      <td>{n.email}{n.name ? <span className={styles.hinweis}> · {n.name}</span> : null}</td>
                      <td><span className={planKlasse(n.plan)}>{t(PLAN_LABEL[n.plan] ?? n.plan)}</span></td>
                      <td>{n.used}</td>
                      <td>{n.subscriptionStatus ?? "–"}</td>
                    </tr>
                  ))}
                  {daten.users.length === 0 && <tr><td colSpan={4} className={styles.hinweis}>{t("No accounts yet.")}</td></tr>}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </main>
  );
}

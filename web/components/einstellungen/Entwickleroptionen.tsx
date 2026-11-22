"use client";

import { useCallback, useEffect, useState } from "react";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { KeySettings } from "@/components/schluessel/KeySettings";
import { api, type DevOptionsState, type DevProvider } from "@/lib/api";
import { useEinstellungen } from "@/lib/einstellungen";
import styles from "./einstellungen.module.css";

export const DEV_OPTIONS_FREIGABE = "lv-dev-options-unlocked";

export function istFreigeschaltet(): boolean {
  try { return window.localStorage.getItem(DEV_OPTIONS_FREIGABE) === "1"; } catch { return false; }
}

function merkeFreigabe(an: boolean) {
  try {
    if (an) window.localStorage.setItem(DEV_OPTIONS_FREIGABE, "1");
    else window.localStorage.removeItem(DEV_OPTIONS_FREIGABE);
  } catch { /* storage blocked: the gate stays in memory for this visit */ }
}

const ANBIETER: { value: DevProvider; label: string }[] = [
  { value: "anthropic", label: "Claude-API (Key)" },
  { value: "grokbot", label: "Grok Bot" },
];

function alsAnbieter(name: string | undefined): DevProvider {
  if (name === "grokbot") return name;
  return "anthropic";
}

export function Entwickleroptionen() {
  const { t } = useEinstellungen();
  const [offen, setOffen] = useState(false);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [fehler, setFehler] = useState("");
  const [state, setState] = useState<DevOptionsState | null | "offline">(null);

  const laden = useCallback(() => {
    api.devOptions().then(setState).catch(() => setState("offline"));
  }, []);

  useEffect(() => {
    setOffen(istFreigeschaltet());
  }, []);

  useEffect(() => {
    if (offen) laden();
  }, [offen, laden]);

  const freischalten = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setFehler("");
    try {
      await api.unlockDevOptions(code.trim());
      merkeFreigabe(true);
      setCode("");
      setOffen(true);
    } catch (error) {
      merkeFreigabe(false);
      setFehler(error instanceof Error ? error.message : t("Wrong unlock code."));
    } finally {
      setBusy(false);
    }
  };

  const sperren = () => {
    merkeFreigabe(false);
    setOffen(false);
    setFehler("");
  };

  const waehle = async (provider: DevProvider) => {
    setFehler("");
    try {
      const next = await api.setDevProvider(provider);
      setState(next);
      window.dispatchEvent(new Event("llm-config-changed"));
    } catch (error) {
      setFehler(error instanceof Error ? error.message : t("Request failed."));
      laden();
    }
  };

  const anbieter = state && state !== "offline" ? alsAnbieter(state.provider) : "anthropic";

  return (
    <section className={styles.karte}>
      <h2 className={styles.abschnitt}>{t("Developer options")}</h2>
      {!offen ? (
        <>
          <p className={styles.hinweis}>
            {t("Unlock this section with a code to choose the AI provider and enter a Claude API key. The key is not shown in the header.")}
          </p>
          <form onSubmit={freischalten} className={styles.devForm}>
            <label className={styles.devLabel}>
              {t("Unlock code")}
              <input type="password" value={code} onChange={(e) => setCode(e.target.value)}
                autoComplete="off" spellCheck={false} required className={styles.devInput}
                placeholder={t("Code")} />
            </label>
            <button type="submit" className={styles.knopf} disabled={busy || !code.trim()}>
              {busy ? t("Checking …") : t("Unlock")}
            </button>
          </form>
          {fehler && <p className={styles.devFehler} role="alert">{fehler}</p>}
        </>
      ) : (
        <>
          <div className={styles.devKopf}>
            <p className={styles.hinweis}>{t("AI provider for reviews, evaluation and research. The choice applies until the backend restarts.")}</p>
            <button type="button" className={styles.knopf} onClick={sperren}>{t("Lock")}</button>
          </div>
          {state === "offline" || state === null ? (
            <p className={styles.hinweis}>{t("The backend is not reachable. Start it with python tools/dev.py.")}</p>
          ) : (
            <>
              <fieldset className={styles.gruppe}>
                <legend>{t("Provider")}</legend>
                <SegmentedControl options={ANBIETER} value={anbieter} onChange={waehle} ariaLabel={t("Provider")} />
              </fieldset>
              {anbieter === "anthropic" && (
                <>
                  <p className={styles.hinweis}>{t("Enter the Claude API key here. It is sent to the backend once and never shown again.")}</p>
                  <KeySettings embedded />
                </>
              )}
              {anbieter === "grokbot" && (
                <p className={styles.hinweis}>
                  {t("Grok Bot mode writes each model call as a file and waits for an answer. During analysis the app shows “Wartet auf Grok Bot …”. Queue folder: {dir}. Default wait {n} s.",
                    { dir: state.queue_dir, n: Math.round(state.timeout_s) })}
                </p>
              )}
            </>
          )}
          {fehler && <p className={styles.devFehler} role="alert">{fehler}</p>}
        </>
      )}
    </section>
  );
}

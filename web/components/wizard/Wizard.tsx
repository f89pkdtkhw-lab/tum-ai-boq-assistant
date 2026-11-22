"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useT } from "@/lib/einstellungen";
import type { AnalyseStatus } from "@/lib/api";
import {
  LADE_STUFEN, WIZARD_IDS, WIZARD_SCHRITTE, WIZARD_WEITER,
  effektiverSchritt, istWizardSchritt, ladeStufe, leseSchritt, liveFortschritt, maxSchritt, schrittIndex, wizardAnzeigeSchritt, wizardPfad, wizardSichtbar, wizardUmleitung,
  type WizardSchritt,
} from "@/lib/wizard";
import { setzeEvaluationSchritt } from "@/lib/evaluation-session";
import styles from "./wizard.module.css";

type Status = { hatBericht: boolean; laeuft: boolean };

type Ctx = {
  schritt: WizardSchritt;
  setSchritt: (s: WizardSchritt) => void;
  maxErreicht: WizardSchritt;
  setStatus: (s: Status) => void;
  sichtbar: boolean;
  kannWeiter: boolean;
};

const WizardCtx = createContext<Ctx | null>(null);

export function useWizard(): Ctx {
  const ctx = useContext(WizardCtx);
  if (!ctx) {
    return {
      schritt: "hochladen",
      setSchritt: () => {},
      maxErreicht: "hochladen",
      setStatus: () => {},
      sichtbar: false,
      kannWeiter: false,
    };
  }
  return ctx;
}

export function WizardProvider({ children }: { children: ReactNode }) {
  const pathname = usePathname() || "/";
  const search = useSearchParams();
  const router = useRouter();
  const sichtbar = wizardSichtbar(pathname);
  const seite = leseSchritt(null, pathname);
  const [status, setStatus] = useState<Status>({ hatBericht: false, laeuft: false });

  useEffect(() => {
    try {
      const offen = JSON.parse(window.sessionStorage.getItem("lv-aktuell-v1") ?? "null");
      if (offen?.bericht) setStatus((s) => (s.hatBericht ? s : { ...s, hatBericht: true }));
    } catch { /* unreadable */ }
  }, []);

  const maxErreicht = useMemo(() => {
    const ausStatus = maxSchritt(status);
    return schrittIndex(seite) > schrittIndex(ausStatus) ? seite : ausStatus;
  }, [status, seite]);

  const gewuenscht = leseSchritt(search.get("schritt"), pathname);
  const geklemmt = effektiverSchritt(gewuenscht, status, seite);
  // Keep the requested step while eval/job is being restored, otherwise the start form covers the error/progress.
  const schritt = wizardAnzeigeSchritt(gewuenscht, status, seite, search);

  const setSchritt = useCallback((s: WizardSchritt) => {
    const ziel = effektiverSchritt(s, status, seite);
    router.push(wizardPfad(ziel));
  }, [router, status, seite]);

  const umleitung = wizardUmleitung(gewuenscht, geklemmt, search);
  // Restoring an evaluation from its link: the step is not reachable until the page reports its status.
  const wartet = gewuenscht !== geklemmt && umleitung === null;
  useEffect(() => {
    if (sichtbar && umleitung) router.replace(umleitung);
  }, [sichtbar, umleitung, router]);

  useEffect(() => {
    if (sichtbar && !wartet) setzeEvaluationSchritt(schritt);
  }, [sichtbar, wartet, schritt]);

  const kannWeiter = schritt === "hochladen" ? status.laeuft || status.hatBericht
    : schritt === "pruefen" ? status.hatBericht
    : schritt !== "export";

  const wert = useMemo<Ctx>(() => ({
    schritt, setSchritt, maxErreicht, setStatus, sichtbar, kannWeiter,
  }), [schritt, setSchritt, maxErreicht, sichtbar, kannWeiter]);

  return <WizardCtx.Provider value={wert}>{children}</WizardCtx.Provider>;
}

const HAKEN = (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
    <path d="M5 12l5 5L19 7" />
  </svg>
);

export function WizardLeiste() {
  const { schritt, setSchritt, maxErreicht, sichtbar } = useWizard();
  const t = useT();
  if (!sichtbar) return null;
  const hier = schrittIndex(schritt);
  const max = schrittIndex(maxErreicht);
  const fill = (hier / (WIZARD_IDS.length - 1)) * 100;
  return (
    <nav className={styles.leiste} aria-label={t("Workflow")}>
      <div className={styles.wrap}>
        <div className={styles.line}><div className={styles.fill} style={{ width: `${fill}%` }} /></div>
        <div className={styles.track}>
          {WIZARD_SCHRITTE.map((s, i) => {
            const current = s.id === schritt;
            const done = i < hier;
            const erlaubt = i <= max;
            return (
              <button key={s.id} type="button" className={`${styles.step} ${current ? styles.stepCurrent : ""} ${done ? styles.stepDone : ""}`}
                disabled={!erlaubt} aria-current={current ? "step" : undefined}
                onClick={() => erlaubt && setSchritt(s.id)}>
                <span className={styles.dot}>{done ? HAKEN : i + 1}</span>
                <span className={styles.lbl}>{t(s.label)}</span>
              </button>
            );
          })}
        </div>
      </div>
    </nav>
  );
}

export function WizardFuss() {
  const { schritt, setSchritt, sichtbar, kannWeiter } = useWizard();
  const t = useT();
  const router = useRouter();
  if (!sichtbar) return null;
  const i = schrittIndex(schritt);
  return (
    <footer className={styles.fuss}>
      <button type="button" className={styles.knopfZweit} disabled={i === 0}
        onClick={() => i > 0 && setSchritt(WIZARD_IDS[i - 1])}>{t("Back")}</button>
      <span className={styles.fussHint} />
      <div className={styles.fussPush}>
        {/* Export step: all downloads sit in the toolbar on the page, so the footer only offers Back. */}
        {schritt !== "export" && <button type="button" className={styles.knopf} disabled={!kannWeiter}
          onClick={() => {
            if (!kannWeiter) return;
            const naechster = WIZARD_IDS[i + 1];
            if (naechster === "marge" || naechster === "export") router.push(wizardPfad(naechster));
            else setSchritt(naechster);
          }}>
          {t(WIZARD_WEITER[schritt])}
        </button>}
      </div>
    </footer>
  );
}

const zahl = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 1 });

export function Ladeanzeige({ phase, importFertig, standStatus, dateiname, stand }: {
  phase: "leer" | "laeuft" | "fertig" | "fehler";
  importFertig?: boolean;
  standStatus?: "laeuft" | "fertig" | "fehler" | null;
  dateiname?: string;
  stand?: AnalyseStatus | null;
}) {
  const t = useT();
  const { stufe, aktiv } = ladeStufe({ phase, importFertig, standStatus });
  const jetzt = t(LADE_STUFEN[stufe - 1]);
  const live = (phase === "laeuft" || phase === "fehler") ? liveFortschritt(stand) : null;
  const meldung = (stand?.meldung ?? "").trim();
  const gestoppt = phase === "fehler" || stand?.status === "fehler";
  const balkenWert = live ? live.prozent : (stufe / 4) * 100;
  return (
    <div className={styles.lade} aria-busy={aktiv} aria-live="polite">
      <div className={styles.ladeKopf}>
        <span className={styles.ladeJetzt}>
          {live ? t("Step {n} of {total}", { n: live.schritt, total: live.gesamt }) : jetzt}
        </span>
        <span className={styles.ladeWait}>
          {live ? <span className={styles.prozent}>{live.prozent} %</span>
            : (aktiv ? t("Just a moment …") : (dateiname ?? ""))}
        </span>
      </div>
      <div className={`${styles.balken} ${gestoppt ? styles.balkenGestoppt : ""}`}
        role="progressbar"
        aria-label={live ? t("Analysis progress") : t("Review")}
        aria-valuemin={live ? 0 : 1}
        aria-valuemax={live ? 100 : 4}
        aria-valuenow={live ? live.prozent : stufe}
        aria-valuetext={meldung || jetzt}>
        <span className={`${styles.balkenFuellung} ${aktiv && !live && stufe < 4 ? styles.puls : ""}`}
          style={{ width: `${balkenWert}%` }} />
      </div>
      {live && meldung ? <p className={styles.fortschrittText}>{meldung}</p> : null}
      <ol className={styles.stufen}>
        {LADE_STUFEN.map((name, i) => {
          const n = i + 1;
          const erledigt = n < stufe || phase === "fertig";
          const an = n === stufe && phase !== "fertig";
          return (
            <li key={name} className={erledigt ? styles.erledigt : an ? styles.an : undefined}>
              <span className={styles.st}>{erledigt ? "✓" : n}</span>
              <span>{t(name)}</span>
            </li>
          );
        })}
      </ol>
      {live && stand && stand.fertige_schritte.length > 0 && (
        <ol className={styles.fertigListe} aria-label={t("Finished steps")}>
          {stand.fertige_schritte.map((s) => (
            <li key={s.schritt}>
              <span className={styles.haken} aria-hidden="true">✓</span>
              <span>{s.meldung}</span>
              <small>{zahl.format(Math.round(s.sekunden * 10) / 10)} s</small>
            </li>
          ))}
        </ol>
      )}
      {stand && stand.fehler.length > 0 && (
        <ul className={styles.fortschrittFehler} role="note">
          {stand.fehler.map((f) => <li key={f}>{f}</li>)}
        </ul>
      )}
    </div>
  );
}

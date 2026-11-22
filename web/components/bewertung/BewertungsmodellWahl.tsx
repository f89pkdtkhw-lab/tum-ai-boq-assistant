"use client";

import { useEffect, useId, useState } from "react";
import { Icon } from "@/components/icon/Icon";
import { MODELL_INFO, MODELLE, type Bewertungsmodell } from "@/lib/bewertungsmodell";
import { useEinstellungen } from "@/lib/einstellungen";
import { useBewertungsmodell } from "@/lib/useBewertungsmodell";
import styles from "./BewertungsmodellWahl.module.css";

const LABEL: Record<Bewertungsmodell, string> = {
  streng: "Strict",
  gestaffelt: "Graduated",
  anteil: "Share",
  fehler_klaerung: "Errors/hints",
  ausgewogen: "Balanced",
};

/** iOS-style 5-stop segmented control plus an info sheet for each scoring model. */
export function BewertungsmodellWahl({ ariaLabel }: { ariaLabel?: string } = {}) {
  const { t } = useEinstellungen();
  const [modell, setze] = useBewertungsmodell();
  const [info, setInfo] = useState<Bewertungsmodell | null>(null);
  const titelId = useId();

  useEffect(() => {
    if (!info) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setInfo(null); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [info]);

  return (
    <div className={styles.feld}>
      <p className={styles.kursue}>{t("Scoring model")}</p>
      <div className={styles.bahn} role="tablist" aria-label={ariaLabel ?? t("Scoring model")}>
        {MODELLE.map((id) => (
          <div key={id} className={styles.zelle} data-aktiv={modell === id ? "true" : "false"}>
            <button type="button" role="tab" className={styles.knopf} aria-selected={modell === id}
              onClick={() => setze(id)}>
              {t(LABEL[id])}
            </button>
            <button type="button" className={styles.info}
              aria-label={t("How {name} is calculated", { name: t(MODELL_INFO[id].name) })}
              onClick={() => setInfo(id)}>
              <Icon name="help" size={12} />
            </button>
          </div>
        ))}
      </div>
      {info && (
        <div className={styles.bg} role="dialog" aria-modal="true" aria-labelledby={titelId}
          onClick={(e) => { if (e.target === e.currentTarget) setInfo(null); }}>
          <div className={styles.blatt}>
            <h2 id={titelId} className={styles.titel}>{t(MODELL_INFO[info].name)}</h2>
            <p className={styles.kurz}>{t(MODELL_INFO[info].kurz)}</p>
            <p>{t(MODELL_INFO[info].text)}</p>
            <p className={styles.beispiel}>{t(MODELL_INFO[info].beispiel)}</p>
            <button type="button" className={styles.schliessen} onClick={() => setInfo(null)}>{t("Close")}</button>
          </div>
        </div>
      )}
    </div>
  );
}

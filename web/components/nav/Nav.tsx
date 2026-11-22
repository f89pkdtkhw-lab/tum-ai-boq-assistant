"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import styles from "./nav.module.css";
import { Logo } from "../logo/Logo";
import { Icon, type IconName } from "../icon/Icon";
import { KontoChip } from "../saas/KontoChip";
import { useEinstellungen, nachts } from "@/lib/einstellungen";
import { evaluationPfad, istNeuerAuftrag, type EvaluationEintrag } from "@/lib/evaluation-session";
import { useEvaluationSitzung } from "@/lib/useEvaluationSitzung";

type Eintrag = { href: string; label: string; icon: IconName };
// Menu as sketched by the team: start an evaluation, submit files, history, settings, theme. Advanced pages sit under "More".
// Submit is one page (price list and final bill), so it has one entry.
const HAUPT: Eintrag[] = [
  { href: "/?neu=1", label: "New evaluation", icon: "upload" },
  // t243: price database, history, stored documents and submissions live together on one page.
  { href: "/vault", label: "Vault", icon: "folder" },
];
const WEITERE: Eintrag[] = [
  { href: "/wettbewerb", label: "Competitors", icon: "chart" },
  { href: "/marge", label: "Margin", icon: "gauge" },
  { href: "/schritte", label: "Step reports", icon: "steps" },
  { href: "/export", label: "Export", icon: "download" },
  { href: "/anleitung", label: "Tutorial", icon: "help" },
  { href: "/tarife", label: "Plans", icon: "sparkles" },
  { href: "/start", label: "About LV Scout", icon: "lightbulb" },
];

function statusText(e: EvaluationEintrag, t: (s: string) => string): string {
  if (e.status === "laeuft") return e.prozent != null ? `${e.prozent} %` : t("Running");
  if (e.status === "fehler") return t("Failed");
  return t("Done");
}

/** Sun/moon switch (sketch: "Theme ☀ ☾"); a third press returns to automatic day/night. */
function ThemaSchalter() {
  const { e, setze, t } = useEinstellungen();
  const dunkel = e.thema === "dark" || (e.thema === "auto" && nachts(new Date().getHours()));
  return (
    <button type="button" className={styles.thema} aria-label={t("Theme")} title={`${t("Theme")}: ${t(e.thema === "auto" ? "Auto" : e.thema === "dark" ? "Dark" : "Light")}`}
      onClick={() => setze({ thema: e.thema === "auto" ? (dunkel ? "light" : "dark") : e.thema === "dark" ? "light" : "auto" })}>
      <span className={!dunkel ? styles.an : undefined}>☀</span><span className={dunkel ? styles.an : undefined}>☾</span>
      {e.thema === "auto" && <small>A</small>}
    </button>
  );
}

export function Nav() {
  const pathname = usePathname();
  const search = useSearchParams();
  const { t } = useEinstellungen();
  const { aktuell, liste } = useEvaluationSitzung();
  const neu = istNeuerAuftrag(search);
  const [offen, setOffen] = useState(false);
  useEffect(() => { setOffen(false); }, [pathname, search]);
  useEffect(() => {
    const zu = (ev: KeyboardEvent) => { if (ev.key === "Escape") setOffen(false); };
    document.addEventListener("keydown", zu);
    return () => document.removeEventListener("keydown", zu);
  }, []);
  const aktiv = (href: string) => {
    if (href.startsWith("/?neu=")) return pathname === "/" && neu;
    if (href === "/") return pathname === "/" && !neu;
    return pathname.startsWith(href.split("#")[0]);
  };
  const listeItems = (eintraege: Eintrag[]) => (
    <ul className={styles.liste}>
      {eintraege.map(({ href, label, icon }) => (
        <li key={href}>
          <Link href={href} className={styles.link} aria-current={aktiv(href) && !href.includes("#") ? "page" : undefined} onClick={() => setOffen(false)}>
            <Icon name={icon} />{t(label)}
          </Link>
        </li>
      ))}
    </ul>
  );
  const weitere = liste.filter((e) => e.id !== aktuell?.id);
  const zurueck = aktuell ?? liste[0] ?? null;

  return (
    <>
      <header className={styles.leiste}>
        <button type="button" className={styles.burger} aria-label={t("Menu")} aria-expanded={offen} onClick={() => setOffen(!offen)}>
          <span /><span /><span />
        </button>
        <Link href="/" className={styles.marke}><Logo size={30} />LV Scout</Link>
        <span className={styles.platz} />
        {zurueck && (
          <Link href={evaluationPfad(zurueck)} className={`${styles.evalChip} ${zurueck.status === "laeuft" ? styles.evalChipLaufend : ""}`}
            title={t("Back to the evaluation")} onClick={() => setOffen(false)}>
            <Icon name={zurueck.status === "laeuft" ? "steps" : "report"} />
            <span className={styles.evalChipText}>
              {t(zurueck.status === "laeuft" ? "Running evaluation" : "Last evaluation")}
              {zurueck.status === "laeuft" && zurueck.prozent != null ? ` · ${zurueck.prozent} %` : ""}
            </span>
          </Link>
        )}
        <KontoChip />
        <ThemaSchalter />
      </header>
      {offen && <div className={styles.schleier} onClick={() => setOffen(false)} aria-hidden="true" />}
      <nav className={`${styles.schublade} ${offen ? styles.offen : ""}`} aria-label={t("Main")} aria-hidden={!offen}>
        <div className={styles.kopf}><Logo size={34} /><strong>LV Scout</strong></div>
        {listeItems(HAUPT)}
        {liste.length > 0 && (
          <div className={styles.evalBlock}>
            {aktuell && (
              <Link href={evaluationPfad(aktuell)} className={`${styles.evalKarte} ${aktuell.status === "laeuft" ? styles.evalLaufend : ""}`}
                aria-current={pathname === "/" && !neu ? "page" : undefined} onClick={() => setOffen(false)}>
                <Icon name={aktuell.status === "laeuft" ? "steps" : "report"} />
                <span className={styles.evalText}>
                  <strong>{t(aktuell.status === "laeuft" ? "Running evaluation" : "Last evaluation")}</strong>
                  <small>{aktuell.titel} · {statusText(aktuell, t)}</small>
                </span>
              </Link>
            )}
            {weitere.length > 0 && (
              <>
                <p className={styles.gruppe}>{t("Recent evaluations")}</p>
                <ul className={styles.liste}>
                  {weitere.slice(0, 5).map((e) => (
                    <li key={e.id}>
                      <Link href={evaluationPfad(e)} className={styles.link} onClick={() => setOffen(false)}>
                        <Icon name="history" />
                        <span className={styles.evalName}>{e.titel}</span>
                        <small className={styles.evalMeta}>{statusText(e, t)}</small>
                      </Link>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </div>
        )}
        <p className={styles.gruppe}>{t("More")}</p>
        {listeItems(WEITERE)}
        <div className={styles.fuss}>
          {listeItems([{ href: "/einstellungen", label: "Settings", icon: "settings" }])}
          <div className={styles.themaZeile}><span>{t("Theme")}</span><ThemaSchalter /></div>
        </div>
      </nav>
    </>
  );
}

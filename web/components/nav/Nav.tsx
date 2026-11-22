"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import styles from "./nav.module.css";
import { Logo } from "../logo/Logo";
import { Icon, type IconName } from "../icon/Icon";
import { KontoChip } from "../saas/KontoChip";
import { useEinstellungen, nachts } from "@/lib/einstellungen";

type Eintrag = { href: string; label: string; icon: IconName };
// Menu as sketched by the team: start an evaluation, submit files, history, settings, theme. Advanced pages sit under "More".
// Submit is one page (price list and final bill), so it has one entry.
const HAUPT: Eintrag[] = [
  { href: "/", label: "New evaluation", icon: "upload" },
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

const MOBIL = "(max-width: 860px)";

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
  const { t } = useEinstellungen();
  const [offen, setOffen] = useState(false);
  const [mobil, setMobil] = useState(false);
  useEffect(() => { setOffen(false); }, [pathname]);
  useEffect(() => {
    const mq = window.matchMedia(MOBIL);
    const sync = () => setMobil(mq.matches);
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);
  useEffect(() => {
    const zu = (ev: KeyboardEvent) => { if (ev.key === "Escape") setOffen(false); };
    document.addEventListener("keydown", zu);
    return () => document.removeEventListener("keydown", zu);
  }, []);
  const aktiv = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href.split("#")[0]));
  const liste = (eintraege: Eintrag[]) => (
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

  return (
    <>
      <nav className={`app-sidebar ${styles.sidebar} ${offen ? styles.offen : ""}`} aria-label={t("Main")} aria-hidden={mobil && !offen}>
        <Link href="/" className={styles.marke} onClick={() => setOffen(false)}><Logo size={32} />LV Scout</Link>
        {liste(HAUPT)}
        <p className={styles.gruppe}>{t("More")}</p>
        {liste(WEITERE)}
        <div className={styles.fuss}>
          {liste([{ href: "/einstellungen", label: "Settings", icon: "settings" }])}
        </div>
      </nav>
      {offen && <div className={styles.schleier} onClick={() => setOffen(false)} aria-hidden="true" />}
      <header className={`app-topbar ${styles.topbar}`}>
        <button type="button" className={styles.burger} aria-label={t("Menu")} aria-expanded={offen} onClick={() => setOffen(!offen)}>
          <span /><span /><span />
        </button>
        <Link href="/" className={styles.markeMobil}><Logo size={32} />LV Scout</Link>
        <span className={styles.platz} />
        <KontoChip />
        <ThemaSchalter />
      </header>
    </>
  );
}

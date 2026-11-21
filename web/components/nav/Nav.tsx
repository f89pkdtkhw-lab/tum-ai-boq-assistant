"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import styles from "./nav.module.css";
import { Logo } from "../logo/Logo";
import { Icon, type IconName } from "../icon/Icon";
import { useEinstellungen, nachts } from "@/lib/einstellungen";
import { KeySettings } from "@/components/schluessel/KeySettings";

type Eintrag = { href: string; label: string; icon: IconName };
// Menu as sketched by the team: start an evaluation, submit files, history, settings, theme. Advanced pages sit under "More".
// Submit is one page (price list and final bill), so it has one entry.
const HAUPT: Eintrag[] = [
  { href: "/", label: "New evaluation", icon: "upload" },
  { href: "/einreichen", label: "Submit", icon: "price" },
];
const WEITERE: Eintrag[] = [
  { href: "/history", label: "History", icon: "history" },
  { href: "/wettbewerb", label: "Competitors", icon: "chart" },
  { href: "/preise", label: "Price database", icon: "euro" },
  { href: "/schritte", label: "Step reports", icon: "steps" },
  { href: "/export", label: "Export", icon: "download" },
  { href: "/anleitung", label: "Tutorial", icon: "help" },
];

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
  useEffect(() => { setOffen(false); }, [pathname]);
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
      <header className={styles.leiste}>
        <button type="button" className={styles.burger} aria-label={t("Menu")} aria-expanded={offen} onClick={() => setOffen(!offen)}>
          <span /><span /><span />
        </button>
        <Link href="/" className={styles.marke}><Logo size={30} />BoQ Review</Link>
        <span className={styles.platz} />
        <KeySettings compact />
        <ThemaSchalter />
      </header>
      {offen && <div className={styles.schleier} onClick={() => setOffen(false)} aria-hidden="true" />}
      <nav className={`${styles.schublade} ${offen ? styles.offen : ""}`} aria-label={t("Main")} aria-hidden={!offen}>
        <div className={styles.kopf}><Logo size={34} /><strong>BoQ Review</strong></div>
        {liste(HAUPT)}
        <p className={styles.gruppe}>{t("More")}</p>
        {liste(WEITERE)}
        <div className={styles.fuss}>
          {liste([{ href: "/einstellungen", label: "Settings", icon: "settings" }])}
          <div className={styles.themaZeile}><span>{t("Theme")}</span><ThemaSchalter /></div>
        </div>
      </nav>
    </>
  );
}

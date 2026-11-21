"use client";

import type { Position } from "@/lib/api";
import { useEinstellungen } from "@/lib/einstellungen";
import { formatVon, fundstelleTeile, pdfLink, text } from "@/lib/fundstelle";
import { Icon } from "../icon/Icon";
import styles from "./fundstelle.module.css";

/**
 * #170: the location note of a finding's item in the original (file · page/line or sheet/row · OZ), with a link that
 * opens the uploaded PDF at the item's page and a button that scrolls to and highlights the OZ in the BoQ view.
 */
export function Fundstelle({ datei, oz, position, originalUrl, onImLv }: {
  datei: string; oz: string; position: Position | undefined; originalUrl?: string | null; onImLv?: () => void;
}) {
  const { e } = useEinstellungen();
  const s = e.sprache;
  const link = pdfLink(originalUrl, position);
  const seite = position?.quelle?.seite;
  return (
    <p className={styles.fundstelle}>
      <span className={styles.ort} title={position?.quelle?.pfad}>
        <Icon name="folder" size={14} /> <b>{text(s, "Source")}:</b> {fundstelleTeile(datei, oz, position, s).join(" · ")}
      </span>
      {link && seite ? (
        <a className={styles.knopfLeise} href={link} target="_blank" rel="noopener noreferrer">{text(s, "Open PDF at page {n}", { n: seite })} ↗</a>
      ) : seite && formatVon(datei) === "pdf" ? (
        <small className={styles.hinweis}>{text(s, "The original file is only kept in this browser tab right after the upload; page and line still name the place.")}</small>
      ) : null}
      {onImLv && position && <button type="button" className={styles.knopfLeise} onClick={onImLv}>{text(s, "Show in BoQ")} ›</button>}
    </p>
  );
}

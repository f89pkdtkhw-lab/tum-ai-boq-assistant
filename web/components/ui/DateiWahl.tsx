"use client";

import type { ReactNode } from "react";
import { Icon } from "../icon/Icon";
import styles from "./DateiWahl.module.css";

/** Hidden native file input behind a Stripe/iOS-style picker card. */
export function DateiWahl({
  id, label, hint, accept, file, disabled, invalid, describedBy, chooseLabel = "Choose file", onChange,
}: {
  id?: string;
  label: ReactNode;
  hint?: ReactNode;
  accept?: string;
  file: File | null;
  disabled?: boolean;
  invalid?: boolean;
  describedBy?: string;
  chooseLabel?: string;
  onChange: (datei: File | null) => void;
}) {
  return (
    <label className={`${styles.wahl} ${file ? styles.gewaehlt : ""} ${invalid ? styles.fehler : ""} ${disabled ? styles.gesperrt : ""}`}>
      <input
        id={id}
        type="file"
        accept={accept}
        disabled={disabled}
        className={styles.eingabe}
        aria-invalid={invalid || undefined}
        aria-describedby={describedBy}
        onChange={(ev) => onChange(ev.target.files?.[0] ?? null)}
      />
      <span className={styles.icon} aria-hidden="true">
        <Icon name={file ? "check" : "upload"} size={18} />
      </span>
      <span className={styles.text}>
        <span className={styles.label}>{label}</span>
        <span className={styles.name}>{file ? file.name : chooseLabel}</span>
        {hint && <span className={styles.hint}>{hint}</span>}
      </span>
    </label>
  );
}

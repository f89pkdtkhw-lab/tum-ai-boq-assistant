"use client";

import styles from "./IosToggle.module.css";

export function IosToggle({ checked, onChange, label, hint, disabled, id }: {
  checked: boolean;
  onChange: (wert: boolean) => void;
  label: React.ReactNode;
  hint?: React.ReactNode;
  disabled?: boolean;
  id?: string;
}) {
  return (
    <label className={styles.zeile}>
      <span className={styles.lbl}>
        <b>{label}</b>
        {hint != null && hint !== false && <small>{hint}</small>}
      </span>
      <span className={styles.sw}>
        <input id={id} type="checkbox" checked={checked} disabled={disabled}
          onChange={(e) => onChange(e.target.checked)} />
        <i className={styles.bahn} aria-hidden="true" />
      </span>
    </label>
  );
}

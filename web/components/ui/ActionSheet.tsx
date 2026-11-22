"use client";

import { useEffect, useRef } from "react";
import styles from "./ActionSheet.module.css";

export type ActionSheetAction = { label: string; onClick: () => void; destructive?: boolean };

export function ActionSheet({ open, onClose, title, actions, cancelLabel }: {
  open: boolean;
  onClose: () => void;
  title?: string;
  actions: ActionSheetAction[];
  cancelLabel: string;
}) {
  const bg = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div ref={bg} className={styles.bg} role="dialog" aria-modal="true" aria-label={title}
      onClick={(e) => { if (e.target === bg.current) onClose(); }}>
      <div className={styles.blatt}>
        <div className={styles.gruppe}>
          {actions.map((a) => (
            <button key={a.label} type="button" className={a.destructive ? styles.destr : undefined}
              onClick={() => { onClose(); a.onClick(); }}>
              {a.label}
            </button>
          ))}
        </div>
        <button type="button" className={styles.abbrechen} onClick={onClose}>{cancelLabel}</button>
      </div>
    </div>
  );
}

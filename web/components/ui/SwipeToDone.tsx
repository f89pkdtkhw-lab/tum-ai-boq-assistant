"use client";

import { useRef, useState } from "react";
import styles from "./SwipeToDone.module.css";

const WEITE = 88;

export function SwipeToDone({ done, onToggle, doneLabel, resetLabel, children, ariaLabel, frontClassName }: {
  done: boolean;
  onToggle: () => void;
  doneLabel: string;
  resetLabel: string;
  children: React.ReactNode;
  ariaLabel?: string;
  frontClassName?: string;
}) {
  const [offset, setOffset] = useState(0);
  const drag = useRef<{ x: number; aktiv: boolean } | null>(null);

  function ende() {
    if (!drag.current?.aktiv) { drag.current = null; return; }
    setOffset((o) => (o < -WEITE / 2 ? -WEITE : 0));
    drag.current = null;
  }

  function klickKreis(e: React.MouseEvent<HTMLButtonElement>) {
    e.stopPropagation();
    onToggle();
  }

  return (
    <div className={styles.wrap}
      onPointerDown={(e) => {
        if ((e.target as HTMLElement).closest("button, a, select, input, textarea, label")) return;
        drag.current = { x: e.clientX, aktiv: true };
        (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
      }}
      onPointerMove={(e) => {
        if (!drag.current?.aktiv) return;
        const dx = Math.min(0, e.clientX - drag.current.x);
        setOffset(Math.max(-WEITE, dx));
      }}
      onPointerUp={ende}
      onPointerCancel={ende}>
      <div className={styles.aktionen}>
        <button type="button" className={done ? styles.undo : undefined} onClick={(e) => { e.stopPropagation(); onToggle(); }}>
          {done ? resetLabel : doneLabel}
        </button>
      </div>
      <div className={`${styles.front} ${done ? styles.done : ""} ${frontClassName ?? ""}`.trim()} style={{ transform: offset ? `translateX(${offset}px)` : undefined }}>
        <button type="button" className={styles.chk} aria-pressed={done}
          aria-label={ariaLabel ?? (done ? resetLabel : doneLabel)} onClick={klickKreis}>
          <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M2 6.2l2.6 2.6L10 3.2" />
          </svg>
        </button>
        <div className={styles.content}>{children}</div>
      </div>
    </div>
  );
}

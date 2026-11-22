"use client";

import { useLayoutEffect, useRef, useState } from "react";
import styles from "./SegmentedControl.module.css";

export function SegmentedControl<T extends string>({ options, value, onChange, ariaLabel }: {
  options: { value: T; label: React.ReactNode }[];
  value: T;
  onChange: (wert: T) => void;
  ariaLabel?: string;
}) {
  const seg = useRef<HTMLDivElement>(null);
  const [pill, setPill] = useState({ left: 2, width: 0 });

  useLayoutEffect(() => {
    const wurzel = seg.current;
    if (!wurzel) return;
    const legen = () => {
      const aktiv = wurzel.querySelector<HTMLElement>("[data-aktiv='true']");
      if (!aktiv) return;
      const sr = wurzel.getBoundingClientRect();
      const br = aktiv.getBoundingClientRect();
      setPill({ left: br.left - sr.left, width: br.width });
    };
    legen();
    const ro = new ResizeObserver(legen);
    ro.observe(wurzel);
    return () => ro.disconnect();
  }, [value, options.map((o) => o.value).join('\0')]); // values only; avoid looping on a new options array each render

  return (
    <div ref={seg} className={styles.seg} role="tablist" aria-label={ariaLabel}>
      <span className={styles.pill} style={{ left: pill.left, width: pill.width }} aria-hidden="true" />
      {options.map((o) => (
        <button key={o.value} type="button" role="tab" className={styles.knopf}
          aria-selected={value === o.value} data-aktiv={value === o.value ? "true" : "false"}
          onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

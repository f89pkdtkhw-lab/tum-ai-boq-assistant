"use client";

import { sliderFarbe } from "@/lib/schwelle";
import styles from "./IosSlider.module.css";

export function IosSlider({ value, min = 0, max, step = 1, onChange, labels, valueLabel, hint, ariaLabel }: {
  value: number;
  min?: number;
  max: number;
  step?: number;
  onChange: (wert: number) => void;
  labels?: string[];
  valueLabel?: string;
  hint?: React.ReactNode;
  ariaLabel?: string;
}) {
  const spanne = max - min || 1;
  const t = (value - min) / spanne;
  const farbe = sliderFarbe(t);
  const pct = `${Math.min(100, Math.max(0, t * 100))}%`;
  const setzen = (roh: number) => {
    const gerundet = Math.round(roh / step) * step;
    onChange(Math.min(max, Math.max(min, gerundet)));
  };

  return (
    <div className={styles.block}>
      <div className={styles.zeile}>
        <div className={styles.stepper}>
          <button type="button" aria-label="−" disabled={value <= min} onClick={() => setzen(value - step)}>−</button>
          <span className={styles.stufe}>{valueLabel ?? value}</span>
          <button type="button" aria-label="+" disabled={value >= max} onClick={() => setzen(value + step)}>+</button>
        </div>
        <div className={styles.live}>
          <div className={styles.wert} style={{ color: farbe }}>{valueLabel ?? value}</div>
          {hint != null && <div className={styles.sub}>{hint}</div>}
        </div>
      </div>
      <div className={styles.trackWrap}>
        <div className={styles.track}>
          <div className={styles.fill} style={{ width: pct, background: farbe }} />
          <div className={styles.knob} style={{ left: pct }} />
          <input className={styles.range} type="range" min={min} max={max} step={step} value={value}
            aria-label={ariaLabel} aria-valuetext={typeof valueLabel === "string" ? valueLabel : undefined}
            onChange={(e) => setzen(Number(e.target.value))} />
        </div>
      </div>
      {labels && labels.length > 0 && (
        <div className={styles.ends}>
          {labels.map((l) => <span key={l}>{l}</span>)}
        </div>
      )}
    </div>
  );
}

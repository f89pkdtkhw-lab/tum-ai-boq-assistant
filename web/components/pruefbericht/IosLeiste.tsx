"use client";

import type { Finding } from "@/lib/api";
import { SCHWELLE_STUFEN } from "@/lib/schwelle";
import { useT } from "@/lib/einstellungen";
import { IosSlider } from "@/components/ui/IosSlider";
import { IosToggle } from "@/components/ui/IosToggle";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import styles from "./IosLeiste.module.css";

type Schwere = Finding["schwere"];
type Segment = "alle" | "hoch" | "mittel" | "niedrig";

const SCHWERE_NAME: Record<Schwere, string> = {
  kritisch: "Critical", hoch: "High", mittel: "Medium", niedrig: "Low",
};

export function IosLeiste({ nurKritisch, onNurKritisch, minSchwere, onMinSchwere, schwere, onSchwere }: {
  nurKritisch: boolean;
  onNurKritisch: (an: boolean) => void;
  minSchwere: Schwere;
  onMinSchwere: (s: Schwere) => void;
  schwere: Schwere | null;
  onSchwere: (s: Schwere | null) => void;
}) {
  const t = useT();
  const index = Math.max(0, SCHWELLE_STUFEN.indexOf(minSchwere));
  const segment: Segment = schwere === "hoch" || schwere === "mittel" || schwere === "niedrig" ? schwere : "alle";

  return (
    <div className={styles.leiste}>
      <div className={styles.karte}>
        <h3 className={styles.titel}>{t("View")}</h3>
        <IosToggle
          label={t("Only critical findings")}
          hint={t("Critical and high only")}
          checked={nurKritisch}
          onChange={onNurKritisch}
        />
        <div className={styles.segZeile}>
          <span className={styles.segLabel}>{t("Severity")}</span>
          <SegmentedControl
            ariaLabel={t("Severity")}
            value={segment}
            onChange={(v) => onSchwere(v === "alle" ? null : v)}
            options={[
              { value: "alle", label: t("All") },
              { value: "hoch", label: t("High") },
              { value: "mittel", label: t("Medium") },
              { value: "niedrig", label: t("Low") },
            ]}
          />
        </div>
      </div>
      <div className={styles.karte}>
        <h3 className={styles.titel}>{t("Risk threshold")}</h3>
        <IosSlider
          min={0}
          max={SCHWELLE_STUFEN.length - 1}
          value={index}
          valueLabel={t(SCHWERE_NAME[minSchwere])}
          hint={t("Show from this severity")}
          ariaLabel={t("Risk threshold")}
          labels={SCHWELLE_STUFEN.map((s) => t(SCHWERE_NAME[s]))}
          onChange={(i) => onMinSchwere(SCHWELLE_STUFEN[i] ?? "niedrig")}
        />
      </div>
    </div>
  );
}

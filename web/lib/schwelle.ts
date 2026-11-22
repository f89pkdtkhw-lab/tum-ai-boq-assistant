// Severity threshold and slider colour for the iOS risk control on the review report.
import type { Finding } from "./api";

export const SCHWERE_RANG: Record<Finding["schwere"], number> = {
  kritisch: 0, hoch: 1, mittel: 2, niedrig: 3,
};

/** Slider stops, left (lenient / green) to right (strict / red). */
export const SCHWELLE_STUFEN: Finding["schwere"][] = ["niedrig", "mittel", "hoch", "kritisch"];

/** True when the finding is at least as severe as the threshold (critical is most severe). */
export function liegtUeberSchwelle(schwere: Finding["schwere"], schwelle: Finding["schwere"]): boolean {
  return SCHWERE_RANG[schwere] <= SCHWERE_RANG[schwelle];
}

/** Green → yellow → orange → red, t in [0, 1]. */
export function sliderFarbe(t: number): string {
  const stops: [number, number, number][] = [[52, 199, 89], [255, 204, 0], [255, 149, 0], [255, 59, 48]];
  const x = Math.min(1, Math.max(0, t)) * (stops.length - 1);
  const i = Math.min(stops.length - 2, Math.floor(x));
  const f = x - i;
  const rgb = stops[i].map((v, k) => Math.round(v + (stops[i + 1][k] - v) * f));
  return `rgb(${rgb.join(", ")})`;
}

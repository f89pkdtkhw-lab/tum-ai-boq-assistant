/**
 * Donut chart: coloured arcs in order, a short value in the hole and a caption.
 * The hole is ~76 units wide, so the value shrinks with its length and the caption goes below the ring
 * when it would not fit inside – nothing overlaps the arcs.
 * `plastisch`: a gently tilted, extruded ring (slight 3D) – the arcs are squashed a little vertically and stacked
 * in a darker shade below to form the side wall; the text stays flat so it reads normally.
 */
export function Ring({ teile, mitte, unter, farbe, beschriftung, max = 200, plastisch = false }: {
  teile: { wert: number; farbe: string }[]; mitte: string; unter?: string; farbe?: string; beschriftung: string; max?: number; plastisch?: boolean;
}) {
  const r = 52, umfang = 2 * Math.PI * r;
  const summe = teile.reduce((s, t) => s + t.wert, 0);
  const groesse = mitte.length <= 3 ? 30 : mitte.length === 4 ? 24 : mitte.length === 5 ? 20 : 16;
  const innen = !!unter && unter.length <= 6;
  // One layer of arcs; `dunkel` darkens it for the side wall.
  const bogen = (dy: number, dunkel: boolean) => {
    let start = 0;
    const seite = (f: string) => (dunkel ? `color-mix(in srgb, ${f} 68%, #000)` : f);
    return (
      <g key={dy} transform={dy ? `translate(0 ${dy})` : undefined}>
        <circle cx="70" cy="70" r={r} fill="none" stroke={dunkel ? "var(--fill-strong)" : "var(--fill)"} strokeWidth="16" />
        {summe > 0 && teile.map((t, i) => {
          const laenge = (t.wert / summe) * umfang;
          const el = t.wert > 0 ? (
            <circle key={i} cx="70" cy="70" r={r} fill="none" stroke={seite(t.farbe)} strokeWidth="16"
              strokeDasharray={`${Math.max(0, laenge - (laenge > 3 ? 2 : 0))} ${umfang}`} strokeDashoffset={-start} transform="rotate(-90 70 70)" />
          ) : null;
          start += laenge;
          return el;
        })}
      </g>
    );
  };
  const TIEFE = 7; // side wall height in viewBox units
  return (
    <figure style={{ margin: 0, display: "grid", justifyItems: "center", gap: 4, width: "100%", maxWidth: max }}>
      <svg viewBox={plastisch ? "0 4 140 140" : "0 0 140 140"} style={{ width: "100%", height: "auto" }} role="img" aria-label={beschriftung}>
        {plastisch ? (
          <>
            {/* Tilt: squash about the centre (0.86 ≈ 30°, less than a phone-widget look), then stack the side wall. */}
            <g transform="translate(0 70) scale(1 .86) translate(0 -70)">
              {Array.from({ length: TIEFE }, (_, i) => bogen(TIEFE - i, true))}
              {bogen(0, false)}
            </g>
          </>
        ) : bogen(0, false)}
        <text x="70" y={innen ? 69 : 70} textAnchor="middle" dominantBaseline={innen ? "auto" : "central"}
          style={{ fontSize: groesse, fontWeight: 600, letterSpacing: "-.02em" }} fill={farbe ?? "var(--ink)"}>{mitte}</text>
        {innen && <text x="70" y="94" textAnchor="middle" style={{ fontSize: 11 }} fill="var(--muted)">{unter}</text>}
      </svg>
      {unter && !innen && <figcaption style={{ fontSize: 12.5, color: "var(--muted)", textAlign: "center" }}>{unter}</figcaption>}
    </figure>
  );
}

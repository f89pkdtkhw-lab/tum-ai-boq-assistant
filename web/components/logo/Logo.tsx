/* eslint-disable @next/next/no-img-element */
/** App logo (public/logo.svg, the team's hammer-on-concrete mark). Transparent artwork on a tile that follows the theme. */
export function Logo({ size = 28 }: { size?: number }) {
  return (
    <span style={{ display: "inline-grid", placeItems: "center", width: size, height: size, borderRadius: 6, background: "var(--logo-tile)" }}>
      <img src="/logo.svg" alt="" width={size} height={size} />
    </span>
  );
}

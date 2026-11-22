/* eslint-disable @next/next/no-img-element */
/** App mark: cropped crane-with-magnifier from the LV Scout lockup. Wordmark is set in the nav as text. */
export function Logo({ size = 28 }: { size?: number }) {
  return (
    <span style={{ display: "inline-grid", placeItems: "center", width: size, height: size, borderRadius: 6, background: "var(--logo-tile)" }}>
      <img src="/logo-mark.png" alt="" width={size} height={size} />
    </span>
  );
}

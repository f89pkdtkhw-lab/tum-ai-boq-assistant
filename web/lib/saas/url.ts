/** Public base URL for Stripe redirects: APP_URL (or AUTH_URL) when set, otherwise the request origin. */
export function basisUrl(req: Request): string {
  const env = process.env.APP_URL || process.env.AUTH_URL;
  if (env) return env.replace(/\/(api\/auth)?\/?$/, "");
  const h = req.headers;
  const host = h.get("x-forwarded-host") || h.get("host");
  const proto = h.get("x-forwarded-proto") || "http";
  return host ? `${proto}://${host}` : new URL(req.url).origin;
}

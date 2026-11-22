import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

// Login/subscription settings (docs/abo.md) may sit in the repository root .env.local next to the model keys.
// Only these names are taken from there, never overriding web/.env.local or the shell; nothing is logged.
const SAAS_ENV = /^(AUTH_[A-Z_]+|SMTP_HOST|SMTP_PORT|SMTP_USER|SMTP_PASS|MAIL_FROM|STRIPE_SECRET_KEY|STRIPE_WEBHOOK_SECRET|ADMIN_EMAILS|APP_URL|LV_SCOUT_DATA_DIR|DEV_OPTIONS_CODE)$/;
try {
  const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", ".env.local");
  for (const zeile of readFileSync(root, "utf8").split(/\r?\n/)) {
    const m = zeile.match(/^\s*(?:export\s+)?([A-Z0-9_]+)\s*=\s*(.*?)\s*$/);
    if (!m || !SAAS_ENV.test(m[1]) || process.env[m[1]] !== undefined) continue;
    const wert = m[2].replace(/^(['"])(.*)\1$/, "$2");
    if (wert) process.env[m[1]] = wert;
  }
} catch { /* no root .env.local: defaults apply */ }

// The UI calls the backend at /backend/... . Locally, FastAPI runs on port 8000;
// for deployment, set API_URL to the public backend address to avoid CORS issues.
const api = (process.env.API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Default proxy buffer is 10 MB; uploads may be up to 10 MiB plus multipart overhead (backend answers 413 above that).
  // Grok Bot queue jobs can take up to GROKBOT_TIMEOUT (900 s). The rewrite proxy otherwise
  // cuts the connection after 30 s (socket hang up / ECONNRESET) and the UI retries,
  // creating duplicate jobs. 960 s leaves a short buffer; Claude still returns in seconds.
  experimental: { proxyClientMaxBodySize: "11mb", proxyTimeout: 960_000 },
  // t243: everything stored (price database, history, submitted price lists/final bills) lives on /vault.
  // The query string is passed on, so /history?fall=<id> still opens that case.
  async redirects() {
    return [
      { source: "/preise", destination: "/vault?tab=preisdatenbank", permanent: false },
      { source: "/history", destination: "/vault?tab=historie", permanent: false },
      { source: "/einreichen", destination: "/vault?tab=einreichen", permanent: false },
    ];
  },
  async rewrites() {
    return [{ source: "/backend/:path*", destination: `${api}/:path*` }];
  },
};

export default nextConfig;

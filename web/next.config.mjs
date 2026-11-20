// Die Oberfläche spricht das Backend unter /backend/... an. Lokal ist das FastAPI auf Port 8000,
// im Deploy setzt ihr API_URL auf die öffentliche Backend-Adresse. So gibt es keine CORS-Probleme.
const api = (process.env.API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [{ source: "/backend/:path*", destination: `${api}/:path*` }];
  },
};

export default nextConfig;

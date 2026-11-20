// The UI calls the backend at /backend/... . Locally, FastAPI runs on port 8000;
// for deployment, set API_URL to the public backend address to avoid CORS issues.
const api = (process.env.API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Default proxy buffer is 10 MB; uploads may be up to 10 MiB plus multipart overhead (backend answers 413 above that).
  experimental: { proxyClientMaxBodySize: "11mb" },
  async rewrites() {
    return [{ source: "/backend/:path*", destination: `${api}/:path*` }];
  },
};

export default nextConfig;

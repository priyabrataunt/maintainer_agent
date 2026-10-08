import type { NextConfig } from "next";

// The browser only ever talks to this origin; /api/* is forwarded to the backend. That keeps
// the httpOnly login cookie first-party (no CORS, no cross-site cookies) and lets the GitHub
// OAuth callback land on the UI's own host.
const backend = process.env.BACKEND_URL ?? "http://localhost:8000";

const config: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/:path*` }];
  },
};

export default config;

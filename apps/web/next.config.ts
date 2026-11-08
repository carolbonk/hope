import type { NextConfig } from "next";

// Deployed: the browser calls `/v1/*` on the web origin and this proxies it to the API (see docs/deploy.md).
const apiOrigin = process.env.HOPE_API_ORIGIN?.replace(/\/+$/, "");

const config: NextConfig = {
  reactStrictMode: true,
  transpilePackages: ["@hope/schemas"],
  async rewrites() {
    return apiOrigin ? [{ source: "/v1/:path*", destination: `${apiOrigin}/v1/:path*` }] : [];
  },
};

export default config;

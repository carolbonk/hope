import type { NextConfig } from "next";

// Deployed: the browser calls `/v1/*` on the web origin and this proxies it to the API (see docs/deploy.md).
const apiOrigin = process.env.HOPE_API_ORIGIN?.replace(/\/+$/, "");
// HOPE_STATIC_EXPORT=1: plain files for the Hugging Face Space (offline demo). The draft route isn't exported,
// so that build drafts in the browser (NEXT_PUBLIC_HOPE_STATIC=1).
const staticExport = process.env.HOPE_STATIC_EXPORT === "1";

const config: NextConfig = {
  reactStrictMode: true,
  transpilePackages: ["@hope/schemas"],
  ...(staticExport
    ? { output: "export", images: { unoptimized: true } }
    : {
        async rewrites() {
          return apiOrigin ? [{ source: "/v1/:path*", destination: `${apiOrigin}/v1/:path*` }] : [];
        },
      }),
};

export default config;

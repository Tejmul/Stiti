import type { NextConfig } from "next";

// Built once into static files (`out/`) that Stiti's Python server serves on 127.0.0.1:7317.
// No Node process runs at runtime (8 GB Mac). In `next dev`, API calls are proxied to the Python server.
const dev = process.env.NODE_ENV === "development";
const PUBLIC = process.env.STITI_PUBLIC === "1";
const privateAlias = { "@/components/private-pages": "./src/components/private-pages.public.tsx" };

// STITI_PUBLIC=1 → the deployable site: landing only; /chat and /memory become a "runs on your Mac" page.
const nextConfig: NextConfig = {
  ...(PUBLIC ? { turbopack: { resolveAlias: privateAlias } } : {}),     // Next 16 builds with Turbopack
  env: { NEXT_PUBLIC_STITI_PUBLIC: PUBLIC ? "1" : "0" },                // public nav: no Chat/Memory links
  ...(dev ? {} : { output: "export" as const }),
  images: { unoptimized: true },
  trailingSlash: false,
  ...(dev
    ? {
        async rewrites() {
          return [
            { source: "/api/:path*", destination: "http://127.0.0.1:7317/api/:path*" },
            { source: "/icons/:path*", destination: "http://127.0.0.1:7317/icons/:path*" },
          ];
        },
      }
    : {}),
};

export default nextConfig;

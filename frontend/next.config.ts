import type { NextConfig } from "next";

// Built once into static files (`out/`) that Stiti's Python server serves on 127.0.0.1:7317.
// No Node process runs at runtime (8 GB Mac). In `next dev`, API calls are proxied to the Python server.
const dev = process.env.NODE_ENV === "development";

const nextConfig: NextConfig = {
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

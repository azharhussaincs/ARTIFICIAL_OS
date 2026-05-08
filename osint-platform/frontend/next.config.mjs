/** @type {import('next').NextConfig} */
//
// This file supports two modes, gated by NEXT_OUTPUT_EXPORT:
//
//   - Development / docker (default):
//       same behaviour as before — `next dev` proxies /api/* to the
//       FastAPI backend on localhost:8000 via rewrites().
//
//   - Static export for desktop packaging (NEXT_OUTPUT_EXPORT=1):
//       `next build` writes a self-contained `out/` tree that the
//       packaging pipeline copies into backend/app/static and FastAPI
//       serves directly. rewrites() are intentionally absent — they're
//       incompatible with `output: "export"` and unnecessary because
//       the export is served from the same origin as /api/*.
//
// Dev behaviour is byte-identical to the previous config when
// NEXT_OUTPUT_EXPORT is unset.

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
const isExport = process.env.NEXT_OUTPUT_EXPORT === "1";

const exportConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
};

const devConfig = {
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${API_BASE}/api/:path*` },
    ];
  },
};

const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  ...(isExport ? exportConfig : devConfig),
};

export default nextConfig;

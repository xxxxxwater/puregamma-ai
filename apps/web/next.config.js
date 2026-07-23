const { PHASE_DEVELOPMENT_SERVER } = require("next/constants");

// NEXT_PUBLIC_* values are inlined at build time. A production build without
// NEXT_PUBLIC_API_URL ships a client that calls http://localhost:8000 for
// every request, and no runtime env change can fix it — fail the build.
// (`next lint` also loads this config with the build phase, so match argv.)
const isRealBuild = process.argv.includes("build");

/** @type {(phase: string) => import('next').NextConfig} */
const nextConfig = (phase) => {
  if (isRealBuild && !process.env.NEXT_PUBLIC_API_URL) {
    throw new Error("NEXT_PUBLIC_API_URL must be set for production builds");
  }
  return {
    reactStrictMode: true,
    output: "standalone",
    // Dev uses .next, builds use .next-build (the Dockerfile copies from there).
    // Deriving it here keeps `next build` scripts portable across shells.
    distDir: process.env.NEXT_DIST_DIR || (phase === PHASE_DEVELOPMENT_SERVER ? ".next" : ".next-build"),
    transpilePackages: ["lucide-react"]
  };
};

module.exports = nextConfig;

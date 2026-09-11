const { PHASE_DEVELOPMENT_SERVER } = require("next/constants");

// NEXT_PUBLIC_* values are inlined at build time. A production build without
// NEXT_PUBLIC_API_URL ships a client that calls http://localhost:8000 for
// every request, and no runtime env change can fix it — fail the build.
// (`next lint` also loads this config with the build phase, so match argv.)
const isRealBuild = process.argv.includes("build");

// Development-only API proxy.
//
// Set NEXT_PUBLIC_API_URL=/__dev-api together with DEV_API_PROXY_TARGET=<api
// origin> and the dev server forwards every `/__dev-api/*` request to that
// origin, so the browser sees a same-origin API exactly like Caddy in
// production. Without this, opening the app on localhost against the deployed
// API is blocked by CORS: production `CORS_ORIGINS` allows only the app origin,
// the browser rejects the preflight, and no request-level test stub can
// intercept a request the browser refuses to send.
//
// `next dev` reloads the config on change, so a target can be added after start.
const DEV_PREFIX = "/__dev-api";
const devTarget = process.env.DEV_API_PROXY_TARGET;

/** @type {(phase: string) => import('next').NextConfig} */
const nextConfig = (phase) => {
  if (isRealBuild && !process.env.NEXT_PUBLIC_API_URL) {
    throw new Error("NEXT_PUBLIC_API_URL must be set for production builds");
  }
  const isDev = phase === PHASE_DEVELOPMENT_SERVER;
  return {
    reactStrictMode: true,
    output: "standalone",
    // Dev uses .next, builds use .next-build (the Dockerfile copies from there).
    // Deriving it here keeps `next build` scripts portable across shells.
    distDir: process.env.NEXT_DIST_DIR || (isDev ? ".next" : ".next-build"),
    transpilePackages: ["lucide-react"],
    ...(isDev && devTarget
      ? {
          async rewrites() {
            return [{ source: `${DEV_PREFIX}/:path*`, destination: `${devTarget.replace(/\/+$/, "")}/:path*` }];
          }
        }
      : {})
  };
};

module.exports = nextConfig;

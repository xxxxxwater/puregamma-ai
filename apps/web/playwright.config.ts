import { defineConfig, devices } from "@playwright/test";

const port = process.env.PLAYWRIGHT_PORT || "3000";
// `NEXT_PUBLIC_API_URL` is inlined into the client bundle at start-up, so the
// API host the browser talks to is decided HERE, not by `page.route()`.
//
// It points at the dev server's own `/__dev-api` proxy (see next.config.js)
// rather than the deployed API on purpose. A cross-origin API makes the browser
// run a CORS preflight, and production `CORS_ORIGINS` allows only the app
// origin — the browser then fails the request before it is sent, so no request
// stub can intercept it and the assertions would test a network-error banner
// instead of the UI. The dev proxy gives the app a same-origin API, exactly
// like Caddy in production, and leaves production CORS untouched.
const apiUrl = process.env.NEXT_PUBLIC_API_URL || "/__dev-api";
const apiProxyTarget = process.env.DEV_API_PROXY_TARGET || "https://api.puregamma.ai";
// Server Components fetch the API from the Next.js process, where no
// `page.route()` stub can reach. They are pointed at a local fixture API
// (tests/e2e/playwright/fixtures/ssr-api.mjs) that serves checked-in fixtures
// and answers 503 for everything else, so the suite runs fully offline.
const ssrApiPort = process.env.PLAYWRIGHT_SSR_API_PORT || "3599";
const ssrApiUrl = process.env.PLAYWRIGHT_SSR_API_URL || `http://127.0.0.1:${ssrApiPort}`;

// `set "KEY=VALUE" && ...` rather than `set KEY=VALUE&& ...`: without the space
// the value keeps the trailing whitespace, so `REQUIRE_AUTH` reads as "false "
// and the middleware's `=== "true"` check silently never matches — the suite
// then only ever saw `/login?returnTo=...` for authenticated routes.
const devEnv: Record<string, string> = {
  NEXT_DIST_DIR: ".next-playwright",
  NEXT_PUBLIC_INITIAL_LAUNCH_MODE: "false",
  NEXT_PUBLIC_API_URL: apiUrl,
  DEV_API_PROXY_TARGET: apiProxyTarget,
  REQUIRE_AUTH: "false",
  PUREGAMMA_SERVER_API_URL: ssrApiUrl,
};
const devCommand = process.platform === "win32"
  ? `${Object.entries(devEnv).map(([key, value]) => `set "${key}=${value}"`).join(" && ")} && node ./node_modules/next/dist/bin/next dev --hostname 127.0.0.1 --port ${port}`
  : `${Object.entries(devEnv).map(([key, value]) => `${key}=${value}`).join(" ")} node ./node_modules/next/dist/bin/next dev --hostname 127.0.0.1 --port ${port}`;

export default defineConfig({
  testDir: "../../tests/e2e/playwright",
  timeout: 30_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: process.env.CI ? 2 : 3,
  reporter: [["list"], ["html", { open: "never", outputFolder: "../../playwright-report" }]],
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL || `http://127.0.0.1:${port}`,
    trace: "retain-on-failure",
    launchOptions: {
      ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH } : {}),
      // Hermetic by default: the browser resolves only loopback, so a page's
      // third-party reads (market data sockets, CDNs, analytics) fail fast and
      // the page must render its unavailable state, instead of the suite
      // depending on, and waiting for, real external services.
      ...(process.env.PLAYWRIGHT_ALLOW_EXTERNAL === "1" ? {} : { args: ["--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1, EXCLUDE localhost"] }),
    },
  },
  webServer: [
    {
      command: `node ../../tests/e2e/playwright/fixtures/ssr-api.mjs ${ssrApiPort}`,
      url: `http://127.0.0.1:${ssrApiPort}/__health`,
      reuseExistingServer: true,
      timeout: 30_000,
    },
    {
      command: devCommand,
      url: `http://127.0.0.1:${port}`,
      reuseExistingServer: true,
      timeout: 120_000,
    },
  ],
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile-chrome", use: { ...devices["Pixel 5"] } },
  ],
});

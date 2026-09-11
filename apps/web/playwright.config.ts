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
const devCommand = process.platform === "win32"
  ? `set NEXT_DIST_DIR=.next-playwright&& set NEXT_PUBLIC_INITIAL_LAUNCH_MODE=false&& set NEXT_PUBLIC_API_URL=${apiUrl}&& set DEV_API_PROXY_TARGET=${apiProxyTarget}&& set REQUIRE_AUTH=false&& node ./node_modules/next/dist/bin/next dev --hostname 127.0.0.1 --port ${port}`
  : `NEXT_DIST_DIR=.next-playwright NEXT_PUBLIC_INITIAL_LAUNCH_MODE=false NEXT_PUBLIC_API_URL=${apiUrl} DEV_API_PROXY_TARGET=${apiProxyTarget} REQUIRE_AUTH=false node ./node_modules/next/dist/bin/next dev --hostname 127.0.0.1 --port ${port}`;

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
    ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH ? { launchOptions: { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH } } : {}),
  },
  webServer: {
    command: devCommand,
    url: `http://127.0.0.1:${port}`,
    reuseExistingServer: true,
    timeout: 120_000,
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile-chrome", use: { ...devices["Pixel 5"] } },
  ],
});

import { defineConfig, devices } from "@playwright/test";

// Standalone config for the LIVE acceptance run: no dev server, no local API.
// The base URL is the deployed site, reached over the public internet.
//
//   LIVE_TOKEN=<pg_session token> npx playwright test \
//     --config ../../tests/e2e/live/playwright.live.config.ts
//
// The token comes from deploy/release-live-session.sh on the server, which also
// deletes the disposable account afterwards.
export default defineConfig({
  testDir: ".",
  timeout: 120_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: process.env.LIVE_BASE_URL || "https://app.puregamma.ai",
    trace: "retain-on-failure",
    ignoreHTTPSErrors: true,
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile-chrome", use: { ...devices["Pixel 5"] } },
  ],
});

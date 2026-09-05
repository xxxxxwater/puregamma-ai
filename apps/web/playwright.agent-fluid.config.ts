import { defineConfig, devices } from "@playwright/test";

const port = process.env.PLAYWRIGHT_FLUID_PORT || "3011";

export default defineConfig({
  testDir: "../../tests/e2e/playwright",
  testMatch: "agent-fluid.spec.ts",
  timeout: 30_000,
  expect: { timeout: 8_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"], ["html", { open: "never", outputFolder: "../../playwright-fluid-report" }]],
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  // CI starts Next explicitly before invoking Playwright. Keeping server startup
  // out of Playwright makes readiness failures observable in the Actions log
  // instead of surfacing as an opaque webServer timeout.
  projects: [
    { name: "desktop-chrome", use: { ...devices["Desktop Chrome"], browserName: "chromium" } },
    { name: "iphone-safari", use: { ...devices["iPhone 13"], browserName: "webkit" } },
  ],
});

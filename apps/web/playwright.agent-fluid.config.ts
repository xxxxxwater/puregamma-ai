import { defineConfig, devices } from "@playwright/test";

const port = process.env.PLAYWRIGHT_FLUID_PORT || "3011";
const devCommand = process.platform === "win32"
  ? `set ENABLE_QA_SURFACES=true&& set NEXT_DIST_DIR=.next-fluid-playwright&& set NEXT_PUBLIC_INITIAL_LAUNCH_MODE=false&& set REQUIRE_AUTH=false&& node ./node_modules/next/dist/bin/next dev --hostname 127.0.0.1 --port ${port}`
  : `ENABLE_QA_SURFACES=true NEXT_DIST_DIR=.next-fluid-playwright NEXT_PUBLIC_INITIAL_LAUNCH_MODE=false REQUIRE_AUTH=false node ./node_modules/next/dist/bin/next dev --hostname 127.0.0.1 --port ${port}`;

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
  webServer: {
    command: devCommand,
    url: `http://127.0.0.1:${port}/__qa/agent-fluid`,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
  projects: [
    { name: "desktop-chrome", use: { ...devices["Desktop Chrome"], browserName: "chromium" } },
    { name: "iphone-safari", use: { ...devices["iPhone 13"], browserName: "webkit" } },
  ],
});

import { defineConfig, devices } from "@playwright/test";

const port = process.env.PLAYWRIGHT_PORT || "3000";
const devCommand = process.platform === "win32"
  ? `set NEXT_DIST_DIR=.next-playwright&& set NEXT_PUBLIC_INITIAL_LAUNCH_MODE=false&& set REQUIRE_AUTH=false&& node ./node_modules/next/dist/bin/next dev --hostname 127.0.0.1 --port ${port}`
  : `NEXT_DIST_DIR=.next-playwright NEXT_PUBLIC_INITIAL_LAUNCH_MODE=false REQUIRE_AUTH=false node ./node_modules/next/dist/bin/next dev --hostname 127.0.0.1 --port ${port}`;

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

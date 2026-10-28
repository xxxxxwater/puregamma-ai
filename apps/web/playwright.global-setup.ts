import type { FullConfig } from "@playwright/test";

/**
 * Pre-compile the dev server's error pages before the first test.
 *
 * The first unstubbed API call the dev proxy answers with a 500 makes `next
 * dev` compile the pages-router `/_error`. When that happens mid-test, the page
 * being loaded waits on the compile and can miss hydration or `load` within the
 * test timeout. Same paths as tests/e2e/playwright/fixtures/warm-dev-server.mjs.
 * Harmless against a production server (both answer immediately).
 */
export default async function globalSetup(config: FullConfig) {
  const baseURL = String(config.projects[0]?.use.baseURL ?? "").replace(/\/+$/, "");
  if (!baseURL) return;
  for (const path of ["/__dev-api/warmup", "/en/__warmup-not-found"]) {
    try {
      const response = await fetch(`${baseURL}${path}`, { redirect: "manual", signal: AbortSignal.timeout(120_000) });
      await response.arrayBuffer();
    } catch {
      // A warm-up that fails leaves the suite exactly as it was without it.
    }
  }
}

import { expect, test } from "@playwright/test";

const openHarness = async (page: import("@playwright/test").Page) => {
  const response = await page.goto("/qa/agent-fluid");
  expect(response?.status()).toBe(200);
  await expect(page.getByRole("heading", { name: "Agent Fluid Interaction Harness" })).toBeVisible();
};

const readHistoryWidth = async (page: import("@playwright/test").Page) => page.getByTestId("history-grid").evaluate((node) => {
  const value = getComputedStyle(node).getPropertyValue("--agent-history-width");
  return Number.parseFloat(value);
});

const readSheetX = async (page: import("@playwright/test").Page) => page.getByTestId("mobile-sheet").evaluate((node) => {
  const match = node.style.transform.match(/translate3d\((-?[\d.]+)px/);
  return match ? Number.parseFloat(match[1]) : Number.NaN;
});

const readInlineTransform = async (page: import("@playwright/test").Page) => page.getByTestId("fluid-press").evaluate((node) => {
  const matrix = new DOMMatrixReadOnly(getComputedStyle(node).transform);
  return { x: matrix.m41, y: matrix.m42, scaleX: matrix.a, scaleY: matrix.d };
});

test("desktop sidebar spring is interruptible and preserves presentation state", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop-chrome");
  await openHarness(page);
  const toggle = page.getByTestId("toggle-history");

  expect(await readHistoryWidth(page)).toBeGreaterThan(240);
  await toggle.click();

  // CI frame scheduling can be noisy. Observe the first real presentation
  // movement instead of assuming the spring has rendered by an arbitrary 80ms.
  await expect.poll(() => readHistoryWidth(page), { timeout: 1_500 }).toBeLessThan(240);
  const collapsing = await readHistoryWidth(page);
  expect(collapsing).toBeGreaterThan(54);

  // Reverse before the first spring settles. A scripted transition would jump
  // or restart; the rAF spring should reverse from its current presentation value.
  await toggle.click();
  await expect.poll(() => readHistoryWidth(page), { timeout: 1_500 }).toBeGreaterThan(243);
  const expanded = await readHistoryWidth(page);
  expect(expanded).toBeLessThanOrEqual(244.5);
});

test("anchored settings materializes above its trigger without layout reflow", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop-chrome");
  await openHarness(page);
  const trigger = page.getByTestId("settings-trigger");
  await trigger.click();
  const sheet = page.getByTestId("settings-sheet");
  await expect(sheet).toBeVisible();

  // Measure after the 180ms materialization transform has settled; during the
  // scale-in phase the visual bounding box is intentionally ~1px closer.
  await page.waitForTimeout(220);
  const triggerBox = await trigger.boundingBox();
  const sheetBox = await sheet.boundingBox();
  expect(triggerBox).not.toBeNull();
  expect(sheetBox).not.toBeNull();
  expect(sheetBox!.y + sheetBox!.height).toBeLessThanOrEqual(triggerBox!.y - 8);
});

test("composer press follows pointer, applies hysteresis, and springs home", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop-chrome");
  await openHarness(page);
  const button = page.getByTestId("fluid-press");
  const box = await button.boundingBox();
  expect(box).not.toBeNull();
  const x = box!.x + box!.width / 2;
  const y = box!.y + box!.height / 2;

  await page.mouse.move(x, y);
  await page.mouse.down();
  const pressed = await readInlineTransform(page);
  expect(pressed.scaleX).toBeLessThan(0.98);
  expect(pressed.y).toBeGreaterThan(0);

  // >10px movement becomes a gesture, so releasing must not activate the button.
  await page.mouse.move(x + 24, y + 3, { steps: 3 });
  await page.mouse.up();
  await expect(page.getByTestId("press-count")).toHaveText("clicks:0");

  await expect.poll(async () => {
    const resting = await readInlineTransform(page);
    return Math.max(Math.abs(resting.x), Math.abs(resting.y), Math.abs(resting.scaleX - 1));
  }, { timeout: 1_500 }).toBeLessThan(0.02);

  await button.click();
  await expect(page.getByTestId("press-count")).toHaveText("clicks:1");
});

test("reduced motion snaps the sidebar instead of animating it", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop-chrome");
  await page.emulateMedia({ reducedMotion: "reduce" });
  await openHarness(page);
  await page.getByTestId("toggle-history").click();
  await page.waitForTimeout(30);
  expect(await readHistoryWidth(page)).toBeLessThanOrEqual(52.5);
});

test("iPhone WebKit history sheet accepts a fast close flick with momentum projection", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "iphone-safari");
  await openHarness(page);
  await page.getByTestId("open-mobile-history").click();
  // Headless WebKit can deliver sparse rAF under CI. Within 8px on a 320px
  // sheet is visually settled; the post-flick close assertion stays strict.
  await expect.poll(async () => Math.abs(await readSheetX(page)), { timeout: 1_500 }).toBeLessThan(8);

  const grab = page.getByTestId("mobile-grab");
  const box = await grab.boundingBox();
  expect(box).not.toBeNull();
  const startX = Math.min(box!.x + box!.width - 36, 286);
  const y = box!.y + box!.height / 2;

  await page.mouse.move(startX, y);
  await page.mouse.down();
  await page.mouse.move(startX - 40, y, { steps: 2 });
  await page.mouse.move(startX - 180, y, { steps: 2 });
  await page.mouse.up();

  await expect.poll(() => readSheetX(page), { timeout: 1_500 }).toBeLessThan(-318);
});

test("streaming state remains visible but subtle in both rendering engines", async ({ page }) => {
  await openHarness(page);
  const message = page.getByTestId("streaming-message");
  await expect(message).toBeVisible();
  await expect(message.getByText("Live", { exact: true })).toBeVisible();
  await expect(message).toHaveAttribute("aria-busy", "true");
});

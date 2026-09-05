import { expect, test } from "@playwright/test";

const readHistoryWidth = async (page: import("@playwright/test").Page) => page.getByTestId("history-grid").evaluate((node) => {
  const value = getComputedStyle(node).getPropertyValue("--agent-history-width");
  return Number.parseFloat(value);
});

const readSheetX = async (page: import("@playwright/test").Page) => page.getByTestId("mobile-sheet").evaluate((node) => {
  const match = node.style.transform.match(/translate3d\((-?[\d.]+)px/);
  return match ? Number.parseFloat(match[1]) : Number.NaN;
});

test.beforeEach(async ({ page }) => {
  await page.goto("/__qa/agent-fluid");
  await expect(page.getByRole("heading", { name: "Agent Fluid Interaction Harness" })).toBeVisible();
});

test("desktop sidebar spring is interruptible and preserves presentation state", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop-chrome");
  const toggle = page.getByTestId("toggle-history");

  expect(await readHistoryWidth(page)).toBeGreaterThan(240);
  await toggle.click();
  await page.waitForTimeout(80);
  const collapsing = await readHistoryWidth(page);
  expect(collapsing).toBeLessThan(240);
  expect(collapsing).toBeGreaterThan(54);

  // Reverse before the first spring settles. A scripted transition would jump
  // or restart; the rAF spring should reverse from its current presentation value.
  await toggle.click();
  await page.waitForTimeout(700);
  const expanded = await readHistoryWidth(page);
  expect(expanded).toBeGreaterThan(243);
  expect(expanded).toBeLessThanOrEqual(244.5);
});

test("anchored settings materializes above its trigger without layout reflow", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop-chrome");
  const trigger = page.getByTestId("settings-trigger");
  await trigger.click();
  const sheet = page.getByTestId("settings-sheet");
  await expect(sheet).toBeVisible();

  const triggerBox = await trigger.boundingBox();
  const sheetBox = await sheet.boundingBox();
  expect(triggerBox).not.toBeNull();
  expect(sheetBox).not.toBeNull();
  expect(sheetBox!.y + sheetBox!.height).toBeLessThanOrEqual(triggerBox!.y - 6);
});

test("composer press follows pointer, applies hysteresis, and springs home", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop-chrome");
  const button = page.getByTestId("fluid-press");
  const box = await button.boundingBox();
  expect(box).not.toBeNull();
  const x = box!.x + box!.width / 2;
  const y = box!.y + box!.height / 2;

  await page.mouse.move(x, y);
  await page.mouse.down();
  const downTransform = await button.evaluate((node) => node.style.transform);
  expect(downTransform).toContain("scale(");
  expect(downTransform).not.toContain("scale(1.0000)");

  // >10px movement becomes a gesture, so releasing must not activate the button.
  await page.mouse.move(x + 24, y + 3, { steps: 3 });
  await page.mouse.up();
  await expect(page.getByTestId("press-count")).toHaveText("clicks:0");

  await page.waitForTimeout(500);
  const restingTransform = await button.evaluate((node) => node.style.transform);
  expect(restingTransform).toContain("translate3d(0.00px,0.00px,0)");

  await button.click();
  await expect(page.getByTestId("press-count")).toHaveText("clicks:1");
});

test("reduced motion snaps the sidebar instead of animating it", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop-chrome");
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.reload();
  await page.getByTestId("toggle-history").click();
  await page.waitForTimeout(30);
  expect(await readHistoryWidth(page)).toBeLessThanOrEqual(52.5);
});

test("iPhone WebKit history sheet accepts a fast close flick with momentum projection", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "iphone-safari");
  await page.getByTestId("open-mobile-history").click();
  await page.waitForTimeout(600);
  expect(Math.abs(await readSheetX(page))).toBeLessThan(1);

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
  await page.waitForTimeout(700);

  expect(await readSheetX(page)).toBeLessThan(-318);
});

test("streaming state remains visible but subtle in both rendering engines", async ({ page }) => {
  const message = page.getByTestId("streaming-message");
  await expect(message).toBeVisible();
  await expect(message.getByText("Live")).toBeVisible();
  await expect(message).toHaveAttribute("aria-busy", "true");
});

import { expect, test } from "@playwright/test";

test.describe("landing-page architecture visual", () => {
  test("presents the live system map inside a macOS display frame", async ({ page }) => {
    await page.goto("/en", { waitUntil: "domcontentloaded" });

    const computer = page.getByTestId("architecture-mac-window");
    await expect(computer).toBeVisible();
    await expect(computer.getByLabel("Close architecture preview")).toBeVisible();
    await expect(computer.getByLabel("Minimize architecture preview")).toBeVisible();
    await expect(computer.getByLabel("Expand architecture preview")).toBeVisible();

    const screen = page.getByTestId("architecture-system-map");
    await expect(screen).toBeVisible();
    await expect(screen).toContainText("PureGamma Runtime Map");
    await expect(screen).toContainText("HMAC");
    expect(await screen.locator("animateMotion").count()).toBeGreaterThan(0);

    const [computerBox, screenBox, captionBox, userBox, baseBox] = await Promise.all([
      computer.boundingBox(),
      screen.boundingBox(),
      page.getByTestId("architecture-map-caption").boundingBox(),
      screen.getByText("User", { exact: true }).boundingBox(),
      page.getByTestId("architecture-mac-base").boundingBox(),
    ]);

    expect(computerBox).not.toBeNull();
    expect(screenBox).not.toBeNull();
    expect(captionBox).not.toBeNull();
    expect(userBox).not.toBeNull();
    expect(baseBox).not.toBeNull();
    if (!computerBox || !screenBox || !captionBox || !userBox || !baseBox) return;

    const captionOverlapsUser = !(
      captionBox.x + captionBox.width <= userBox.x ||
      userBox.x + userBox.width <= captionBox.x ||
      captionBox.y + captionBox.height <= userBox.y ||
      userBox.y + userBox.height <= captionBox.y
    );
    expect(captionOverlapsUser).toBe(false);
    expect(computerBox.width).toBeGreaterThan(screenBox.width);
    expect(baseBox.width).toBeLessThan(computerBox.width);
    expect(baseBox.y).toBeGreaterThanOrEqual(screenBox.y + screenBox.height);
  });

  test("localizes the computer visual for Chinese visitors", async ({ page }) => {
    await page.goto("/zh", { waitUntil: "domcontentloaded" });

    const computer = page.getByTestId("architecture-mac-window");
    // The badge was renamed from "在线" (online) to "系统示意" (system map):
    // a static diagram must not claim live status.
    await expect(computer).toContainText("系统示意");
    await expect(computer).not.toContainText("在线");
    await expect(computer.getByLabel("关闭架构预览")).toBeVisible();
    await expect(page.getByTestId("architecture-system-map")).toContainText("PureGamma 运行图");
  });

  test("keeps the computer visual within a narrow viewport", async ({ browser }) => {
    const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
    const page = await context.newPage();
    await page.goto("/en", { waitUntil: "domcontentloaded" });

    const screen = page.getByTestId("architecture-system-map");
    const nodes = page.getByTestId("architecture-node");
    await expect(page.getByTestId("architecture-mac-window")).toBeVisible();
    await expect(nodes).toHaveCount(17);
    await expect
      .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth))
      .toBe(true);

    const screenBox = await screen.boundingBox();
    const nodeBoxes = await Promise.all(
      Array.from({ length: await nodes.count() }, (_, index) => nodes.nth(index).boundingBox()),
    );
    expect(screenBox).not.toBeNull();
    expect(nodeBoxes.every((box) => box !== null)).toBe(true);
    if (screenBox) {
      for (const nodeBox of nodeBoxes) {
        if (!nodeBox) throw new Error("Expected every architecture node to have a layout box");
        expect(nodeBox.x).toBeGreaterThanOrEqual(screenBox.x - 1);
        expect(nodeBox.y).toBeGreaterThanOrEqual(screenBox.y - 1);
        expect(nodeBox.x + nodeBox.width).toBeLessThanOrEqual(screenBox.x + screenBox.width + 1);
        expect(nodeBox.y + nodeBox.height).toBeLessThanOrEqual(screenBox.y + screenBox.height + 1);
      }

      const [userBox, apiBox, notificationBox] = await Promise.all([
        screen.getByText("User", { exact: true }).boundingBox(),
        screen.getByText("FastAPI API", { exact: true }).boundingBox(),
        screen.getByText("Notifications", { exact: true }).boundingBox(),
      ]);
      if (!userBox || !apiBox || !notificationBox) throw new Error("Expected flow anchor nodes to have layout boxes");
      const relativeCenterY = (box: NonNullable<typeof userBox>) => (box.y + box.height / 2 - screenBox.y) / screenBox.height;
      expect(relativeCenterY(userBox)).toBeCloseTo(0.06, 1);
      expect(relativeCenterY(apiBox)).toBeCloseTo(0.29, 1);
      expect(relativeCenterY(notificationBox)).toBeCloseTo(0.88, 1);
      const flowPaths = await screen.locator("svg path").evaluateAll((paths) => paths.map((path) => path.getAttribute("d")));
      expect(flowPaths).toContain("M 50 8 C 42 10, 30 12, 22 14.5");
      expect(flowPaths).toContain("M 50 31 C 50 58, 50 72, 50 88.5");
    }

    await context.close();
  });
});

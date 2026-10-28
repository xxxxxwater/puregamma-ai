import { expect, test } from "@playwright/test";

/**
 * The admin entry point for visitors who are not administrators.
 *
 * This spec used to look for an "Operational Control Room" page with Users,
 * Stripe and notification panels on one screen; that page was replaced by the
 * sectioned admin console, which admin-console.spec.ts covers (including the
 * signed-in non-admin permission state). What is left here is the signed-out
 * path: the admin guard sends the visitor to sign in and back, and never
 * renders the console.
 */
test.describe("/admin", () => {
  test("a signed-out visitor is sent to sign in and returned to the console", async ({ page }) => {
    await page.route("**/__dev-api/**", (route) => route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "offline" }) }));
    await page.route("**/__dev-api/me", (route) => route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ detail: "Not authenticated" }) }));

    await page.goto("/en/admin");

    await expect(page).toHaveURL(/\/en\/login\?returnTo=%2Fen%2Fadmin$/);
    await expect(page.getByRole("navigation", { name: "Admin sections" })).toHaveCount(0);
  });

  test("a non-administrator never sees the admin sections", async ({ page }) => {
    await page.route("**/__dev-api/**", (route) => route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "offline" }) }));
    await page.route("**/__dev-api/me", (route) =>
      route.fulfill({ contentType: "application/json", body: JSON.stringify({ user: { id: "u1", email: "user@example.invalid", name: "User", role: "user", plan: "Pro", credit_balance: 0, auth_provider: "email" } }) }),
    );

    await page.goto("/zh/admin");

    await expect(page.getByText("需要管理员权限").first()).toBeVisible();
    await expect(page.getByRole("navigation", { name: "管理后台分区" })).toHaveCount(0);
    await expect(page.getByText("运行状态读取失败。")).toHaveCount(0);
  });
});

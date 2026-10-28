import { expect, test, type Page } from "@playwright/test";

/**
 * /daily-push reads the user's delivery preferences and plan on the server.
 * Those reads go to the offline fixture API (fixtures/ssr-api.mjs): anonymous
 * requests get 401, and a request carrying the fixture session gets the
 * checked-in Pro-plan fixtures.
 *
 * (This spec used to expect an iMessage channel pre-selected for every visitor
 * and a fixed disclaimer; the page now refuses to show an editor it could not
 * load, and offers only the channels the plan includes.)
 */
const FIXTURE_SESSION = "playwright-fixture-session";

async function signIn(page: Page, baseURL: string | undefined) {
  await page.context().addCookies([{ name: "pg_session", value: FIXTURE_SESSION, url: baseURL ?? "http://127.0.0.1:3000" }]);
  await page.route("**/__dev-api/**", (route) => route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "offline" }) }));
  await page.route("**/__dev-api/me", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify({ user: { id: "u-push", email: "push@example.invalid", name: "Push", role: "user", plan: "Pro", credit_balance: 1200, auth_provider: "email" } }) }),
  );
}

test.describe("/daily-push", () => {
  test("without its settings the page says so and offers no editor that could overwrite them", async ({ page }) => {
    await page.goto("/en/daily-push");

    await expect(page.getByRole("heading", { name: "Daily Research Delivery" })).toBeVisible();
    await expect(page.getByTestId("daily-push-unavailable")).toContainText("Delivery settings are unavailable right now");
    await expect(page.getByRole("button", { name: "Save" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Send test" })).toHaveCount(0);
  });

  test("a Pro user edits real settings, sees only plan channels and can record a test send", async ({ page, baseURL }) => {
    await signIn(page, baseURL);
    let sent: Record<string, unknown> | null = null;
    await page.route("**/__dev-api/notifications/send", async (route) => {
      sent = route.request().postDataJSON();
      await route.fulfill({ contentType: "application/json", body: JSON.stringify({ delivery: { id: "d1", channel: "email", status: "sent", created_at: "2026-10-28T09:00:00+00:00", sent_at: "2026-10-28T09:00:01+00:00", provider_response: {} } }) });
    });

    await page.goto("/en/daily-push");

    await expect(page.getByRole("heading", { name: "Delivery settings" })).toBeVisible();
    const channel = page.getByLabel("Channel");
    await expect(channel).toHaveValue("email");
    // Pro includes email and Telegram; iMessage is a Max/Enterprise channel.
    await expect(channel.locator("option")).toHaveText(["email", "telegram"]);
    await expect(page.getByLabel("Timezone")).toHaveValue("Asia/Shanghai");
    await expect(page.getByText("No deliveries yet")).toBeVisible();

    await page.getByRole("button", { name: "Send test" }).click();
    await expect(page.getByText("Test delivery recorded")).toBeVisible();
    expect(sent).toMatchObject({ channel: "email", locale: "en" });
    await expect(page.getByText("No deliveries yet")).toHaveCount(0);
  });
});

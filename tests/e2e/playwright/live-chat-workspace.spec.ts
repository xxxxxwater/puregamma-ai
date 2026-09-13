/**
 * Live acceptance for the deployed chat workspace.
 *
 * Unlike the stubbed specs, this talks to the real api.puregamma.ai through the
 * real app.puregamma.ai. It exists to answer questions a stub cannot:
 *
 *  - does the session cookie reach the API host for an image subresource? The
 *    download endpoint is on api.puregamma.ai while the page is app.puregamma.ai,
 *    and a SameSite or CORS mistake would only show up here.
 *  - does a real uploaded file come back as a card with a working link?
 *  - does the permission selector report what the server stored?
 *
 * Two constraints shape this file. The API rate-limits writes per client
 * (EXPENSIVE_RATE_LIMIT_PER_MINUTE, 20/min in production), so the run makes as
 * few uploads as it can and retries a 429 instead of failing. And a real signup
 * needs a captcha, so LIVE_TOKEN is minted server-side for a disposable account
 * by deploy/release-live-session.sh; the account only ever touches its own rows.
 */
import { expect, test, type APIResponse } from "@playwright/test";

const BASE = (process.env.LIVE_BASE_URL || "https://app.puregamma.ai").replace(/\/+$/, "");
const TOKEN = process.env.LIVE_TOKEN || "";
const API = (process.env.LIVE_API_URL || "https://api.puregamma.ai").replace(/\/+$/, "");

test.skip(!TOKEN, "LIVE_TOKEN not provided");

/**
 * A valid 2x2 PNG. Generated rather than hand-written: a hand-typed base64 blob
 * decoded by Pillow's lazy loader but raised inside EXIF transposition, which
 * made this spec fail against a server that was behaving correctly.
 */
const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAFklEQVR4nGP8z8DAwMDAwMDEAAWMDAwAFvcBaZzTzB0AAAAASUVORK5CYII=",
  "base64",
);

function auth() {
  return { Authorization: `Bearer ${TOKEN}` };
}

/** Retry a 429 (per-client write budget) rather than reporting it as a defect. */
async function withinRateLimit(send: () => Promise<APIResponse>): Promise<APIResponse> {
  let response = await send();
  for (let attempt = 0; attempt < 4 && response.status() === 429; attempt += 1) {
    const retryAfter = Number(response.headers()["retry-after"] || "60");
    await new Promise((resolve) => setTimeout(resolve, Math.min(retryAfter, 65) * 1000));
    response = await send();
  }
  return response;
}

test.describe("live chat workspace", () => {
  test("the deployed composer carries a real attachment round trip", async ({ page, context }) => {
    test.setTimeout(180_000);
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(String(error)));

    await context.addCookies([
      {
        name: process.env.LIVE_COOKIE_NAME || "pg_session",
        value: TOKEN,
        domain: ".puregamma.ai",
        path: "/",
        httpOnly: true,
        secure: true,
        sameSite: "Lax",
      },
    ]);

    await page.goto(`${BASE}/zh/chat`);
    await expect(page.getByTestId("harness-composer"), "the chat workspace did not mount").toBeVisible({ timeout: 20000 });
    await expect(page).not.toHaveURL(/\/login/);

    // The permission selector must report what the server stored, not a default.
    const permission = page.getByLabel("对话权限", { exact: true });
    await expect(permission).toBeVisible();
    await expect(permission).toHaveValue("workspace-write");

    // A text attachment: upload, then read the same bytes back from the API host.
    const stamp = Date.now().toString(36);
    const name = `live-${stamp}.txt`;
    await page.locator('input[type="file"]').setInputFiles({
      name,
      mimeType: "text/plain",
      buffer: Buffer.from(`live acceptance ${stamp}`),
    });
    const link = page.getByRole("link", { name });
    await expect(link, "the uploaded file did not appear as a card").toBeVisible({ timeout: 30000 });
    const href = await link.getAttribute("href");
    expect(href, "the card must link to the authenticated download endpoint").toContain("/api/agent/attachments/");

    const response = await withinRateLimit(() => page.request.get(href!, { headers: auth() }));
    expect(response.status(), `GET ${href} -> ${response.status()}`).toBe(200);
    expect(await response.text()).toBe(`live acceptance ${stamp}`);

    // The same download without a session must be refused: the endpoint is
    // owner-scoped, and this is the live proof of it.
    const anonymous = await page.request.get(href!, { headers: { Authorization: "" } });
    expect(anonymous.status(), "the download endpoint answered an anonymous caller").toBe(401);

    expect(errors, `runtime errors on the live chat page:\n${errors.join("\n")}`).toEqual([]);

    await page.screenshot({ path: "../../.preview-live-chat-1280.png", fullPage: false });
  });

  test("the deployed API stores an image and serves it back to its owner", async ({ page, context }) => {
    test.setTimeout(180_000);
    await context.addCookies([
      {
        name: process.env.LIVE_COOKIE_NAME || "pg_session",
        value: TOKEN,
        domain: ".puregamma.ai",
        path: "/",
        httpOnly: true,
        secure: true,
        sameSite: "Lax",
      },
    ]);

    const upload = await withinRateLimit(() =>
      page.request.post(`${API}/api/agent/attachments?name=live-image.png`, {
        headers: { ...auth(), "Content-Type": "application/octet-stream" },
        data: PNG,
      }),
    );
    expect(upload.status(), `upload -> ${upload.status()} ${await upload.text()}`).toBe(200);
    const attachment = (await upload.json()).attachment as { id: string; kind: string; url: string; size: number };
    expect(attachment.kind, "a PNG must be stored as an image").toBe("image");
    expect(attachment.size).toBeGreaterThan(0);

    const download = await withinRateLimit(() => page.request.get(`${API}${attachment.url}`, { headers: auth() }));
    expect(download.status()).toBe(200);
    expect(download.headers()["content-type"]).toContain("image/");
    expect((await download.body()).length).toBe(attachment.size);

    // Render it in the page pointed at the API host: this is the subresource
    // case a SameSite or CORS mistake breaks, and only a real browser sees it.
    // No query parameter is added: the browser must carry the session cookie on
    // its own, which is the behaviour under test.
    await page.goto(`${BASE}/zh/chat`);
    const loaded = await page.evaluate(async (url) => {
      const image = new Image();
      const done = new Promise<number>((resolve) => {
        image.onload = () => resolve(image.naturalWidth);
        image.onerror = () => resolve(-1);
      });
      image.src = url;
      return await done;
    }, `${API}${attachment.url}`);
    expect(loaded, "the image did not decode from the API host in a real browser").toBeGreaterThan(0);
  });
});

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
import { expect, request, test, type APIResponse } from "@playwright/test";

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

    // The add-file button stays disabled until the workspace policy has loaded,
    // and a click on a disabled control is silently ignored. Waiting for it is
    // what makes this spec test the upload instead of racing it.
    const fileInput = page.locator('input[type="file"]');
    await expect(page.getByRole("button", { name: "添加文件" })).toBeEnabled({ timeout: 30000 });

    // A text attachment: upload, then read the same bytes back from the API host.
    const stamp = Date.now().toString(36);
    const name = `live-${stamp}.txt`;
    await fileInput.setInputFiles({
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

    // Removing it frees the bytes and says so, instead of leaving a card that
    // points at a file the API refuses to serve.
    await page.getByRole("button", { name: `移除: ${name}` }).click();
    await expect(page.getByText("已移除").first()).toBeVisible({ timeout: 20000 });
    // `href` is already an absolute API URL; prefixing the API origin again
    // produced "api.puregamma.aihttps://..." and ENOTFOUND.
    const afterRemoval = await page.request.get(href!, { headers: auth() });
    expect(afterRemoval.status(), "a removed attachment must not still download").toBe(410);

    // The same download without a session must be refused: the endpoint is
    // owner-scoped, and this is the live proof of it. `page.request` shares the
    // browser context's cookies, so an empty Authorization header would still
    // carry the session and prove nothing — this needs a cookie-less client.
    const anonymousClient = await request.newContext({ baseURL: API });
    try {
      const anonymous = await anonymousClient.get(href!);
      expect(anonymous.status(), "the download endpoint answered an anonymous caller").toBe(401);
    } finally {
      await anonymousClient.dispose();
    }

    expect(errors, `runtime errors on the live chat page:\n${errors.join("\n")}`).toEqual([]);

    await page.screenshot({ path: "../../.preview-live-chat-1280.png", fullPage: false });
  });

  test("a stored attachment can be removed and its space is usable again", async ({ page, context }) => {
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

    const stamp = Date.now().toString(36);
    const name = `space-${stamp}.txt`;
    await page.goto(`${BASE}/zh/chat`);
    await expect(page.getByRole("button", { name: "添加文件" })).toBeEnabled({ timeout: 30000 });

    // An image attachment is stored as an image and handed back byte-for-byte.
    const upload = await withinRateLimit(() =>
      page.request.post(`${API}/api/agent/attachments?name=live-${stamp}.png`, {
        headers: { ...auth(), "Content-Type": "application/octet-stream" },
        data: PNG,
      }),
    );
    expect(upload.status(), `upload -> ${upload.status()} ${await upload.text()}`).toBe(200);
    const image = (await upload.json()).attachment as { id: string; kind: string; mime: string; url: string; size: number };
    expect(image.kind, "a PNG must be stored as an image").toBe("image");
    expect(image.mime, "and must come back as a PNG").toBe("image/png");
    const imageBytes = await withinRateLimit(() => page.request.get(`${API}${image.url}`, { headers: auth() }));
    expect(imageBytes.status()).toBe(200);
    expect((await imageBytes.body()).length).toBe(PNG.length);

    // Upload a text file through the real composer, then remove it there: the
    // card stays (marked removed) and the bytes are freed. No navigation in
    // between — the composer's tray belongs to the conversation it is on, so
    // reloading first would be testing a different screen.
    await page.locator('input[type="file"]').setInputFiles({
      name,
      mimeType: "text/plain",
      buffer: Buffer.from("space test"),
    });
    const link = page.getByRole("link", { name });
    await expect(link).toBeVisible({ timeout: 30000 });
    const href = await link.getAttribute("href");

    await page.getByRole("button", { name: `移除: ${name}` }).click();
    await expect(page.getByText("已移除").first()).toBeVisible({ timeout: 20000 });
    expect((await page.request.get(href!, { headers: auth() })).status()).toBe(410);

    // Space reclaimed means the next upload is accepted rather than answered with
    // ATTACHMENT_STORAGE_LIMIT, which is the dead end this replaced.
    const after = await withinRateLimit(() =>
      page.request.post(`${API}/api/agent/attachments?name=after-${stamp}.txt`, {
        headers: { ...auth(), "Content-Type": "application/octet-stream" },
        data: Buffer.from("accepted"),
      }),
    );
    expect(after.status(), `upload after removal -> ${after.status()} ${await after.text()}`).toBe(200);

    // And releasing an image works the same way.
    const released = await page.request.delete(`${API}/api/agent/attachments/${image.id}`, { headers: auth() });
    expect(released.status()).toBe(200);
    expect((await released.json()).attachment.removed).toBe(true);
    expect((await page.request.get(`${API}${image.url}`, { headers: auth() })).status()).toBe(410);
  });
});

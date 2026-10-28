// Offline API for server-rendered reads during the Playwright suite.
//
// `page.route()` only intercepts requests the *browser* makes. A Server
// Component (the homepage's model preview, for example) fetches the API from
// the Next.js process, which the browser never sees. Those reads are pointed
// here through PUREGAMMA_SERVER_API_URL (see apps/web/lib/api.ts and
// apps/web/playwright.config.ts) so the suite never reaches a real API.
//
// Only paths listed in ROUTES answer, from checked-in fixtures. Everything else
// answers the way the real API answers a request it cannot serve: 401 when the
// request carries no credentials (the suite never has a server-side session,
// exactly like an anonymous visitor), otherwise 503, an honest outage. A page
// must render its unauthorized/unavailable state, never invented data.
import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const fixture = (name) => JSON.parse(readFileSync(join(here, name), "utf8"));

/** The session cookie value a spec sets to render a signed-in server page. */
export const FIXTURE_SESSION = "playwright-fixture-session";

/**
 * Server-side GET reads the suite depends on, keyed by path (no query).
 * `auth: true` routes answer only a request carrying FIXTURE_SESSION, exactly
 * as the real API answers only a signed-in request.
 */
const ROUTES = {
  "/gateway/catalog": { auth: false, body: () => fixture("gateway-catalog.json") },
  "/notifications/preferences/daily-brief": { auth: true, body: () => fixture("ssr/daily-brief-preferences.json") },
  "/billing/subscription": { auth: true, body: () => fixture("ssr/billing-subscription-pro.json") },
  "/portfolio": { auth: true, body: () => fixture("ssr/portfolio-two-connections.json") },
  "/gateway/dashboard": { auth: true, body: () => fixture("ssr/gateway-dashboard.json") },
  "/gateway/keys": { auth: true, body: () => fixture("ssr/gateway-keys.json") },
  "/gateway/requests": { auth: true, body: () => fixture("ssr/gateway-requests.json") },
  "/gateway/usage": { auth: true, body: () => fixture("ssr/gateway-usage.json") },
};

const port = Number(process.env.SSR_API_PORT || process.argv[2] || 3599);

createServer((request, response) => {
  const path = new URL(request.url ?? "/", "http://fixture").pathname.replace(/\/+$/, "") || "/";
  const signedIn = new RegExp(`(?:^|;\\s*)pg_session=${FIXTURE_SESSION}(?:;|$)`).test(request.headers.cookie ?? "");
  const route = request.method === "GET" ? ROUTES[path] : undefined;
  const handler = route && (!route.auth || signedIn) ? route.body : undefined;
  if (path === "/__health") {
    response.writeHead(200, { "content-type": "text/plain" });
    response.end("ok");
    return;
  }
  if (!handler) {
    const credentialed = Boolean(request.headers.authorization) || /(?:^|;\s*)pg_session=/.test(request.headers.cookie ?? "");
    response.writeHead(credentialed ? 503 : 401, { "content-type": "application/json" });
    response.end(JSON.stringify(credentialed
      ? { detail: { code: "OFFLINE_FIXTURE_API", message: `No server-side fixture for ${request.method} ${path}` } }
      : { detail: "Not authenticated" }));
    return;
  }
  response.writeHead(200, { "content-type": "application/json" });
  response.end(JSON.stringify(handler()));
}).listen(port, "127.0.0.1", () => {
  process.stdout.write(`ssr fixture API on http://127.0.0.1:${port}\n`);
});

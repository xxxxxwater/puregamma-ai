/**
 * Which app surfaces require an authenticated session.
 *
 * This list used to live only in `middleware.ts`. The client-side
 * auth-expired watchdog needs the same answer, and two copies would drift:
 * adding a protected route in one place would leave the other silently wrong.
 * Both now read it from here.
 *
 * Paths are locale-stripped (call `stripLocale` first) so `/zh/account` and
 * `/account` behave identically.
 */
export const AUTHENTICATED_ROUTES = [
  "/account",
  "/admin",
  "/billing",
  "/chat",
  "/dashboard",
  "/gateway",
  "/memory",
  "/mobile-access",
  "/news",
  "/options",
  "/portfolio",
  "/reports",
  "/research",
] as const;

/**
 * True when `localPath` (already locale-stripped) is a route that needs a
 * session. Public surfaces such as the landing page (`/`) and the API docs
 * (`/api`) return false.
 */
export function requiresAuthentication(localPath: string): boolean {
  const path = localPath || "/";
  return AUTHENTICATED_ROUTES.some(
    (route) => path === route || path.startsWith(`${route}/`),
  );
}

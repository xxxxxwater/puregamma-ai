import { NextResponse, type NextRequest } from "next/server";
import { defaultLocale, isLocale, legacyLocaleRoutes, localeCookieName, localeFromAcceptLanguage, localePrefixPattern } from "@/i18n/routing";
import { requiresAuthentication } from "@/lib/route-access";
import { isChinaIP } from "@/lib/geoip";

const PUBLIC_FILE = /\.(.*)$/;
const INITIAL_LAUNCH_HIDDEN = ["/signals", "/playbooks", "/strategies", "/trading", "/nautilus", "/data-sources", "/integrations", "/daily-push", "/billing/mock-checkout"];

const PUBLIC_SAAS_HOSTS = new Set(["new.puregamma.ai", "app.puregamma.ai"]);
const INSTABOX_PREVIEW_HOST = /^3100-[a-z0-9]+\.instabox\.tech$/;

/** Next.js requires an absolute Location; accept only our known public hosts. */
function redirectTo(request: NextRequest, pathname: string, search = "") {
  const candidates = [request.headers.get("host"), request.headers.get("x-forwarded-host")];
  const publicHost = candidates
    .map((candidate) => candidate?.split(",")[0]?.trim().toLowerCase().replace(/:443$/, ""))
    .find((candidate) => candidate && (PUBLIC_SAAS_HOSTS.has(candidate) || INSTABOX_PREVIEW_HOST.test(candidate)));
  const origin = publicHost ? `https://${publicHost}` : request.nextUrl.origin;
  return NextResponse.redirect(new URL(`${pathname}${search}`, origin));
}

async function resolveLocale(request: NextRequest, useGeo: boolean): Promise<string> {
  const cookieLocale = request.cookies.get(localeCookieName)?.value;
  if (isLocale(cookieLocale)) return cookieLocale;
  const acceptLocale = localeFromAcceptLanguage(request.headers.get("accept-language"));
  if (acceptLocale !== defaultLocale) return acceptLocale;
  // Geo lookup is a paid, rate-limited external call — only worth it for the
  // landing page, not for every deep-link/404/crawler request.
  if (!useGeo) return defaultLocale;
  const isCN = await isChinaIP(request.headers);
  return isCN ? "zh" : defaultLocale;
}

export async function middleware(request: NextRequest) {
  const { pathname, search } = request.nextUrl;

  if (pathname.startsWith("/api") || pathname.startsWith("/_next") || PUBLIC_FILE.test(pathname)) {
    return NextResponse.next();
  }

  const pathnameLocale = pathname.match(localePrefixPattern)?.[1];
  if (isLocale(pathnameLocale)) {
    const localPath = pathname.replace(localePrefixPattern, "") || "/";
    const initialLaunch = process.env.NEXT_PUBLIC_INITIAL_LAUNCH_MODE !== "false";
    if (initialLaunch && INITIAL_LAUNCH_HIDDEN.some((route) => localPath === route || localPath.startsWith(`${route}/`))) {
      return redirectTo(request, `/${pathnameLocale}/dashboard`);
    }
    const sessionCookieName = process.env.SESSION_COOKIE_NAME || "pg_session";
    const authenticationRequired = process.env.REQUIRE_AUTH === "true";
    if (authenticationRequired && requiresAuthentication(localPath) && !request.cookies.get(sessionCookieName)) {
      const returnTo = `${pathname}${search}`;
      return redirectTo(request, `/${pathnameLocale}/login`, `?returnTo=${encodeURIComponent(returnTo)}`);
    }
    const response = NextResponse.next();
    response.cookies.set(localeCookieName, pathnameLocale, { path: "/", sameSite: "lax" });
    return response;
  }

  const shouldRedirect = pathname === "/" || legacyLocaleRoutes.some((route) => pathname === route || pathname.startsWith(`${route}/`));

  if (shouldRedirect) {
    const preferred = await resolveLocale(request, pathname === "/");
    return redirectTo(request, `/${preferred}${pathname === "/" ? "" : pathname}`, search);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next|.*\\..*).*)"]
};

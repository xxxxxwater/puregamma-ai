import { NextResponse, type NextRequest } from "next/server";
import { defaultLocale, isLocale, legacyLocaleRoutes, localeCookieName, localeFromAcceptLanguage, localePrefixPattern } from "@/i18n/routing";

const PUBLIC_FILE = /\.(.*)$/;
const INITIAL_LAUNCH_HIDDEN = ["/signals", "/playbooks", "/strategies", "/trading", "/nautilus", "/data-sources", "/integrations", "/daily-push", "/billing/mock-checkout"];
const AUTHENTICATED_ROUTES = ["/account", "/admin", "/billing", "/chat", "/dashboard", "/options", "/portfolio", "/reports"];

export function middleware(request: NextRequest) {
  const { pathname, search } = request.nextUrl;

  if (pathname.startsWith("/api") || pathname.startsWith("/_next") || PUBLIC_FILE.test(pathname)) {
    return NextResponse.next();
  }

  const pathnameLocale = pathname.match(localePrefixPattern)?.[1];
  if (isLocale(pathnameLocale)) {
    const localPath = pathname.replace(localePrefixPattern, "") || "/";
    const initialLaunch = process.env.NEXT_PUBLIC_INITIAL_LAUNCH_MODE !== "false";
    if (initialLaunch && INITIAL_LAUNCH_HIDDEN.some((route) => localPath === route || localPath.startsWith(`${route}/`))) {
      const url = request.nextUrl.clone();
      url.pathname = `/${pathnameLocale}/dashboard`;
      url.search = "";
      return NextResponse.redirect(url);
    }
    const sessionCookieName = process.env.SESSION_COOKIE_NAME || "pg_session";
    const requiresAuthentication = AUTHENTICATED_ROUTES.some((route) => localPath === route || localPath.startsWith(`${route}/`));
    const authenticationRequired = process.env.REQUIRE_AUTH === "true";
    if (authenticationRequired && requiresAuthentication && !request.cookies.get(sessionCookieName)) {
      const url = request.nextUrl.clone();
      const returnTo = `${pathname}${search}`;
      url.pathname = `/${pathnameLocale}/login`;
      url.search = `?returnTo=${encodeURIComponent(returnTo)}`;
      return NextResponse.redirect(url);
    }
    const response = NextResponse.next();
    response.cookies.set(localeCookieName, pathnameLocale, { path: "/", sameSite: "lax" });
    return response;
  }

  const cookieLocale = request.cookies.get(localeCookieName)?.value;
  const preferred = isLocale(cookieLocale) ? cookieLocale : localeFromAcceptLanguage(request.headers.get("accept-language")) || defaultLocale;
  const shouldRedirect = pathname === "/" || legacyLocaleRoutes.some((route) => pathname === route || pathname.startsWith(`${route}/`));

  if (shouldRedirect) {
    const url = request.nextUrl.clone();
    url.pathname = `/${preferred}${pathname === "/" ? "" : pathname}`;
    url.search = search;
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next|.*\\..*).*)"]
};

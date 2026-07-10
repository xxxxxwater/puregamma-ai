import { NextResponse, type NextRequest } from "next/server";
import { defaultLocale, isLocale, legacyLocaleRoutes, localeCookieName, localeFromAcceptLanguage, localePrefixPattern } from "@/i18n/routing";

const PUBLIC_FILE = /\.(.*)$/;

export function middleware(request: NextRequest) {
  const { pathname, search } = request.nextUrl;

  if (pathname.startsWith("/api") || pathname.startsWith("/_next") || PUBLIC_FILE.test(pathname)) {
    return NextResponse.next();
  }

  const pathnameLocale = pathname.match(localePrefixPattern)?.[1];
  if (isLocale(pathnameLocale)) {
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

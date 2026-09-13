import type { Metadata } from "next";
import type { ReactNode } from "react";
import Script from "next/script";
import "./globals.css";

export const metadata: Metadata = {
  title: "PureGamma AI — Cross-Asset Research & Portfolio Intelligence",
  description: "AI-powered cross-market research, portfolio monitoring, daily briefs, and controlled execution for digital assets, equities, and derivatives.",
  keywords: ["AI research", "portfolio intelligence", "crypto research", "BTC", "ETH", "quantitative trading", "market analysis", "investment research"],
  icons: { icon: "/logo.png", apple: "/logo.png" },
  robots: { index: true, follow: true },
  openGraph: {
    title: "PureGamma AI — Cross-Asset Research & Portfolio Intelligence",
    description: "AI-powered cross-market research, portfolio monitoring, daily briefs, and controlled execution.",
    siteName: "PureGamma AI",
    locale: "en_US",
    type: "website",
    images: [{ url: `${process.env.NEXT_PUBLIC_SITE_URL || "https://puregamma.ai"}/logo.png`, width: 512, height: 512 }],
  },
  twitter: {
    card: "summary",
    title: "PureGamma AI",
    description: "AI-powered cross-market research, portfolio monitoring, daily briefs, and controlled execution.",
  },
  verification: {
    google: process.env.GOOGLE_SITE_VERIFICATION,
  },
};

const visualStyleDefault = process.env.NEXT_PUBLIC_VISUAL_STYLE_DEFAULT === "classic" ? "classic" : "glass";

/**
 * Pre-paint bootstrap.
 *
 * Runs before first paint and resolves the appearance from storage BEFORE the
 * browser renders anything, which is what removes the flash. Previously only
 * the visual style was applied here; theme and font scale were applied in a
 * `useEffect`, i.e. after hydration, so a light-preference user saw the dark
 * default on every single load and the page reflowed from 16px to 14/18px.
 *
 * Contract:
 *  - `pg_theme` keeps its existing accepted values (`light` / `dark`) so saved
 *    preferences are preserved; `system` (or anything unrecognised, or a
 *    storage that throws) falls back to the OS preference.
 *  - `data-theme` is ALWAYS written as `light` or `dark`. The stylesheet still
 *    contains light-scoped rules (`:root[data-theme="light"] ::selection`, the
 *    grid backdrop), so leaving the attribute off would silently drop them.
 *  - `color-scheme` is set here and in CSS so native controls — the `<select>`
 *    popups, scrollbars and date pickers — follow the app theme instead of the
 *    operating system. Nothing here weakens any CSP: it is an inline script in
 *    the document, as the existing visual-style script already was.
 */
const appearanceBootstrap = `(function(){try{
var d=document.documentElement;
var read=function(k){try{return window.localStorage.getItem(k);}catch(e){return null;}};
var pref=read('pg_theme');
if(pref!=='light'&&pref!=='dark'){pref=(window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches)?'dark':'light';}
d.dataset.theme=pref;
d.style.colorScheme=pref;
var fs=read('pg_font_scale');
d.dataset.fontScale=(fs==='compact'||fs==='large')?fs:'default';
var vs=read('pg_visual_style');
d.dataset.visualStyle=(vs==='classic')?'classic':${JSON.stringify(visualStyleDefault)};
}catch(e){}})();`;

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <link rel="icon" href="/logo.png" type="image/png" />
        <link rel="apple-touch-icon" href="/logo.png" />
        <meta name="google-site-verification" content="am4owqouAFJwpQpOFy__OAAm1HeW2MPH5hqDlJ2C1vM" />
        {/*
          A plain inline <script> in <head>, not next/script.

          next/script with strategy="beforeInteractive" did NOT reach the
          server-rendered HTML for this App Router page — the response's <html>
          carried no data-theme and no bootstrap script, so the theme was still
          being decided after the document was parsed and the light default had
          already painted. A raw inline script is executed synchronously by the
          HTML parser while it walks <head>, which is before the body is parsed
          and therefore before the first paint. That is the only placement that
          actually removes the flash.
        */}
        <script dangerouslySetInnerHTML={{ __html: appearanceBootstrap }} />
        <Script async src="https://www.googletagmanager.com/gtag/js?id=AW-18313089953" />
        <Script id="gtag-init" dangerouslySetInnerHTML={{ __html: `window.dataLayer = window.dataLayer || []; function gtag(){dataLayer.push(arguments);} gtag('js', new Date()); gtag('config', 'AW-18313089953');` }} />
      </head>
      <body>
        {children}
      </body>
    </html>
  );
}

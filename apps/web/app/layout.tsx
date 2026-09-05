import type { Metadata } from "next";
import type { ReactNode } from "react";
import Script from "next/script";
import "./globals.css";
import "./apple-fluid.css";
import "./apple-workspaces.css";
import "./agent-fluid-runtime.css";

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

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <link rel="icon" href="/logo.png" type="image/png" />
        <link rel="apple-touch-icon" href="/logo.png" />
        <meta name="google-site-verification" content="am4owqouAFJwpQpOFy__OAAm1HeW2MPH5hqDlJ2C1vM" />
        <Script id="pg-visual-style" strategy="beforeInteractive" dangerouslySetInnerHTML={{ __html: `(function(){try{var s=window.localStorage.getItem('pg_visual_style');document.documentElement.dataset.visualStyle=(s==='classic'?'classic':${JSON.stringify(visualStyleDefault)});}catch(e){document.documentElement.dataset.visualStyle=${JSON.stringify(visualStyleDefault)};}})();` }} />
        <Script async src="https://www.googletagmanager.com/gtag/js?id=AW-18313089953" />
        <Script id="gtag-init" dangerouslySetInnerHTML={{ __html: `window.dataLayer = window.dataLayer || []; function gtag(){dataLayer.push(arguments);} gtag('js', new Date()); gtag('config', 'AW-18313089953');` }} />
      </head>
      <body>
        {children}
      </body>
    </html>
  );
}

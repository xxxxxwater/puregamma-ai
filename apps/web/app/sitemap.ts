import type { MetadataRoute } from "next";

const baseUrl = process.env.NEXT_PUBLIC_SITE_URL || "https://puregamma.ai";

const locales = ["en", "zh"] as const;

const localizedPages = [
  { path: "/", changeFrequency: "daily" as const, priority: 1.0 },
  { path: "/api", changeFrequency: "weekly" as const, priority: 0.9 },
  { path: "/login", changeFrequency: "monthly" as const, priority: 0.6 },
  { path: "/signup", changeFrequency: "monthly" as const, priority: 0.7 },
  { path: "/forgot-password", changeFrequency: "monthly" as const, priority: 0.3 },
];

// Legal pages live at the root (no locale prefix); /{locale}/terms 404s.
const rootPages = [
  { path: "/terms", changeFrequency: "monthly" as const, priority: 0.2 },
  { path: "/privacy", changeFrequency: "monthly" as const, priority: 0.2 },
];

export default function sitemap(): MetadataRoute.Sitemap {
  const entries: MetadataRoute.Sitemap = [];

  for (const locale of locales) {
    for (const page of localizedPages) {
      entries.push({
        url: `${baseUrl}/${locale}${page.path === "/" ? "" : page.path}`,
        lastModified: new Date(),
        changeFrequency: page.changeFrequency,
        priority: page.priority,
      });
    }
  }

  for (const page of rootPages) {
    entries.push({
      url: `${baseUrl}${page.path}`,
      lastModified: new Date(),
      changeFrequency: page.changeFrequency,
      priority: page.priority,
    });
  }

  return entries;
}

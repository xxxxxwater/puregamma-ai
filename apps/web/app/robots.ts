import type { MetadataRoute } from "next";

const baseUrl = process.env.NEXT_PUBLIC_SITE_URL || "https://puregamma.ai";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      { userAgent: "*", allow: "/" },
      { userAgent: "*", disallow: ["/internal/", "/api/", "/admin/", "/_next/"] },
    ],
    sitemap: `${baseUrl}/sitemap.xml`,
  };
}

import type { MetadataRoute } from "next";
import { SITE_URL } from "@/lib/site";

export const dynamic = "force-static";   // emitted as out/robots.txt by the static export

export default function robots(): MetadataRoute.Robots {
  return {
    rules: { userAgent: "*", allow: "/", disallow: ["/chat", "/memory"] },   // on-device pages, not the website
    sitemap: `${SITE_URL}/sitemap.xml`,
    host: SITE_URL,
  };
}

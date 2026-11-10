import type { Metadata, Viewport } from "next";
import { Hanken_Grotesk, Martian_Mono } from "next/font/google";
import { SITE_DESCRIPTION, SITE_KEYWORDS, SITE_NAME, SITE_TITLE, SITE_URL } from "@/lib/site";
import "./globals.css";

// Fonts are downloaded at build time and served from this Mac (no Google request at runtime).
const hanken = Hanken_Grotesk({ subsets: ["latin"], weight: ["200", "300", "400", "500", "600", "700"], variable: "--font-hanken", display: "swap" });
// Martian Mono has no arrows (→); like the original, they must fall back to the Mac's mono font, not to
// next/font's Arial-based metric fallback (which made arrows wide).
const martian = Martian_Mono({ subsets: ["latin"], weight: ["300", "400", "500"], variable: "--font-martian", display: "swap",
  adjustFontFallback: false, fallback: ["ui-monospace", "SF Mono", "Menlo", "monospace"] });

// Site-wide SEO. Share images are static files next to this layout (opengraph-image.png / twitter-image.png, made
// by scripts/og.mjs), so they work with the static export. Canonical/OG URLs use NEXT_PUBLIC_SITE_URL (src/lib/site.ts).
export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: { default: SITE_TITLE, template: "%s — Stiti" },
  description: SITE_DESCRIPTION,
  applicationName: SITE_NAME,
  keywords: SITE_KEYWORDS,
  category: "technology",
  alternates: { canonical: "/" },
  openGraph: {
    type: "website", url: "/", siteName: SITE_NAME, locale: "en_US",
    title: SITE_TITLE, description: SITE_DESCRIPTION,
  },
  twitter: { card: "summary_large_image", title: SITE_TITLE, description: SITE_DESCRIPTION },
  robots: { index: true, follow: true },
  icons: { icon: [{ url: "/favicon.svg", type: "image/svg+xml" }], apple: [{ url: "/apple-touch-icon.png", sizes: "180x180" }] },
  formatDetection: { telephone: false, email: false, address: false },
};

export const viewport: Viewport = { themeColor: "#ecebf2", width: "device-width", initialScale: 1, viewportFit: "cover" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${hanken.variable} ${martian.variable}`}>
      <body>{children}</body>
    </html>
  );
}

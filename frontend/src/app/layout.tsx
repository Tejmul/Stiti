import type { Metadata, Viewport } from "next";
import { Hanken_Grotesk, Martian_Mono } from "next/font/google";
import "./globals.css";

// Fonts are downloaded at build time and served from this Mac (no Google request at runtime).
const hanken = Hanken_Grotesk({ subsets: ["latin"], weight: ["200", "300", "400", "500", "600", "700"], variable: "--font-hanken", display: "swap" });
// Martian Mono has no arrows (→); like the original, they must fall back to the Mac's mono font, not to
// next/font's Arial-based metric fallback (which made arrows wide).
const martian = Martian_Mono({ subsets: ["latin"], weight: ["300", "400", "500"], variable: "--font-martian", display: "swap",
  adjustFontFallback: false, fallback: ["ui-monospace", "SF Mono", "Menlo", "monospace"] });

export const metadata: Metadata = {
  title: "Stiti — your local AI buddy",
  description: "Stiti is a voice buddy that runs on your Mac, remembers everything you tell her, and learns how you like to be talked to.",
  icons: { icon: "/favicon.svg" },
};

export const viewport: Viewport = { themeColor: "#ecebf2", width: "device-width", initialScale: 1, viewportFit: "cover" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${hanken.variable} ${martian.variable}`} suppressHydrationWarning>
      <head>
        {/* Before first paint: if the intro already played in this tab, hide the preloader (no 000% flash). */}
        <script dangerouslySetInnerHTML={{ __html: `try{if(sessionStorage.getItem("stiti_intro")==="1")document.documentElement.classList.add("intro-seen")}catch(e){}` }} />
      </head>
      <body>{children}</body>
    </html>
  );
}

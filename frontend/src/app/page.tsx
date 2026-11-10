import Landing from "@/components/landing/Landing";
import { GITHUB, SITE_DESCRIPTION, SITE_NAME, SITE_URL } from "@/lib/site";
import "./landing.css";

// Title, description, canonical and share images come from the root layout (one source of truth).

// Structured data: what Stiti is, for search engines and AI crawlers (no personal data).
const jsonLd = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  name: SITE_NAME,
  description: SITE_DESCRIPTION,
  url: `${SITE_URL}/`,
  image: `${SITE_URL}/opengraph-image.png`,
  applicationCategory: "LifestyleApplication",
  applicationSubCategory: "Personal AI assistant",
  operatingSystem: "macOS",
  isAccessibleForFree: true,
  offers: { "@type": "Offer", price: "0", priceCurrency: "USD" },
  featureList: [
    "Voice conversation: say “Hey Stiti” and talk naturally",
    "Remembers your people, plans and past conversations",
    "Alarms, reminders and todos by voice",
    "News, tech and AI updates, new research papers and placement news",
    "One-night crash courses on any book or subject",
    "Notices when you sound tired or stressed",
    "Learns how you like to be talked to",
    "Memory stays on your Mac; no account",
  ],
  sameAs: [GITHUB],
};

export default function Page() {
  return (
    <>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd).replace(/</g, "\\u003c") }} />
      <Landing />
    </>
  );
}

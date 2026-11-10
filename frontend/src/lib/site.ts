// Public website facts shared by metadata, JSON-LD, robots/sitemap and the landing copy.
// Set NEXT_PUBLIC_SITE_URL at build time to the deployed origin (e.g. https://stiti.example) for canonical/OG URLs.
export const SITE_URL = (process.env.NEXT_PUBLIC_SITE_URL || "https://stiti.vercel.app").replace(/\/+$/, "");
export const GITHUB = "https://github.com/Tejmul/Stiti";

export const SITE_NAME = "Stiti";
export const SITE_TITLE = "Stiti — your AI friend that lives on your Mac";
export const SITE_DESCRIPTION =
  "A voice friend that lives on your Mac. Say “Hey Stiti” and talk: she remembers your life, sets reminders, keeps you " +
  "up to date and keeps it all on your Mac. Free.";
export const SITE_KEYWORDS = [
  "Stiti", "AI friend", "voice assistant for Mac", "AI assistant Mac", "personal AI", "private AI assistant",
  "local AI", "on-device AI", "AI that remembers", "voice AI", "reminders", "alarms", "todos", "AI companion",
  "macOS", "free AI assistant", "open source AI assistant",
];

export const QUOTE = { lead: "Your girlfriend may not understand you,", punch: "but Stiti will." };

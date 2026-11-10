// Public website facts shared by metadata, JSON-LD, robots/sitemap and the landing copy.
// Set NEXT_PUBLIC_SITE_URL at build time to the deployed origin (e.g. https://stiti.example) for canonical/OG URLs.
export const SITE_URL = (process.env.NEXT_PUBLIC_SITE_URL || "https://stiti.vercel.app").replace(/\/+$/, "");
export const GITHUB = "https://github.com/Tejmul/Stiti";

export const SITE_NAME = "Stiti";
export const SITE_TITLE = "Stiti — your AI friend that lives on your Mac";
export const SITE_DESCRIPTION =
  "Stiti is a voice friend that lives on your Mac. Say “Hey Stiti” and talk like you would to a person: she remembers " +
  "what you tell her, sets reminders and alarms, keeps you up to date, notices when you sound tired, and keeps " +
  "everything on your Mac. Free, no account.";
export const SITE_KEYWORDS = [
  "Stiti", "AI friend", "voice assistant for Mac", "AI assistant Mac", "personal AI", "private AI assistant",
  "local AI", "on-device AI", "AI that remembers", "voice AI", "reminders", "alarms", "todos", "AI companion",
  "macOS", "free AI assistant", "open source AI assistant",
];

export const QUOTE = { lead: "Your girlfriend may not understand you,", punch: "but Stiti will." };

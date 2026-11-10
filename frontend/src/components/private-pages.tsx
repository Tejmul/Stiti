// The owner-only pages. The PUBLIC build (STITI_PUBLIC=1) swaps this module for private-pages.public.tsx via a
// bundler alias (next.config.ts), so the chat/memory code is not even shipped on a deployed site.
export { default as ChatPage } from "@/components/chat/ChatApp";
export { default as MemoryPage } from "@/components/memory/MemoryPage";
export const PUBLIC_BUILD = false;

import type { Metadata } from "next";
import { BoardPage } from "@/components/private-pages";

// The whiteboard tutor. Served on this Mac by the tutor's board server (127.0.0.1:7318, which serves out/board.html
// at "/"); the PUBLIC build swaps in a "runs on your Mac" page. BoardPage itself is a client component and loads
// Excalidraw with next/dynamic (ssr: false).
export const metadata: Metadata = {
  title: { absolute: "Stiti Whiteboard" },
  robots: { index: false, follow: false },   // on-device page, never part of the public website
  alternates: { canonical: null },
  description: "Stiti's whiteboard tutor.",
};

export default function Page() {
  return <BoardPage />;
}

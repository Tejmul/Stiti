import type { Metadata } from "next";
import { ChatPage } from "@/components/private-pages";
import "./chat.css";

export const metadata: Metadata = {
  title: { absolute: "Chat · Stiti" },
  robots: { index: false, follow: false },   // on-device page, never part of the public website
  alternates: { canonical: null },
  description: "Talk to Stiti, your local AI buddy.",
};

export default function Page() {
  return <ChatPage />;
}

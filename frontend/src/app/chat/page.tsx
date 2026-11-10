import type { Metadata } from "next";
import { ChatPage } from "@/components/private-pages";
import "./chat.css";

export const metadata: Metadata = {
  title: "Chat · Stiti",
  description: "Talk to Stiti, your local AI buddy.",
};

export default function Page() {
  return <ChatPage />;
}

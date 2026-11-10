import type { Metadata } from "next";
import ChatApp from "@/components/chat/ChatApp";
import "./chat.css";

export const metadata: Metadata = {
  title: "Chat · Stiti",
  description: "Talk to Stiti, your local AI buddy.",
};

export default function Page() {
  return <ChatApp />;
}

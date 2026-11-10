import type { Metadata } from "next";
import MemoryPage from "@/components/memory/MemoryPage";
import "./memory.css";

export const metadata: Metadata = {
  title: "Memory · Stiti",
  description: "Everything Stiti knows about you — facts, people, rules, habits, mood and every conversation. Stored on this Mac.",
};

export default function Page() {
  return <MemoryPage />;
}

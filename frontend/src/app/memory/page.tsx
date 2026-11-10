import type { Metadata } from "next";
import { MemoryPage } from "@/components/private-pages";
import "./memory.css";

export const metadata: Metadata = {
  title: "Memory · Stiti",
  description: "Everything Stiti knows about you — facts, people, rules, habits and mood. Stored on this Mac.",
};

export default function Page() {
  return <MemoryPage />;
}

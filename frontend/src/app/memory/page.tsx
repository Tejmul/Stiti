import type { Metadata } from "next";
import { MemoryPage } from "@/components/private-pages";
import "./memory.css";

export const metadata: Metadata = {
  title: { absolute: "Memory · Stiti" },
  robots: { index: false, follow: false },   // on-device page, never part of the public website
  alternates: { canonical: null },
  description: "Everything Stiti knows about you — facts, people, rules, habits and mood. Stored on this Mac.",
};

export default function Page() {
  return <MemoryPage />;
}

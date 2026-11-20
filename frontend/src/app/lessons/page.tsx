import type { Metadata } from "next";
import { LessonsPage } from "@/components/private-pages";
import "./lessons.css";

export const metadata: Metadata = {
  title: { absolute: "Lessons · Stiti" },
  robots: { index: false, follow: false },   // on-device page, never part of the public website
  alternates: { canonical: null },
  description: "Start a whiteboard lesson from your own files or any topic, see what you know, and read your notes.",
};

export default function Page() {
  return <LessonsPage />;
}

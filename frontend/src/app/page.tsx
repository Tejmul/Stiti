import type { Metadata } from "next";
import Landing from "@/components/landing/Landing";
import "./landing.css";

export const metadata: Metadata = {
  title: "Stiti — your local AI buddy",
  description: "Stiti is a voice buddy that keeps her memory on your Mac — your people, your plans, and how you like to be talked to.",
};

export default function Page() {
  return <Landing />;
}

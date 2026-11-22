import type { Metadata } from "next";
import { Schritte } from "@/components/schritte/Schritte";

export const metadata: Metadata = {
  title: "Step reports",
  description: "Notes 1–4 from the offline comparison-step contract (synthetic placeholders).",
};

export default function SchrittePage() {
  return <Schritte />;
}

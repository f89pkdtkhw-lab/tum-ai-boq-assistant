import type { Metadata } from "next";
import { HistoryView } from "@/components/history/HistoryView";

export const metadata: Metadata = {
  title: "History · BoQ Review Assistant",
  description: "Past cases with estimates, actual values, comments and marks.",
};

export default function HistoryPage() {
  return <HistoryView />;
}

import type { Metadata } from "next";
import { Preise } from "@/components/preise/Preise";

export const metadata: Metadata = {
  title: "Prices · BoQ Review Assistant",
  description: "Price database: unit prices from priced bills, kept for later reviews.",
};

export default function PreisePage() {
  return <Preise />;
}

import type { Metadata } from "next";
import { Marge } from "@/components/marge/Marge";

export const metadata: Metadata = { title: "Margin · BoQ Review Assistant", description: "Competitor markup per item, outliers removed, and our price just below the median." };

export default function MargePage() {
  return <Marge />;
}

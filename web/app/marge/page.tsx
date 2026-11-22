import type { Metadata } from "next";
import { Marge } from "@/components/marge/Marge";

export const metadata: Metadata = { title: "Margin", description: "Pick competitors, set our margin on a slider, never below our costs." };

export default function MargePage() {
  return <Marge />;
}

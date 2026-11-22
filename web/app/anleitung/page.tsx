import type { Metadata } from "next";
import { Anleitung } from "@/components/anleitung/Anleitung";

export const metadata: Metadata = { title: "Tutorial", description: "Step-by-step guide to reviewing a BoQ." };

export default function TutorialPage() {
  return <Anleitung />;
}

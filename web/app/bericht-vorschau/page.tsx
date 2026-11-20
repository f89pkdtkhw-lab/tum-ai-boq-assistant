import type { Metadata } from "next";
import { Vorschau } from "./Vorschau";

export const metadata: Metadata = {
  title: "Review report preview · TUM.ai Construction Hackathon",
  description: "Synthetic example BoQ processed by the review pipeline and displayed as a review report.",
};

export default function BerichtVorschauSeite() {
  return <Vorschau />;
}

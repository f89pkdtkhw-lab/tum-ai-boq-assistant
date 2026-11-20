import type { Metadata } from "next";
import { Vorschau } from "./Vorschau";

export const metadata: Metadata = {
  title: "Prüfbericht-Vorschau · TUM.ai Construction Hackathon",
  description: "Synthetisches Beispiel-LV durch die Prüfpipeline und als Prüfbericht dargestellt.",
};

export default function BerichtVorschauSeite() {
  return <Vorschau />;
}

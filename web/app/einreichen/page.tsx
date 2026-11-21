import type { Metadata } from "next";
import { Einreichen } from "@/components/einreichen/Einreichen";

export const metadata: Metadata = { title: "Submit · BoQ Review Assistant", description: "Submit a price list or a project's final bill." };

export default function SubmitPage() {
  return <Einreichen />;
}

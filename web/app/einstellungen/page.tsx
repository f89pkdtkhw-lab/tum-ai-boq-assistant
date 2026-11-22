import type { Metadata } from "next";
import { EinstellungenSeite } from "@/components/einstellungen/EinstellungenSeite";

export const metadata: Metadata = { title: "Settings", description: "Language, theme, density and stored data." };

export default function SettingsPage() {
  return <EinstellungenSeite />;
}

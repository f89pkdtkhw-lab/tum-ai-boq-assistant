import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Produktname · TUM.ai Construction Hackathon",
  description: "Prototyp unseres Teams für TUM.ai Construction Hackathon 2026",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="de">
      <body>{children}</body>
    </html>
  );
}

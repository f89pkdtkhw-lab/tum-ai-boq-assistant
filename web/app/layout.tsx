import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Product name · TUM.ai Construction Hackathon",
  description: "Our team's prototype for TUM.ai Construction Hackathon 2026",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

import type { Metadata } from "next";
import "./globals.css";
import { Nav } from "@/components/nav/Nav";

export const metadata: Metadata = {
  title: "Product name · TUM.ai Construction Hackathon",
  description: "Our team's prototype for TUM.ai Construction Hackathon 2026",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Nav />
        {children}
      </body>
    </html>
  );
}

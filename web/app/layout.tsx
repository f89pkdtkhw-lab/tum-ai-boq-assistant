import type { Metadata } from "next";
import "./globals.css";
import { Nav } from "@/components/nav/Nav";
import { EinstellungenProvider } from "@/lib/einstellungen";

export const metadata: Metadata = {
  title: "BoQ Review Assistant",
  description: "Our team's prototype for TUM.ai Construction Hackathon 2026",
};

// Applies saved settings (lib/einstellungen.tsx) before the first paint, so there is no light/dark flash.
const THEME_SCRIPT = `(function(){var e={};try{e=JSON.parse(localStorage.getItem("lv-einstellungen-v1")||"{}")}catch(x){}var d=document.documentElement,h=new Date().getHours();d.dataset.theme=e.thema==="light"||e.thema==="dark"?e.thema:(h>=19||h<7?"dark":"light");d.dataset.dichte=e.dichte==="kompakt"?"kompakt":"normal";if(e.sprache==="de")d.lang="de"})()`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // suppressHydrationWarning: the inline script sets data-theme before React hydrates.
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body>
        <EinstellungenProvider>
          <div className="app">
            <Nav />
            {children}
          </div>
        </EinstellungenProvider>
      </body>
    </html>
  );
}

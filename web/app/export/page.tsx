import type { Metadata } from "next";
import { Export } from "./Export";

export const metadata: Metadata = {
  title: "Export · LV-Prüfassistent",
  description: "Prüfbericht als PDF drucken oder als Excel-Datei herunterladen.",
};

export default function ExportSeite() {
  return <Export />;
}

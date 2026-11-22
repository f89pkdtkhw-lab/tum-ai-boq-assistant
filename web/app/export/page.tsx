import type { Metadata } from "next";
import { Export } from "./Export";

export const metadata: Metadata = {
  title: "Export",
  description: "Print the review report as PDF or download it as an Excel file.",
};

export default function ExportSeite() {
  return <Export />;
}

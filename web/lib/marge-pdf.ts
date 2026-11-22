// t271: shared helpers for "Read PDF with AI" on the margin page and in the vault tab.
import type { MargePdfAntwort } from "./api";
import type { VaultEintrag } from "./vault";

export function istPdfName(name: string): boolean {
  return name.trim().toLowerCase().endsWith(".pdf");
}

export function filtereVaultPdfs(liste: readonly VaultEintrag[]): VaultEintrag[] {
  return liste.filter((e) => istPdfName(e.dateiname));
}

export function xlsxAusMargeAntwort(antwort: Pick<MargePdfAntwort, "xlsx_base64" | "dateiname">): File {
  const roh = Uint8Array.from(atob(antwort.xlsx_base64), (c) => c.charCodeAt(0));
  return new File([roh], antwort.dateiname, { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
}

export function margeVergleichHref(vaultId: string): string {
  return `/marge?vault=${encodeURIComponent(vaultId)}`;
}

// Client-side downloads that reuse the export page's builders (JSON / Excel / PDF).
import type { Pruefbericht } from "./api";
import type { Bewertungen } from "./bewertung";
import { bewertungVon, statusName } from "./bewertung";
import { dateiname, xlsx } from "./export";
import { berichtPdf } from "./berichtpdf";
import type { Sprache } from "./i18n";
import { ladePreisliste } from "./preisliste";
import { preisbericht } from "./preisbericht";

type Uebersetzer = (text: string, werte?: Record<string, string | number>) => string;

export function speichereDatei(inhalt: BlobPart, typ: string, name: string) {
  const url = URL.createObjectURL(new Blob([inhalt], { type: typ }));
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

export function ladePreisbericht(bericht: Pruefbericht) {
  return preisbericht(bericht.lv.positionen, null, ladePreisliste());
}

export function jsonHerunterladen(bericht: Pruefbericht) {
  speichereDatei(JSON.stringify(bericht, null, 2), "application/json", dateiname(bericht.lv.name, "json"));
}

export function excelHerunterladen(bericht: Pruefbericht, bewertungen: Bewertungen) {
  const bytes = xlsx(bericht, bewertungen, ladePreisbericht(bericht));
  speichereDatei(bytes as BlobPart, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", dateiname(bericht.lv.name, "xlsx"));
}

export function pdfHerunterladen(bericht: Pruefbericht, bewertungen: Bewertungen, t: Uebersetzer, sprache: Sprache) {
  const bytes = berichtPdf(bericht, {
    t,
    sprache,
    preis: ladePreisbericht(bericht),
    status: (f) => {
      const s = bewertungVon(bewertungen, f.id).status;
      return s === "offen" ? "" : t(statusName(s));
    },
  });
  speichereDatei(bytes as BlobPart, "application/pdf", dateiname(bericht.lv.name, "pdf"));
}

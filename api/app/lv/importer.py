"""Format dispatch without storage; each format importer has its own file scope."""
from pathlib import Path
from ..modelle import LV
from . import excel, gaeb, pdf, pdf_vision


def _pdf(dateiname: str, inhalt: bytes) -> LV:
    """Text parser first; #192: pages with gaps (or a PDF with no recognized item) go to the AI vision fallback."""
    try:
        lv = pdf.importiere(dateiname, inhalt)
    except ValueError as exc:
        if "No BoQ positions" not in str(exc):  # unreadable, encrypted or scanned-only PDFs stay errors
            raise
        return pdf_vision.ergaenze(dateiname, inhalt, None, exc)
    return pdf_vision.ergaenze(dateiname, inhalt, lv)


def importiere(dateiname: str, inhalt: bytes) -> LV:
    endung = Path(dateiname).suffix.lower()
    if endung == ".json":
        return LV.model_validate_json(inhalt)
    parser = {".x83": gaeb.importiere, ".x84": gaeb.importiere,
              ".d83": gaeb.importiere, ".d84": gaeb.importiere, ".d86": gaeb.importiere,  # GAEB 90 (DA83/84/86)
              ".xlsx": excel.importiere, ".pdf": _pdf}.get(endung)
    if parser is None:
        raise ValueError("Unsupported format. Allowed: JSON, X83, X84, D83, D84, D86, XLSX, PDF.")
    return parser(dateiname, inhalt)

"""Format dispatch without storage; each format importer has its own file scope."""
from pathlib import Path
from ..modelle import LV
from . import excel, gaeb, pdf


def importiere(dateiname: str, inhalt: bytes) -> LV:
    endung = Path(dateiname).suffix.lower()
    if endung == ".json":
        return LV.model_validate_json(inhalt)
    parser = {".x83": gaeb.importiere, ".x84": gaeb.importiere,
              ".xlsx": excel.importiere, ".pdf": pdf.importiere}.get(endung)
    if parser is None:
        raise ValueError("Unsupported format. Allowed: JSON, X83, X84, XLSX, PDF.")
    return parser(dateiname, inhalt)

"""Synthetic demo price list (issue #111): one unit price per item type of the synthetic example bills.

Price = median EP of that item type across data/beispiel_lv_{sauber,mittel,gross}.json times a fixed
per-trade market factor, so the estimated bill visibly differs from the original. No partner data.
Run: python tools/demo_preisliste.py  ->  web/public/demo-preisliste.json
"""
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Fixed market factors per trade (synthetic; first word of the short text).
FAKTOR = {"Erdarbeiten": 1.06, "Betonarbeiten": 1.12, "Mauerarbeiten": 0.95, "Dacharbeiten": 1.18,
          "Fliesenarbeiten": 0.92, "Putzarbeiten": 1.04, "Malerarbeiten": 0.9, "Abdichtung": 1.1, "Bewehrung": 1.15,
          "Estricharbeiten": 0.97, "Fenster": 1.07, "Sanitär": 1.09}


def main() -> None:
    eps: dict[tuple[str, str], list[float]] = {}
    for name in ("sauber", "mittel", "gross"):
        lv = json.loads((ROOT / f"data/beispiel_lv_{name}.json").read_text(encoding="utf-8"))
        for p in lv["positionen"]:
            if p.get("ep") and p.get("einheit"):
                eps.setdefault((p["kurztext"], p["einheit"]), []).append(p["ep"])
    liste = [{"item": k, "unit": u, "price": round(statistics.median(v) * FAKTOR.get(k.split()[0], 1.0), 2)}
             for (k, u), v in sorted(eps.items())]
    assert liste and all(p["price"] > 0 for p in liste)
    out = ROOT / "web/public/demo-preisliste.json"
    out.write_text(json.dumps(liste, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(liste)} prices -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

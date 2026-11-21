"""Generate synthetic example BoQs (no partner data) of different quality, so a demo can show every side.

Deterministic (fixed seeds), so the files only change when this script changes. Run: python tools/beispiel_gross.py
- sauber:  small office building, ~300 items, no seeded errors           → data/beispiel_lv_sauber.json
- mittel:  residential building, ~800 items, some errors and outliers     → data/beispiel_lv_mittel.json
- gross:   housing estate, ~2,400 items in 3 buildings x 12 trades, ~4 % seeded errors (arithmetic, missing quantity,
           unit or long text, duplicate OZ), ~1.5 % unit-price outliers, outdated standards → data/beispiel_lv_gross.json
"""
import json
import random
from pathlib import Path

DATEN = Path(__file__).resolve().parent.parent / "data"

# (trade, unit, unit price range in EUR, typical works)
GEWERKE = [
    ("Erdarbeiten", "m³", (12, 45), ["Baugrubenaushub", "Bodenaustausch", "Verfüllung", "Oberboden abtragen", "Grabenaushub"]),
    ("Betonarbeiten", "m³", (160, 320), ["Bodenplatte C25/30", "Streifenfundament", "Stahlbetonwand", "Stahlbetondecke", "Stütze"]),
    ("Bewehrung", "t", (1400, 2100), ["Betonstahl B500B", "Betonstahlmatten", "Anschlussbewehrung"]),
    ("Mauerarbeiten", "m²", (45, 110), ["Außenwand KS 24 cm", "Innenwand KS 17,5 cm", "Ziegelmauerwerk 36,5 cm", "Trennwand 11,5 cm"]),
    ("Abdichtung", "m²", (25, 70), ["Bitumenbahn Bodenplatte", "Perimeterdämmung", "Kellerwandabdichtung"]),
    ("Dacharbeiten", "m²", (55, 140), ["Flachdachabdichtung", "Wärmedämmung Dach", "Attikaabdeckung"]),
    ("Fenster", "St", (450, 1600), ["Kunststoff 2-flg.", "Holz-Alu 1-flg.", "Dachflächenfenster"]),
    ("Putzarbeiten", "m²", (18, 42), ["Innenputz Kalkgips", "Außenputz mineralisch", "Sockelputz"]),
    ("Estricharbeiten", "m²", (22, 48), ["Zementestrich 50 mm", "Trittschalldämmung", "Heizestrich"]),
    ("Fliesenarbeiten", "m²", (48, 115), ["Bodenfliesen 60x60", "Wandfliesen Bad", "Sockelfliesen"]),
    ("Malerarbeiten", "m²", (6, 18), ["Dispersionsanstrich", "Grundierung", "Tapezierarbeiten Vlies"]),
    ("Sanitär", "St", (180, 950), ["WC-Anlage komplett", "Waschtisch", "Duschrinne", "Abwasserleitung DN 100"]),
]
GEBAEUDE = ["Haus A", "Haus B", "Tiefgarage"]
FEHLERQUOTE = 0.04
NORMQUOTE = 0.08
NORMTEXTE = {
    "Erdarbeiten": ["Ausführung nach ATV DIN 18300 (2012-09), Bodenklasse 3–5.", "Aushub nach ATV DIN 18300."],
    "Abdichtung": ["Abdichtung nach DIN 18195-4.", "Abdichtung nach DIN 18533 und DIN 18195-6."],
    "Betonarbeiten": ["Beton nach DIN EN 206 und DIN 1045-2.", "Ausführung nach DIN."],
    "Mauerarbeiten": ["Mauerwerk nach DIN 1053-1.", "Mauerwerk nach DIN EN 1996."],
}
PREISAUSREISSER = 0.015  # unit prices far off the usual range, for the price comparison (Preisspiegel)


# Quality profiles. "gross" keeps the original settings, so its file stays unchanged.
PROFILE = {
    "gross": dict(name="Synthetisches Großprojekt – Wohnanlage mit Tiefgarage", gebaeude=GEBAEUDE, gewerke=None, anzahl=(55, 80),
                  fehler=FEHLERQUOTE, typen=[92, 4, 2, 2], norm=NORMQUOTE, ausreisser=PREISAUSREISSER, seed=7),
    "mittel": dict(name="Synthetisches Mehrfamilienhaus – mittlere Qualität", gebaeude=["Haus 1"], gewerke=None, anzahl=(55, 75),
                   fehler=0.012, typen=[97, 2, 1, 0], norm=0.03, ausreisser=0.004, seed=21),
    "sauber": dict(name="Synthetisches Bürogebäude – sauberes LV", gebaeude=["Bürogebäude"],
                   gewerke=["Erdarbeiten", "Betonarbeiten", "Mauerarbeiten", "Fenster", "Malerarbeiten", "Sanitär"], anzahl=(45, 60),
                   fehler=0.004, typen=[100, 0, 0, 0], norm=0.0, ausreisser=0.0, seed=31, streuung=0.1),
}


def erzeuge(profil: str = "gross") -> dict:
    p = PROFILE[profil]
    zufall = random.Random(p["seed"])
    preise = random.Random(p["seed"] + 4)
    normen = random.Random(p["seed"] + 6)
    gewerke = [g for g in GEWERKE if p["gewerke"] is None or g[0] in p["gewerke"]]
    positionen = []
    for g, gebaeude in enumerate(p["gebaeude"], start=1):
        for t, (gewerk, einheit, (ep_min, ep_max), arbeiten) in enumerate(gewerke, start=1):
            for n in range(1, zufall.randint(*p["anzahl"]) + 1):
                arbeit = zufall.choice(arbeiten)
                menge = round(zufall.uniform(2, 900) if einheit != "t" else zufall.uniform(0.5, 40), 2 if einheit != "St" else 0)
                # "streuung": a clean BoQ prices the same work consistently (±10 % around the usual price).
                mitte = (ep_min + ep_max) / 2
                ep = round(zufall.uniform(ep_min, ep_max) if "streuung" not in p else mitte * (1 + zufall.uniform(-1, 1) * p["streuung"]), 2)
                pos = {
                    "oz": f"{g:02d}.{t:02d}.{n:04d}",
                    "kurztext": f"{gewerk} {arbeit}",
                    "langtext": f"{arbeit} im Bereich {gebaeude}, Abschnitt {n}, nach Plan herstellen, inkl. aller Nebenleistungen.",
                    "menge": menge, "einheit": einheit, "ep": ep, "gp": round(menge * ep, 2),
                    "typ": zufall.choices(["normal", "bedarf", "alternativ", "zulage"], p["typen"])[0],
                    "titel_pfad": [gebaeude, f"{t:02d} {gewerk}"],
                }
                if zufall.random() < p["fehler"]:
                    fehler = zufall.choice(["rechnung", "menge", "einheit", "langtext", "duplikat"])
                    # Keep the original random draws so the clean example retains its items and prices.
                    if profil == "sauber":
                        fehler = None
                    if fehler == "rechnung":
                        pos["gp"] = round(pos["gp"] * zufall.choice([0.1, 1.5, 10]), 2)
                    elif fehler == "menge":
                        pos["menge"] = None
                    elif fehler == "einheit":
                        pos["einheit"] = None
                    elif fehler == "langtext":
                        pos["langtext"] = ""
                    elif fehler == "duplikat" and positionen:
                        pos["oz"] = positionen[-1]["oz"]
                # Standard references as found in real BoQs, so the norm checks (N1–N5) have something to review.
                if normen.random() < p["norm"] and gewerk in NORMTEXTE:
                    pos["langtext"] += " " + normen.choice(NORMTEXTE[gewerk])
                # Separate generator, so the seeded data errors above stay the same.
                if preise.random() < p["ausreisser"] and pos["menge"] is not None:
                    pos["ep"] = round(pos["ep"] * preise.choice([0.15, 0.3, 2.5, 4]), 2)
                    pos["gp"] = round(pos["menge"] * pos["ep"], 2)
                positionen.append(pos)
    return {
        "name": p["name"],
        "quelle": "synthetisch: tools/beispiel_gross.py, keine Partnerdaten",
        "positionen": positionen,
        "summen": {},
    }


if __name__ == "__main__":
    for profil in PROFILE:
        lv = erzeuge(profil)
        ziel = DATEN / f"beispiel_lv_{profil}.json"
        ziel.write_text(json.dumps(lv, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"{ziel.name}: {len(lv['positionen'])} items")

"""Export one stored analysis from the local vault into .demo-replay/ for `python tools/dev.py --demo`.

    python3 tools/demo_fixture.py                         # latest report of LV_09_Porenbetondach
    python3 tools/demo_fixture.py --lv LV_15_Abdichtung_Aussenwaende
    python3 tools/demo_fixture.py --bericht a95da10bca80aaab --evaluation d06419fb8716c485

Copies the vault entries as they are (no edits): `bericht.json` (the full report incl. the bill) and
`evaluation.json` (the newest AI evaluation of the same bill after that report). The folder is git-ignored.
"""
import argparse
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VAULT = ROOT / "data" / "vault"


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lv", default="LV_09_Porenbetondach", help="lv_name in the vault")
    parser.add_argument("--bericht", help="vault id of the report (default: newest for --lv)")
    parser.add_argument("--evaluation", help="vault id of the AI evaluation (default: newest after the report)")
    parser.add_argument("--ziel", default=str(ROOT / ".demo-replay"))
    args = parser.parse_args()
    index = json.loads((VAULT / "index.json").read_text("utf-8"))
    eintraege = index if isinstance(index, list) else list(index.values())
    nach_id = {e["id"]: e for e in eintraege}

    def neuester(typ, ab=""):
        passend = [e for e in eintraege if e["typ"] == typ and e.get("lv_name") == args.lv and e["hochgeladen_am"] >= ab]
        return max(passend, key=lambda e: e["hochgeladen_am"], default=None)

    bericht = nach_id.get(args.bericht) if args.bericht else neuester("bericht")
    if bericht is None:
        raise SystemExit(f"✗ No report for {args.lv} in {VAULT}.")
    evaluation = nach_id.get(args.evaluation) if args.evaluation else neuester("auswertung", bericht["hochgeladen_am"])
    ziel = Path(args.ziel)
    ziel.mkdir(parents=True, exist_ok=True)

    def datei(e):
        return next((VAULT / "dateien").glob(f"{e['id']}.*"))

    shutil.copyfile(datei(bericht), ziel / "bericht.json")
    print(f"✓ report     {bericht['id']}  {bericht['dateiname']}")
    if evaluation:
        shutil.copyfile(datei(evaluation), ziel / "evaluation.json")
        print(f"✓ evaluation {evaluation['id']}  {evaluation['dateiname']}")
    else:
        (ziel / "evaluation.json").unlink(missing_ok=True)
        print("· no AI evaluation after this report; the normal route answers")
    (ziel / "quelle.json").write_text(json.dumps({"bericht": bericht, "evaluation": evaluation}, ensure_ascii=False, indent=1), "utf-8")
    print(f"→ {ziel}  ·  start with: python3 tools/dev.py --demo")


if __name__ == "__main__":
    main()

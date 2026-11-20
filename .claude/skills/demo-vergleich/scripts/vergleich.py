"""Compare observed, discrete outcomes on paired hackathon examples."""
import argparse
import json
from pathlib import Path


def summarize(rows):
    if not isinstance(rows, list) or not rows:
        raise ValueError("At least one executed comparison case is required.")
    seen = set()
    previous_hits = current_hits = 0
    gains, losses, no_result = [], [], []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict) or not {"fall", "soll", "bisher", "prototyp"} <= row.keys():
            raise ValueError(f"Row {index} requires fall, soll, bisher and prototyp.")
        name, expected = row["fall"], row["soll"]
        if not all(isinstance(v, str) and v.strip() for v in (name, expected)):
            raise ValueError(f"Row {index} requires a case name and expected result.")
        name = name.strip()
        if name in seen:
            raise ValueError(f"Duplicate case: {name}")
        seen.add(name)
        for variant in ("bisher", "prototyp"):
            value = row[variant]
            if value is None:
                no_result.append(f"{name} ({variant})")
            elif not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name}: {variant} expects text or null for a failed attempt.")
        before = row["bisher"] == expected
        after = row["prototyp"] == expected
        previous_hits += before
        current_hits += after
        if after and not before:
            gains.append(name)
        if before and not after:
            losses.append(name)
    return previous_hits, current_hits, len(seen), gains, losses, no_result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("datei", type=Path, help="UTF-8 JSON with both variants' results")
    args = parser.parse_args()
    try:
        rows = json.loads(args.datei.read_text(encoding="utf-8-sig"))
        before, after, count, gains, losses, missing = summarize(rows)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Comparison aborted: {exc}\n")
    print(f"Baseline correct: {before}/{count} | Prototype correct: {after}/{count}")
    for label, names in [("Newly correct", gains), ("Regression", losses), ("No result", missing)]:
        print(f"{label}: {', '.join(names) if names else '–'}")


if __name__ == "__main__":
    main()

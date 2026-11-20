"""Mirror team skills for Claude Code and validate their format.

Codex and Antigravity read `.agents/skills/` directly; Claude Code reads only `.claude/skills/`.
Symlinks often break on Windows, so this script creates a copy.

    python tools/agents_sync.py           # Update the copy
    python tools/agents_sync.py --check   # Check only, exit code 1 on differences
"""
import argparse
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / ".agents" / "skills"
TARGET = ROOT / ".claude" / "skills"
NOTE = ("<!-- Generated from .agents/skills/{name}/SKILL.md using python tools/agents_sync.py. "
        "Do not edit here. -->")
VALID_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _ignored(path):
    return "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}


def read_frontmatter(text):
    """Return the top-level frontmatter fields and the offset where the body starts."""
    text = text.replace("\r\n", "\n")
    if not text.startswith("---\n"):
        raise ValueError("does not start with YAML frontmatter (---)")
    end = text.find("\n---\n", 3)
    if end < 0:
        raise ValueError("frontmatter is not closed with ---")
    fields = {}
    for line in text[4:end].splitlines():
        key, separator, value = line.partition(":")
        if separator and not line.startswith((" ", "\t")):
            fields[key.strip()] = value.strip().strip("\"'")
    return fields, end + len("\n---\n")


def skill_problems(skill_dir):
    path = skill_dir / "SKILL.md"
    if not path.is_file():
        return [f"{skill_dir.name}: SKILL.md is missing"]
    try:
        fields, _ = read_frontmatter(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        return [f"{skill_dir.name}: {exc}"]
    problems = []
    if not VALID_NAME.match(skill_dir.name) or len(skill_dir.name) > 64:
        problems.append(f"{skill_dir.name}: folder name must use a-z, 0-9 and hyphens, at most 64 characters")
    if fields.get("name") != skill_dir.name:
        problems.append(f"{skill_dir.name}: frontmatter name must match the folder name")
    description = fields.get("description", "")
    if not description:
        problems.append(f"{skill_dir.name}: description is missing")
    elif len(description) > 1024:
        problems.append(f"{skill_dir.name}: description exceeds 1024 characters")
    return problems


def skill_dirs():
    if not SOURCE.is_dir():
        return []
    return sorted(path for path in SOURCE.iterdir() if path.is_dir() and not _ignored(path))


def expected_files():
    """Map each mirrored path below .claude/skills to its expected bytes."""
    files = {}
    for skill_dir in skill_dirs():
        for source in sorted(path for path in skill_dir.rglob("*") if path.is_file() and not _ignored(path)):
            relative = source.relative_to(SOURCE)
            data = source.read_bytes().replace(b"\r\n", b"\n")
            if relative.parts[1:] == ("SKILL.md",):
                text = data.decode("utf-8")
                _, body = read_frontmatter(text)
                text = text[:body] + "\n" + NOTE.format(name=skill_dir.name) + "\n" + text[body:]
                data = text.encode("utf-8")
            files[relative.as_posix()] = data
    return files


def actual_files():
    if not TARGET.is_dir():
        return {}
    return {
        path.relative_to(TARGET).as_posix(): path.read_bytes().replace(b"\r\n", b"\n")
        for path in TARGET.rglob("*")
        if path.is_file() and not _ignored(path)
    }


def problems():
    """Everything a reviewer would have to fix before the skills work in all tools."""
    found = [problem for skill_dir in skill_dirs() for problem in skill_problems(skill_dir)]
    if found:
        return found
    expected, actual = expected_files(), actual_files()
    for path in sorted(expected.keys() - actual.keys()):
        found.append(f".claude/skills/{path} is missing")
    for path in sorted(actual.keys() - expected.keys()):
        found.append(f".claude/skills/{path} has no source in .agents/skills")
    for path in sorted(expected.keys() & actual.keys()):
        if expected[path] != actual[path]:
            found.append(f".claude/skills/{path} differs from .agents/skills")
    return found


def sync():
    found = [problem for skill_dir in skill_dirs() for problem in skill_problems(skill_dir)]
    if found:
        raise ValueError("\n".join(found))
    expected = expected_files()
    for path in actual_files().keys() - expected.keys():
        (TARGET / path).unlink()
    for path, data in expected.items():
        target = TARGET / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or target.read_bytes().replace(b"\r\n", b"\n") != data:
            target.write_bytes(data)
    if TARGET.is_dir():
        for directory in sorted((p for p in TARGET.rglob("*") if p.is_dir()), reverse=True):
            if not any(directory.iterdir()):
                directory.rmdir()
    return sorted({path.split("/", 1)[0] for path in expected})


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="check only, write nothing")
    args = parser.parse_args()
    if args.check:
        found = problems()
        for problem in found:
            print(f"✗ {problem}")
        if found:
            print("Fix this in .agents/skills and run python tools/agents_sync.py.")
            return 1
        print(f"✓ {len(skill_dirs())} skills; Claude Code copy is up to date.")
        return 0
    try:
        names = sync()
    except ValueError as exc:
        print(exc)
        return 1
    print(f"✓ {len(names)} skills mirrored to .claude/skills: {', '.join(names)}")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())

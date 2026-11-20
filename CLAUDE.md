@AGENTS.md

## Nur für Claude Code

- `.claude/skills/` ist eine generierte Kopie von `.agents/skills/`. Ändere Skills nur in `.agents/skills/` und führe danach `python tools/agents_sync.py` aus. Ein Test prüft, dass beide Ordner übereinstimmen.
- Die gemeinsamen Freigaben stehen in `.claude/settings.json`. Persönliche Einstellungen gehören in `.claude/settings.local.json`, die nicht eingecheckt wird.

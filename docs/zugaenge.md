# Gestellte Zugänge am Wettbewerb

Partner und Veranstalter stellen oft Modell-Zugänge, als Konto oder als API-Schlüssel. Es gibt zwei getrennte Verwendungen: für eure **Coding-Agenten** und für euer **Produkt**. Schlüssel gehören nie in den Chat, aufs Board, in Issues oder ins Repo; teilt sie nur über einen Passwortmanager.

## Für die Coding-Agenten

| Zugang | Claude Code | Codex |
| --- | --- | --- |
| Konto (Login) | `claude`, dann `/login` mit dem gestellten Konto | `codex`, dann „Sign in“ mit dem gestellten Konto |
| API-Schlüssel | `export ANTHROPIC_API_KEY=…` vor dem Start | `codex login --api-key …` |
| AWS Bedrock | `export CLAUDE_CODE_USE_BEDROCK=1` plus AWS-Zugang | – |
| Google Vertex | `export CLAUDE_CODE_USE_VERTEX=1` plus Google-Projekt | – |

Mit einem gestellten API-Budget statt eigener Abos sieht quota-axi kein Kontingent. Dann den First Mate auf Budget stellen:

```sh
bash tools/firstmate/modus.sh budget   # günstigere Modelle, ein gemeinsames Budget, höchstens 4 Worker
bash tools/firstmate/modus.sh abo      # zurück zu den eigenen Abos
```

## Für das Produkt

```sh
cp .env.example .env.local
```

In `.env.local` den Schlüssel des gestellten Anbieters eintragen und `LLM_PROVIDER` sowie `LLM_MODEL` setzen. Ohne Eintrag nimmt das Backend den ersten Anbieter mit Schlüssel, ohne jeden Schlüssel den Mock. `python tools/setup.py` zeigt, welche Schlüssel gefunden wurden, nie ihren Wert. `http://localhost:8000/health` zeigt Anbieter und Modell, mit dem das Produkt gerade läuft.

| Anbieter | Variablen |
| --- | --- |
| Anthropic | `ANTHROPIC_API_KEY`, optional `ANTHROPIC_BASE_URL` |
| OpenAI oder kompatibler Endpunkt | `OPENAI_API_KEY`, `LLM_MODEL`, optional `OPENAI_BASE_URL` |
| Azure OpenAI | `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT` |
| Google Gemini | `GEMINI_API_KEY` |

Für ein öffentliches Deploy (Vercel oder Render, siehe `render.yaml`) tragt ihr dieselben Variablen im Dashboard des Hosters ein. Für GitHub Actions: `gh secret set NAME`.

## Budget im Blick

- Pay-per-Use-Schlüssel können in einer Stunde leer sein, wenn viele Worker Opus nutzen. Budget-Modus nutzt Haiku und Sonnet und Opus nur für die schwersten Aufgaben.
- Tests und Demo laufen im Mock und kosten nichts. Echte Modellaufrufe nur dort, wo das Issue es verlangt.
- Fragt am Stand des Partners nach dem Limit des Schlüssels und tragt es in `docs/case.md` ein.
